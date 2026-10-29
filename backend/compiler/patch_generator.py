"""Pure literal-span proposals over scanner-confirmed bytes; never write/apply.

The review format deliberately contains literal tokens, not entire source lines:
an SDK call may put a credential or prompt on the same line as its model keyword.
"""

from __future__ import annotations

import ast
import codecs
import copy
import hashlib
import io
import json
import re
import tokenize
from dataclasses import dataclass, field

from backend.schemas import PatchEdit, PatchFile, PatchFileValidation, PatchManifest, PatchOmission, PatchProposal, PatchSyntaxDiagnostic


class PatchInputError(ValueError):
    def __init__(self):
        super().__init__("Patch input or proposed content is inconsistent.")


class PatchBudgetExceeded(PatchInputError):
    pass


class PatchVerificationError(PatchInputError):
    """A bounded check outcome; never include parser text, source or host paths."""

    def __init__(self, validation: PatchFileValidation):
        super().__init__()
        self.validation = validation


@dataclass(frozen=True)
class FileProposal:
    file: PatchFile | None
    omissions: tuple[PatchOmission, ...]
    review_diff: str = field(default="", repr=False)


def _splice(raw, replacements):
    cursor, chunks = 0, []
    for start, end, replacement in replacements:
        if type(start) is not int or type(end) is not int or not cursor <= start < end <= len(raw):
            raise PatchInputError()
        chunks.extend((raw[cursor:start], replacement))
        cursor = end
    chunks.append(raw[cursor:])
    return b"".join(chunks)


def _verify_regions(raw, proposed, replacements):
    old_cursor = new_cursor = 0
    for start, end, replacement in replacements:
        length = start - old_cursor
        if (proposed[new_cursor:new_cursor + length] != raw[old_cursor:start]
                or proposed[new_cursor + length:new_cursor + length + len(replacement)] != replacement):
            raise PatchInputError()
        old_cursor, new_cursor = end, new_cursor + length + len(replacement)
    if proposed[new_cursor:] != raw[old_cursor:]:
        raise PatchInputError()


def _single_literal(text):
    if len(text) > 4096 or "\n" in text or "\r" in text:
        return False
    prefix = 1 if text[:1] in ("r", "R", "u", "U") else 0
    if text[prefix:prefix + 1] not in ("'", '"') or text[prefix:prefix + 3] in ("'''", '"""'):
        return False
    tokens = [item for item in tokenize.generate_tokens(io.StringIO(text).readline)
              if item.type not in (tokenize.NEWLINE, tokenize.ENDMARKER)]
    return len(tokens) == 1 and tokens[0].type == tokenize.STRING and tokens[0].string == text


def _parse_candidate(source):
    return ast.parse(source, feature_version=(3, 11))


