"""Pure verification of stored literal spans using the canonical generator.

The caller supplies scanner-verified ephemeral bytes and approved decisions.
No path is opened here, no review text is interpreted as replacement code, and
candidate bytes are neither returned publicly nor persisted.
"""

from pydantic import ValidationError

from backend.compiler.patch_generator import PatchBudgetExceeded, PatchInputError, PatchVerificationError, generate_file
from backend.schemas import PatchFile, PatchFileValidation


def validate_file(parsed, stored_file, nodes, decisions):
    """Return bounded check metadata and the canonical artifact, when verified."""
    def failure(reason, state="not_checked"):
        return PatchFileValidation(file_path=parsed.fingerprint.file_path, original_digest=parsed.fingerprint.sha256,
            spans="invalid" if reason == "invalid_spans" else state, candidate=state, syntax=state,
            ast_preservation=state, reason=reason), None
    try:
        stored_file = PatchFile.model_validate(stored_file)
        generated = generate_file(parsed, nodes, decisions, expected_file=stored_file)
    except PatchVerificationError as error:
        return error.validation, None
    except (PatchBudgetExceeded, MemoryError, RecursionError):
        return failure("resource_limit")
    except (PatchInputError, ValidationError, ValueError):
        return failure("invalid_spans")
    if generated.file is None:
        if any(item.reason == "unsupported_encoding" for item in generated.omissions):
            return failure("unsupported_encoding", "not_applicable")
        return failure("invalid_spans")
    return PatchFileValidation(file_path=generated.file.file_path, original_digest=generated.file.original_digest,
        candidate_digest=generated.file.proposed_digest, spans="valid", candidate="constructed", syntax="passed",
        ast_preservation="verified", reason="checked"), generated
