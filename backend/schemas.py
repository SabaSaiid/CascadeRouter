"""First-party API contract v1; no routes or compiler adapter are implemented here.

Public messages come from fixed catalogs. Source text, credentials, fingerprints
and internal graph evidence have no fields in this contract. Validation performs
no filesystem access and does not authorize a repository.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


API_SCHEMA_VERSION = "cascaderouter.scan.v1"
DataSource = Literal["live", "recorded", "mock"]
ResolutionState = Literal["missing", "unresolved", "literal", "reference"]
DiagnosticLevel = Literal["warning", "error"]
SchemaType = Literal["object", "array", "string", "number", "integer", "boolean", "null"]
Count = Annotated[int, Field(strict=True, ge=0, le=2**53 - 1)]
LineNumber = Annotated[int, Field(strict=True, ge=1, le=2**53 - 1)]
NodeId = Annotated[str, Field(strict=True, min_length=28, max_length=28, pattern=r"^llm_[0-9a-f]{24}$")]
AnalysisId = Annotated[str, Field(strict=True, min_length=41, max_length=41, pattern=r"^analysis_[0-9a-f]{32}$")]
RequestId = Annotated[str, Field(strict=True, min_length=36, max_length=36, pattern=r"^req_[0-9a-f]{32}$")]
Reference = Annotated[str, Field(strict=True, min_length=1, max_length=256)]

# These are public, deliberately generic messages, not exception renderings.
# Both the initial scan and the graph's guarded reread can emit scanner codes.
_SCAN_MESSAGES = {
    "root_error": "The repository root could not be safely inspected.",
    "invalid_root": "The repository root is not a directory.",
    "link_skipped": "A link or reparse point was omitted.",
    "outside_root": "A path outside the repository root was omitted.",
    "path_error": "A source path could not be safely inspected.",
    "directory_error": "A source directory could not be safely inspected.",
    "directory_depth_limit": "The directory depth budget was reached.",
    "directory_entry_limit": "The directory entry budget was reached.",
    "file_count_limit": "The source file count budget was reached.",
    "file_size_limit": "A source file exceeds the byte budget.",
    "total_bytes_limit": "The aggregate source byte budget was reached.",
    "file_changed": "A source changed during guarded reading.",
    "read_error": "A source file could not be safely read.",
    "binary_source": "A source contains invalid binary data.",
    "encoding_error": "A source has an unsupported or invalid encoding.",
    "syntax_error": "A source has invalid Python syntax.",
    "ast_node_limit": "The source AST budget was reached.",
    "analysis_resource_limit": "Source analysis reached a resource limit.",
    "sdk_import_ambiguous": "SDK provenance could not be established.",
    "model_literal_redacted": "An unsafe model literal was omitted.",
    "metadata_limit": "The argument metadata budget was reached.",
}
_GRAPH_MESSAGES = {
    "node_limit": "The graph node budget was reached.",
    "fingerprint_limit": "The source verification input budget was reached.",
    "invalid_scanner_node": "Scanner node identities or locations are inconsistent.",
    "invalid_source_fingerprint": "Source verification metadata is inconsistent.",
    "missing_source_fingerprint": "A new scan is required for source verification.",
    "invalid_source_options": "Recorded source limits are unavailable.",
    "input_scan_incomplete": "The initial scan reported incomplete coverage.",
    "source_changed": "A source changed after the initial scan.",
    "source_unavailable": "A previously scanned source could not be verified.",
    "call_sites_mismatch": "Verified source call sites differ from the initial scan.",
    "call_objects_mismatch": "Verified call identities are inconsistent.",
    "expression_limit": "The graph expression budget was reached.",
    "flow_analysis_limit": "Graph analysis reached a work or recursion limit.",
    "edge_limit": "The graph edge budget was reached.",
    "edge_evidence_limit": "The graph evidence budget was reached.",
    "value_provenance_limit": "The value provenance budget was reached.",
    "alias_limit": "The alias depth budget was reached.",
    "reference_limit": "An oversized source reference was omitted.",
    "cross_scope_dependency": "Cross-scope data flow remains unresolved.",
    "default_value_boundary": "Data flow through function defaults remains unresolved.",
    "unresolved_input": "A call input crosses unsupported data flow.",
    "unbound_producer": "A nested result lacks supported named evidence.",
    "self_dependency": "Self-referential graph evidence was rejected.",
    "repository_mismatch": "The graph repository differs from the initial scan.",
    "inconsistent_graph": "Invalid graph endpoints or a cycle were rejected.",
    "diagnostic_limit": "Additional graph diagnostics were omitted.",
}
for _boundary in (
    "control_flow_boundary", "mutation_boundary", "complex_assignment", "class_boundary",
    "decorator_boundary", "import_boundary", "wildcard_boundary", "opaque_await_boundary",
    "opaque_call_boundary", "opaque_selector", "container_selection", "dynamic_index",
    "unpacking_boundary", "ambiguous_container", "unsupported_expression",
):
    _GRAPH_MESSAGES[_boundary] = "Dependencies across unsupported behavior were omitted."

DIAGNOSTIC_MESSAGES = {**_SCAN_MESSAGES, **_GRAPH_MESSAGES}
DIAGNOSTIC_MESSAGES.update({"source_" + code: message for code, message in _SCAN_MESSAGES.items()})
DIAGNOSTIC_MESSAGES = MappingProxyType(DIAGNOSTIC_MESSAGES)
_ERROR_DIAGNOSTICS = frozenset({
    "root_error", "invalid_root", "read_error", "encoding_error", "syntax_error", "binary_source",
    "invalid_scanner_node", "invalid_source_fingerprint", "invalid_source_options",
    "call_sites_mismatch", "call_objects_mismatch", "repository_mismatch", "inconsistent_graph",
})
ERROR_MESSAGES = MappingProxyType({
    "invalid_request": "The request does not satisfy the API contract.",
    "repository_forbidden": "The repository is outside the permitted policy.",
    "repository_unavailable": "The repository could not be safely analyzed.",
    "not_found": "The requested resource was not found.",
    "source_conflict": "The source version no longer matches the analysis.",
    "request_too_large": "The request exceeds the permitted size.",
    "capacity_exceeded": "The service has reached its capacity limit.",
    "capability_unavailable": "The requested capability is unavailable.",
    "internal_error": "The operation could not be completed.",
})


class APIModel(BaseModel):
    """Strict, frozen models with immutable collections and hidden error inputs.

    Use model_dump(mode="json") / model_dump_json() for the wire format. Optional
    declared fields serialize as null by default; they are not silently omitted.
    Pydantic validation errors are internal: do not return errors() or exception
    text to clients, even with hide_input_in_errors enabled.
    """

    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True, hide_input_in_errors=True,
        revalidate_instances="always", validate_default=True,
    )


def _text_path(value: str) -> str:
    if not value.strip() or any(unicodedata.category(char) in {"Cc", "Cs", "Zl", "Zp"} for char in value):
        raise ValueError("Path text must be nonblank and contain no control characters.")
    return value


def _relative_path(value: str) -> str:
    _text_path(value)
    path = PurePosixPath(value)
    if (
        value == "." or "\\" in value or ":" in value or path.is_absolute()
        or ".." in path.parts or path.as_posix() != value
    ):
        raise ValueError("Source locations require canonical repository-relative POSIX paths.")
    return value


def _reference(value: str | None) -> str | None:
    if value is not None and (
        len(value.split(".")) > 17 or not all(part.isidentifier() for part in value.split("."))
    ):
        raise ValueError("References must be bounded Python names or attribute paths.")
    return value


def _sequence(value: object, maximum: int) -> tuple:
    if type(value) not in (list, tuple) or len(value) > maximum:
        raise ValueError("A bounded array is required.")
    return tuple(value)


def _resolution(kind: str, reference: str | None, references: tuple[str, ...]) -> None:
    if len(set(references)) != len(references):
        raise ValueError("Reference collections must not contain duplicates.")
    if kind == "reference":
        if reference is None or reference not in references:
            raise ValueError("Reference metadata requires its primary reference in the collection.")
    elif reference is not None:
        raise ValueError("Only reference metadata may have a primary reference.")
    if kind in ("missing", "literal") and references:
        raise ValueError("Missing and literal metadata cannot contain unresolved references.")


class SourceLocation(APIModel):
    """Relative source location; line is one-based, column is a UTF-8 byte offset."""

    file_path: Annotated[str, Field(min_length=1, max_length=4096)]
    line_number: LineNumber | None = None
    column_number: Count | None = None

    _path = field_validator("file_path")(_relative_path)

    @model_validator(mode="after")
    def location_consistency(self) -> SourceLocation:
        if self.column_number is not None and self.line_number is None:
            raise ValueError("A column requires a line number.")
        return self


class Diagnostic(APIModel):
    """A catalog code determines the only permitted message and severity.

    Omitting level/message fills their controlled values. Supplying values is
    allowed only when they match the catalog, supporting validated JSON round trips.
    Root-level diagnostics use location=null; a root '.' marker is not a file path.
    """

    code: Annotated[str, Field(min_length=1, max_length=80, json_schema_extra={"enum": sorted(DIAGNOSTIC_MESSAGES)})]
    level: DiagnosticLevel
    message: Annotated[str, Field(min_length=1, max_length=200)]
    location: SourceLocation | None = None

    @model_validator(mode="before")
    @classmethod
    def catalog_defaults(cls, data: object) -> object:
        if isinstance(data, dict) and type(data.get("code")) is str:
            code = data["code"]
            if code in DIAGNOSTIC_MESSAGES:
                data = dict(data)
                underlying = code[7:] if code.startswith("source_") else code
                data.setdefault("level", "error" if underlying in _ERROR_DIAGNOSTICS else "warning")
                data.setdefault("message", DIAGNOSTIC_MESSAGES[code])
        return data

    @model_validator(mode="after")
    def controlled_message(self) -> Diagnostic:
        if self.code not in DIAGNOSTIC_MESSAGES:
            raise ValueError("Unknown public diagnostic code.")
        underlying = self.code[7:] if self.code.startswith("source_") else self.code
        level = "error" if underlying in _ERROR_DIAGNOSTICS else "warning"
        if self.message != DIAGNOSTIC_MESSAGES[self.code] or self.level != level:
            raise ValueError("Diagnostic message and level must match their controlled code.")
        return self


class ErrorResponse(APIModel):
    """Flat controlled public error; never construct its message from an exception."""

    schema_version: Literal["cascaderouter.scan.v1"] = API_SCHEMA_VERSION
    code: Annotated[str, Field(min_length=1, max_length=80, json_schema_extra={"enum": sorted(ERROR_MESSAGES)})]
    message: Annotated[str, Field(min_length=1, max_length=200)]
    request_id: RequestId | None = None

    @model_validator(mode="before")
    @classmethod
    def catalog_default(cls, data: object) -> object:
        if isinstance(data, dict) and type(data.get("code")) is str and data["code"] in ERROR_MESSAGES:
            data = dict(data)
            data.setdefault("message", ERROR_MESSAGES[data["code"]])
        return data

    @model_validator(mode="after")
    def controlled_message(self) -> ErrorResponse:
        if self.code not in ERROR_MESSAGES or self.message != ERROR_MESSAGES[self.code]:
            raise ValueError("Error code and message must match the controlled catalog.")
        return self


class ScanRequest(APIModel):
    """Path syntax only; authorization and time-of-use containment are service duties."""

    repository_path: Annotated[str, Field(min_length=1, max_length=4096)]
    _path = field_validator("repository_path")(_text_path)


class SchemaShapeSummary(APIModel):
    """Limited shape/reference information, never a complete JSON Schema."""

    kind: ResolutionState
    reference: Reference | None = None
    definition_reference: Reference | None = None
    type: SchemaType | None = None
    property_count: Count | None = None
    required_count: Count | None = None

    _references = field_validator("reference", "definition_reference")(_reference)

    @model_validator(mode="after")
    def consistent_shape(self) -> SchemaShapeSummary:
        if (self.kind == "reference") != (self.reference is not None):
            raise ValueError("A schema reference requires reference resolution.")
        if self.kind == "missing" and any(value is not None for value in (
            self.definition_reference, self.type, self.property_count, self.required_count,
        )):
            raise ValueError("Missing schema metadata cannot contain shape information.")
        if self.kind in ("reference", "literal") and self.definition_reference is not None:
            raise ValueError("Definition references require unresolved schema metadata.")
        if self.kind == "reference" and any(value is not None for value in (
            self.type, self.property_count, self.required_count,
        )):
            raise ValueError("An unresolved schema reference has no resolved shape.")
        return self


class LimitedSchemaSummary(APIModel):
    """Only whitelisted response-format and shape facts; no properties or literals."""

    format_type: Literal["json_object", "json_schema", "text"]
    strict: bool | None = None
    schema_shape: SchemaShapeSummary | None = None

    @model_validator(mode="after")
    def consistent_format(self) -> LimitedSchemaSummary:
        if self.format_type != "json_schema" and (self.strict is not None or self.schema_shape is not None):
            raise ValueError("Schema shape and strictness require JSON-schema format.")
        return self


class LLMNode(SourceLocation):
    """Scanner-confirmed node identity and safe syntax metadata; no source snippets."""

    node_id: NodeId
    line_number: LineNumber
    column_number: Count
    current_model: Annotated[str, Field(min_length=1, max_length=256)] | None
    call_signature: Literal[
        "openai.OpenAI.chat.completions.create(...)",
        "openai.AsyncOpenAI.chat.completions.create(...)",
    ]
    function_name: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    model_resolution: ResolutionState
    model_reference: Reference | None = None
    model_references: tuple[Reference, ...] = Field(default=(), max_length=32)
    prompt_resolution: ResolutionState
    prompt_reference: Reference | None = None
    prompt_references: tuple[Reference, ...] = Field(default=(), max_length=32)
    schema_resolution: ResolutionState
    schema_reference: Reference | None = None
    schema_references: tuple[Reference, ...] = Field(default=(), max_length=32)
    limited_schema_summary: LimitedSchemaSummary | None = None

    _primary_references = field_validator("model_reference", "prompt_reference", "schema_reference")(_reference)

    @field_validator("function_name")
    @classmethod
    def function_syntax(cls, value: str | None) -> str | None:
        # The existing scanner caps qualified names at 256 characters; that cap
        # can land on a separator. Preserve that bounded syntax prefix too.
        prefix = value[:-1] if value is not None and len(value) == 256 and value.endswith(".") else value
        if prefix is not None and not all(part.isidentifier() for part in prefix.split(".")):
            raise ValueError("Function metadata must contain a bounded qualified-name syntax prefix.")
        return value

    @field_validator("model_references", "prompt_references", "schema_references", mode="before")
    @classmethod
    def reference_arrays(cls, value: object) -> tuple:
        return _sequence(value, 32)

    @field_validator("model_references", "prompt_references", "schema_references")
    @classmethod
    def valid_references(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for reference in value:
            _reference(reference)
        return value

    @field_validator("current_model")
    @classmethod
    def safe_model_identifier(cls, value: str | None) -> str | None:
        if value is not None and (
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", value, re.ASCII) is None
            or value.casefold().startswith((
                "sk-", "sk_", "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_",
                "xoxb-", "xoxp-", "xoxa-", "aiza",
            ))
            or re.fullmatch(r"(?:AKIA|ASIA)[A-Z0-9]{16}", value)
        ):
            raise ValueError("Model identifiers must satisfy the safe literal identifier policy.")
        return value

    @model_validator(mode="after")
    def resolution_consistency(self) -> LLMNode:
        for kind, reference, references in (
            (self.model_resolution, self.model_reference, self.model_references),
            (self.prompt_resolution, self.prompt_reference, self.prompt_references),
            (self.schema_resolution, self.schema_reference, self.schema_references),
        ):
            _resolution(kind, reference, references)
        if (self.model_resolution == "literal") != (self.current_model is not None):
            raise ValueError("Only literal model resolution permits a non-null model identifier.")
        if self.schema_resolution in ("missing", "reference") and self.limited_schema_summary is not None:
            raise ValueError("Missing or reference response formats cannot contain a literal summary.")
        return self


class ScanResponse(APIModel):
    """Flat public scan response; metadata is supplied explicitly by a future service.

    Ordering is preserved. Complete flags must agree; this model never repairs,
    filters or invents graph edges. Internal evidence and fingerprints stay internal.
    """

    schema_version: Literal["cascaderouter.scan.v1"] = API_SCHEMA_VERSION
    analysis_id: AnalysisId
    timestamp: datetime
    repository_path: Annotated[str, Field(min_length=1, max_length=4096)]
    nodes: tuple[LLMNode, ...] = Field(max_length=20_000)
    graph_edges: tuple[tuple[NodeId, NodeId], ...] = Field(max_length=10_000)
    scanned_files_count: Count
    discovered_files_count: Count
    total_source_bytes_read: Count
    detected_framework: Literal["OpenAI SDK"] | None
    data_source: DataSource
    scan_complete: bool
    graph_complete: bool
    complete: bool
    scan_diagnostics: tuple[Diagnostic, ...] = Field(max_length=50_000)
    graph_diagnostics: tuple[Diagnostic, ...] = Field(max_length=1_000)

    _path = field_validator("repository_path")(_text_path)

    @field_validator("timestamp", mode="before")
    @classmethod
    def supplied_timestamp(cls, value: object) -> datetime:
        if type(value) is str:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value) is None:
                raise ValueError("Timestamp must be an explicit timezone-aware RFC3339 value.")
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("Timestamp must be a valid RFC3339 value.") from None
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must be an explicit timezone-aware datetime.")
        return value.astimezone(timezone.utc)

    @field_serializer("timestamp", when_used="json")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    @field_validator("nodes", "scan_diagnostics", "graph_diagnostics", mode="before")
    @classmethod
    def bounded_arrays(cls, value: object, info) -> tuple:
        maximum = {"nodes": 20_000, "scan_diagnostics": 50_000, "graph_diagnostics": 1_000}[info.field_name]
        return _sequence(value, maximum)

    @field_validator("graph_edges", mode="before")
    @classmethod
    def endpoint_pairs(cls, value: object) -> tuple:
        return tuple(_sequence(pair, 2) for pair in _sequence(value, 10_000))

    @model_validator(mode="after")
    def consistent_result(self) -> ScanResponse:
        if self.complete != (self.scan_complete and self.graph_complete):
            raise ValueError("Overall completeness must equal both component flags.")
        if (self.scan_complete and self.scan_diagnostics) or (self.graph_complete and self.graph_diagnostics):
            raise ValueError("Diagnostics reporting omitted coverage require an incomplete component.")
        if any(diagnostic.code not in _SCAN_MESSAGES for diagnostic in self.scan_diagnostics):
            raise ValueError("Scan diagnostics must use initial-scanner codes.")
        graph_codes = _GRAPH_MESSAGES.keys() | {"source_" + code for code in _SCAN_MESSAGES}
        if any(diagnostic.code not in graph_codes for diagnostic in self.graph_diagnostics):
            raise ValueError("Graph diagnostics must use graph or guarded-reread codes.")
        if self.scanned_files_count > self.discovered_files_count:
            raise ValueError("Scanned file count cannot exceed discovered file count.")
        if len({node.file_path for node in self.nodes}) > self.scanned_files_count:
            raise ValueError("Node source files must be included in the scanned file count.")
        identifiers = {node.node_id for node in self.nodes}
        if len(identifiers) != len(self.nodes):
            raise ValueError("Node identities must be unique.")
        if len(set(self.graph_edges)) != len(self.graph_edges):
            raise ValueError("Graph endpoint pairs must be unique.")
        if any(source == target or source not in identifiers or target not in identifiers
               for source, target in self.graph_edges):
            raise ValueError("Graph edges require distinct endpoints included in the response.")
        if self.detected_framework is not None and not self.nodes:
            raise ValueError("A detected framework label requires scanner-confirmed nodes.")
        return self