def _verify_candidate(parsed, edits, encoding):
    """Shared generation/validation checks. Candidate bytes exist only in memory."""
    raw = parsed.raw
    def fail(reason, spans, candidate, syntax, preservation, proposed=None, diagnostic=None):
        raise PatchVerificationError(PatchFileValidation(
            file_path=parsed.fingerprint.file_path, original_digest=hashlib.sha256(raw).hexdigest(),
            candidate_digest=None if proposed is None else hashlib.sha256(proposed).hexdigest(),
            spans=spans, candidate=candidate, syntax=syntax, ast_preservation=preservation,
            reason=reason, diagnostic=diagnostic,
        ))
    replacements = [(edit.start_byte, edit.end_byte, replacement) for edit, replacement, _, _ in edits]
    try:
        proposed = _splice(raw, replacements)
    except PatchInputError:
        fail("invalid_spans", "invalid", "not_checked", "not_checked", "not_checked")
    if len(proposed) > 1024 * 1024:
        raise PatchBudgetExceeded()
    try:
        _verify_regions(raw, proposed, replacements)
        source = proposed.decode(encoding)
    except (PatchInputError, UnicodeError):
        fail("candidate_failed", "valid", "failed", "not_checked", "not_checked")
    try:
        tree = _parse_candidate(source)
        if sum(1 for _ in ast.walk(tree)) > 100000:
            raise PatchBudgetExceeded()
        expected = copy.deepcopy(parsed.tree)
        changes = {location: edit.proposed_model_id for edit, _, _, location in edits}
        changed = set()
        for item in ast.walk(expected):
            if isinstance(item, ast.Constant):
                key = item.lineno, item.col_offset, item.end_lineno, item.end_col_offset
                if key in changes:
                    item.value = changes[key]
                    item.kind = None
                    changed.add(key)
        if changed != changes.keys() or ast.dump(tree, include_attributes=False) != ast.dump(expected, include_attributes=False):
            fail("ast_mismatch", "valid", "constructed", "passed", "failed", proposed)
    except SyntaxError as error:
        def position(value, minimum):
            return value if type(value) is int and minimum <= value <= 2**53 - 1 else None
        fail("syntax_error", "valid", "constructed", "failed", "not_checked", proposed,
             PatchSyntaxDiagnostic(line_number=position(error.lineno, 1), column_number=position(error.offset, 0)))
    except (RecursionError, MemoryError):
        raise PatchBudgetExceeded() from None
    return proposed


def generate_file(parsed, nodes, decisions) -> FileProposal:
    """Transform only requested, unambiguous model constants; all bytes stay in memory."""
    if len(nodes) > 16 or len(decisions) > 16:
        raise PatchInputError()
    public = {item.node_id: item for item in nodes}
    selected = {item.node_id: item for item in decisions}
    if len(public) != len(nodes) or len(selected) != len(decisions) or selected.keys() != public.keys():
        raise PatchInputError()
    raw, path = parsed.raw, parsed.fingerprint.file_path
    if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != parsed.fingerprint.sha256:
        raise PatchInputError()
    confirmed = {item.node_id: (item, call) for item, call in zip(parsed.nodes, parsed.calls)}
    if len(parsed.nodes) != len(parsed.calls) or len(confirmed) != len(parsed.nodes):
        raise PatchInputError()
    omissions, eligible = [], []
    def omit(node, reason):
        omissions.append(PatchOmission(node_id=node, reason=reason))
    for identifier in sorted(selected):
        node, decision = public[identifier], selected[identifier]
        if node.file_path != path:
            raise PatchInputError()
        if decision.status == "baseline_retained":
            omit(identifier, "baseline_retained")
        elif decision.status != "recommended":
            omit(identifier, "decision_inconclusive")
        elif node.model_resolution != "literal" or node.current_model is None:
            omit(identifier, "model_unresolved")
        elif node.current_model == decision.selected_model_id:
            omit(identifier, "already_selected")
        elif node.current_model != decision.baseline_model_id:
            omit(identifier, "baseline_mismatch")
        elif identifier not in confirmed:
            omit(identifier, "unsupported_call")
        else:
            original, call = confirmed[identifier]
            if (original.file_path, original.line_number, original.column_number, original.call_signature, original.current_model) != (
                    node.file_path, node.line_number, node.column_number, node.call_signature, node.current_model):
                raise PatchInputError()
            eligible.append((node, decision, call))
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        if codecs.lookup(encoding).name not in ("utf-8", "utf-8-sig", "ascii"):
            for node, _, _ in eligible:
                omit(node.node_id, "unsupported_encoding")
            return FileProposal(None, tuple(sorted(omissions, key=lambda item: item.node_id)))
        source = raw.decode(encoding)
    except (ValueError, UnicodeError, LookupError, SyntaxError):
        raise PatchInputError() from None
    # For supported encodings original columns are UTF-8 byte columns. Retain
    # CRLF bytes and add the BOM stripped by utf-8-sig decoding explicitly.
    lines = re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", source)
    starts, total = [], len(codecs.BOM_UTF8) if raw.startswith(codecs.BOM_UTF8) else 0
    for line in lines:
        starts.append(total)
        total += len(line.encode("utf-8"))
    edits = []
    for node, decision, call in eligible:
        keywords = [keyword.value for keyword in call.keywords if keyword.arg == "model"]
        if (len(keywords) != 1 or any(keyword.arg is None for keyword in call.keywords)
                or not isinstance(keywords[0], ast.Constant) or type(keywords[0].value) is not str):
            omit(node.node_id, "unsupported_literal")
            continue
        literal = keywords[0]
        if literal.value != node.current_model or literal.end_lineno != literal.lineno:
            omit(node.node_id, "unsupported_literal")
            continue
        try:
            start = starts[literal.lineno - 1] + literal.col_offset
            end = starts[literal.end_lineno - 1] + literal.end_col_offset
            token = raw[start:end].decode("utf-8")
            if not _single_literal(token):
                omit(node.node_id, "unsupported_literal")
                continue
        except (IndexError, TypeError, UnicodeError, tokenize.TokenError):
            raise PatchInputError() from None
        replacement = json.dumps(decision.selected_model_id, ensure_ascii=True).encode("ascii")
        edit = PatchEdit(node_id=node.node_id, old_model_id=node.current_model, proposed_model_id=decision.selected_model_id,
                         start_byte=start, end_byte=end)
        location = literal.lineno, literal.col_offset, literal.end_lineno, literal.end_col_offset
        edits.append((edit, replacement, token, location))
    edits.sort(key=lambda item: item[0].start_byte)
    if not edits:
        return FileProposal(None, tuple(sorted(omissions, key=lambda item: item.node_id)))
    proposed = _verify_candidate(parsed, edits, encoding)
    metadata = PatchFile(file_path=path, original_digest=hashlib.sha256(raw).hexdigest(),
                         proposed_digest=hashlib.sha256(proposed).hexdigest(), edits=[item[0] for item in edits])
    diff = [f"--- a/{path}\n+++ b/{path}\n"]
    for edit, replacement, token, _ in edits:
        diff.extend((f"@@ bytes {edit.start_byte}:{edit.end_byte} node {edit.node_id} @@\n", "-" + token + "\n",
                     "+" + replacement.decode("ascii") + "\n"))
    return FileProposal(metadata, tuple(sorted(omissions, key=lambda item: item.node_id)), "".join(diff))


def assemble_proposal(analysis, source_manifest, optimization, requested_nodes, files, *, patch_id, created_at, maximum=524288):
    """Pure deterministic assembly for explicit IDs/times; no source text in metadata."""
    included = sorted((item for item in files if item.file is not None), key=lambda item: item.file.file_path)
    omissions = tuple(sorted((omission for item in files for omission in item.omissions), key=lambda item: item.node_id))
    response = optimization.response
    manifest = PatchManifest(
        patch_id=patch_id, analysis_id=analysis.analysis_id, source_manifest_digest=source_manifest.digest,
        optimization_id=optimization.optimization_id, optimization_digest=optimization.digest, policy_digest=response.policy.digest,
        created_at=created_at, provenance=response.result.provenance, requested_node_ids=tuple(sorted(requested_nodes)),
        files=[item.file for item in included], omissions=omissions,
        status="unavailable" if not included else "partial" if omissions else "proposed",
        complete_for_requested_nodes=bool(included) and not omissions,
    )
    review = "literal-spans.v1\n" + "".join(item.review_diff for item in included) if included else ""
    if len(review.encode("utf-8")) > min(maximum, 524288):
        raise PatchBudgetExceeded()
    data = dict(manifest=manifest.model_dump(mode="json"), review_diff=review,
                artifact_digest=hashlib.sha256(review.encode("utf-8")).hexdigest())
    digest = hashlib.sha256(json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return PatchProposal(**data, digest=digest)
