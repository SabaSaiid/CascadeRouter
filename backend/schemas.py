"""First-party API contract v1, shared by routes, adapter and persistence.

Public messages come from fixed catalogs. Source text, credentials, fingerprints
and internal graph evidence have no fields in this contract. Validation performs
no filesystem access and does not authorize a repository.
"""

from __future__ import annotations

import re
import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
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


class HealthResponse(APIModel):
    schema_version: Literal["cascaderouter.scan.v1"] = API_SCHEMA_VERSION
    status: Literal["ok"] = "ok"
    scan_available: bool
    analysis_retrieval_available: bool
    configuration_required: bool
    benchmark_available: bool = False
    benchmark_provenance: Literal["test", "recorded"] | None = None
    benchmark_unavailable_reason: Literal[
        "registry_unconfigured", "executor_unconfigured", "execution_not_approved",
        "lifecycle_unavailable", "storage_unavailable",
    ] | None = None
    optimization_available: bool = False


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
    """Flat public scan response; metadata is supplied explicitly by the scan service.

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


# Local benchmark contract. Scan provenance remains unchanged; test results can
# never be represented as live or recorded benchmark evidence.
JOB_SCHEMA_VERSION = "cascaderouter.benchmark.v1"
RunId = Annotated[str, Field(min_length=36, max_length=36, pattern=r"^run_[0-9a-f]{32}$")]
Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]
Digest = Annotated[str, Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")]
ModelIdentifier = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")]
BenchmarkProvenance = Literal["test", "recorded"]
JobState = Literal["queued", "running", "cancelling", "cancelled", "complete", "error", "interrupted"]
TERMINAL_JOB_STATES = frozenset({"cancelled", "complete", "error", "interrupted"})
JOB_TRANSITIONS = MappingProxyType({
    "queued": frozenset({"running", "cancelled", "error", "interrupted"}),
    "running": frozenset({"cancelling", "complete", "error", "interrupted"}),
    "cancelling": frozenset({"cancelled", "error", "interrupted"}),
    **{state: frozenset() for state in TERMINAL_JOB_STATES},
})
JOB_ERROR_MESSAGES = MappingProxyType({
    "executor_failed": "The local executor could not finish the job.",
    "invalid_result": "The executor returned an incompatible result.",
    "deadline_exceeded": "The job deadline was reached.",
    "recovery_unavailable": "The queued plan cannot be safely resumed.",
    "process_interrupted": "The previous execution was interrupted.",
    "shutdown": "The service stopped before execution could finish.",
    "storage_unavailable": "The job result could not be safely persisted.",
})


class BenchmarkRequest(APIModel):
    analysis_id: AnalysisId
    node_ids: tuple[NodeId, ...] = Field(min_length=1, max_length=16)
    baseline_model_id: ModelIdentifier
    candidate_model_ids: tuple[ModelIdentifier, ...] = Field(min_length=1, max_length=8)
    benchmark_case_set_id: Identifier
    evaluation_profile_id: Identifier
    idempotency_key: Identifier | None = None

    @field_validator("node_ids", "candidate_model_ids", mode="before")
    @classmethod
    def bounded_selections(cls, value, info):
        return _sequence(value, 16 if info.field_name == "node_ids" else 8)

    @model_validator(mode="after")
    def unique_selections(self):
        models = (self.baseline_model_id, *self.candidate_model_ids)
        if len(set(self.node_ids)) != len(self.node_ids) or len(set(models)) != len(models):
            raise ValueError("Selections must be distinct, including the baseline.")
        for value in models:
            LLMNode.safe_model_identifier(value)
        if self.idempotency_key is not None:
            LLMNode.safe_model_identifier(self.idempotency_key)
        return self


class VersionedReference(APIModel):
    identifier: Identifier
    version: Identifier


class ModelVersion(APIModel):
    identifier: ModelIdentifier
    version: Identifier

    _safe_id = field_validator("identifier")(LLMNode.safe_model_identifier)


class BenchmarkPlan(APIModel):
    schema_version: Literal["cascaderouter.benchmark.v1"] = JOB_SCHEMA_VERSION
    analysis_id: AnalysisId
    analysis_schema_version: Literal["cascaderouter.scan.v1"] = API_SCHEMA_VERSION
    analysis_digest: Digest
    node_ids: tuple[NodeId, ...] = Field(min_length=1, max_length=16)
    models: tuple[ModelVersion, ...] = Field(min_length=2, max_length=9)  # baseline first
    case_set: VersionedReference
    case_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    evaluation_profile: VersionedReference
    registry_digest: Digest
    configuration_version: Literal["zero-cost.jobs.v1"] = "zero-cost.jobs.v1"
    configuration_digest: Digest
    execution_digest: Digest
    provenance: BenchmarkProvenance

    case_set_digest: Digest | None = None
    evaluation_profile_digest: Digest | None = None

    @field_validator("node_ids", "models", "case_ids", mode="before")
    @classmethod
    def bounded_inputs(cls, value, info):
        return _sequence(value, {"node_ids": 16, "models": 9, "case_ids": 64}[info.field_name])

    @model_validator(mode="after")
    def unique_units(self):
        for values in (self.node_ids, self.case_ids, tuple(model.identifier for model in self.models)):
            if len(values) != len(set(values)):
                raise ValueError("Plan inputs must be unique.")
        if len(self.node_ids) * len(self.models) * len(self.case_ids) > 1024:
            raise ValueError("Plan work exceeds the contract budget.")
        return self

    def unit_keys(self) -> tuple[tuple[str, str, str], ...]:
        return tuple((node, model.identifier, case) for node in self.node_ids for model in self.models for case in self.case_ids)


class NumberMeasurement(APIModel):
    availability: Literal["available", "unavailable"]
    value: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def availability_matches(self):
        if (self.availability == "available") != (self.value is not None):
            raise ValueError("Availability must match the supplied measurement.")
        return self


class CountMeasurement(APIModel):
    availability: Literal["available", "unavailable"]
    value: Count | None = None

    @model_validator(mode="after")
    def availability_matches(self):
        if (self.availability == "available") != (self.value is not None):
            raise ValueError("Availability must match the supplied measurement.")
        return self


class BenchmarkMeasurement(APIModel):
    node_id: NodeId
    model_id: ModelIdentifier
    case_id: Identifier
    provenance: BenchmarkProvenance
    latency_ms: NumberMeasurement
    input_tokens: CountMeasurement
    output_tokens: CountMeasurement
    cost_usd: NumberMeasurement
    evaluation_status: Literal["passed", "failed", "inconclusive", "unavailable", "skipped", "not_run"]
    quality_score: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    evaluation: CaseEvaluation | None = None
    ttft_ms: NumberMeasurement | None = None
    calculated_cost: CostCalculation | None = None
    recording_id: Identifier | None = None
    evidence_digest: Digest | None = None
    output_available: bool | None = None

    _safe_id = field_validator("model_id")(LLMNode.safe_model_identifier)

    @model_validator(mode="after")
    def score_availability(self):
        if self.evaluation_status in ("unavailable", "not_run", "skipped") and self.quality_score is not None:
            raise ValueError("Unavailable evaluation has no score.")
        if self.evaluation is not None and self.evaluation.status != self.evaluation_status:
            raise ValueError("Evaluation status must agree with its checks.")
        return self

    def unit_key(self) -> tuple[str, str, str]:
        return self.node_id, self.model_id, self.case_id


class BenchmarkSummary(APIModel):
    provenance: BenchmarkProvenance
    evaluation_status: Literal["passed", "failed", "inconclusive"]
    metrics: OfflineMetrics | None = None


class JobError(APIModel):
    code: Annotated[str, Field(json_schema_extra={"enum": sorted(JOB_ERROR_MESSAGES)})]
    message: str

    @model_validator(mode="before")
    @classmethod
    def controlled_default(cls, data):
        if isinstance(data, dict) and type(data.get("code")) is str and data["code"] in JOB_ERROR_MESSAGES:
            data = {"message": JOB_ERROR_MESSAGES[data["code"]], **data}
        return data

    @model_validator(mode="after")
    def controlled_message(self):
        if self.code not in JOB_ERROR_MESSAGES or self.message != JOB_ERROR_MESSAGES[self.code]:
            raise ValueError("Job errors require a controlled code and message.")
        return self


class JobProgress(APIModel):
    completed_units: Annotated[int, Field(ge=0, le=1024)]
    total_units: Annotated[int, Field(ge=1, le=1024)]


class JobResponse(APIModel):
    schema_version: Literal["cascaderouter.benchmark.v1"] = JOB_SCHEMA_VERSION
    run_id: RunId
    status: JobState
    plan: BenchmarkPlan
    created_at: datetime
    updated_at: datetime
    deadline_at: datetime
    finished_at: datetime | None = None
    idempotency_key: Identifier | None = None
    progress: JobProgress
    measurements: tuple[BenchmarkMeasurement, ...] = Field(max_length=1024)
    result: BenchmarkSummary | None = None
    error: JobError | None = None
    cancellation_reason: Literal["requested", "deadline", "shutdown"] | None = None

    @field_validator("measurements", mode="before")
    @classmethod
    def bounded_results(cls, value):
        return _sequence(value, 1024)

    @field_validator("created_at", "updated_at", "deadline_at", "finished_at", mode="before")
    @classmethod
    def aware_times(cls, value):
        return None if value is None else ScanResponse.supplied_timestamp(value)

    @field_serializer("created_at", "updated_at", "deadline_at", "finished_at", when_used="json")
    def utc_times(self, value):
        return None if value is None else value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    @model_validator(mode="after")
    def truthful_state(self):
        keys = [item.unit_key() for item in self.measurements]
        if (len(keys) != len(set(keys)) or not set(keys) <= set(self.plan.unit_keys())
                or any(item.provenance != self.plan.provenance for item in self.measurements)
                or self.progress.completed_units != len(keys) or self.progress.total_units != len(self.plan.unit_keys())):
            raise ValueError("Progress and measurements must match the immutable plan.")
        terminal = self.status in TERMINAL_JOB_STATES
        if terminal != (self.finished_at is not None) or self.updated_at < self.created_at or self.deadline_at <= self.created_at:
            raise ValueError("Job timestamps and state are inconsistent.")
        if (self.status == "complete") != (self.result is not None):
            raise ValueError("Only persisted complete jobs have a terminal summary.")
        if self.status == "complete" and (len(keys) != self.progress.total_units or self.result.provenance != self.plan.provenance):
            raise ValueError("Completion requires all planned work.")
        if self.result is not None:
            statuses = {item.evaluation_status for item in self.measurements}
            expected = "failed" if "failed" in statuses else "passed" if statuses == {"passed"} else "inconclusive"
            if self.result.evaluation_status != expected:
                raise ValueError("Summary quality must reflect the supplied evaluations.")
            metrics = self.result.metrics
            if metrics is not None:
                if (metrics.provenance != self.plan.provenance or metrics.planned_units != self.progress.total_units
                        or metrics.processed_units != len(keys) or metrics.planned_cases != len(self.plan.case_ids)
                        or metrics.valid_recorded_outputs != sum(item.output_available is True for item in self.measurements)
                        or metrics.evaluated_units != sum(item.evaluation is not None and bool(item.evaluation.checks_ran) for item in self.measurements)):
                    raise ValueError("Metric coverage must match persisted units.")
                for state in ("passed", "failed", "skipped", "inconclusive", "not_run"):
                    actual = sum(("not_run" if item.evaluation_status == "unavailable" else item.evaluation_status) == state for item in self.measurements)
                    if getattr(metrics, state) != actual:
                        raise ValueError("Metric evaluation counts must match persisted units.")
        if self.status in ("queued", "running", "cancelling", "complete", "cancelled") and self.error is not None:
            raise ValueError("This state cannot carry a terminal failure.")
        if self.status in ("error", "interrupted") and self.error is None:
            raise ValueError("Failed execution requires controlled error information.")
        if self.status == "queued" and keys:
            raise ValueError("Queued jobs cannot claim completed work.")
        return self


class JobAccepted(APIModel):
    schema_version: Literal["cascaderouter.benchmark.v1"] = JOB_SCHEMA_VERSION
    run_id: RunId
    status: JobState
    provenance: BenchmarkProvenance
    status_url: Annotated[str, Field(pattern=r"^/api/runs/run_[0-9a-f]{32}$")]


class LocalBenchmarkCase(APIModel):
    identifier: Identifier
    input_text: Annotated[str, Field(min_length=1, max_length=8192, repr=False)]
    expected_output: Annotated[str, Field(max_length=8192)] | None = Field(default=None, repr=False)
    skip_reason: Literal["operator_excluded"] | None = None


class BenchmarkCaseSet(APIModel):
    identifier: Identifier
    version: Identifier
    provenance: Literal["local", "test"] | None = None
    validation_version: Literal["offline.v1"] | None = None
    content_digest: Digest | None = None
    cases: tuple[LocalBenchmarkCase, ...] = Field(min_length=1, max_length=64)

    @field_validator("cases", mode="before")
    @classmethod
    def bounded_cases(cls, value):
        return _sequence(value, 64)

    @model_validator(mode="after")
    def pinned_version(self):
        if self.content_digest is not None and content_digest(self, exclude={"content_digest"}) != self.content_digest:
            raise ValueError("Case-set content does not match its version digest.")
        return self


class EvaluationProfile(APIModel):
    identifier: Identifier
    version: Identifier
    criteria_id: Identifier
    mechanism: Literal["exact", "json", "json_schema"] | None = None
    validation_schema_json: Annotated[str, Field(max_length=16384)] | None = Field(default=None, repr=False)
    content_digest: Digest | None = None

    @model_validator(mode="after")
    def pinned_version(self):
        if self.content_digest is not None and content_digest(self, exclude={"content_digest"}) != self.content_digest:
            raise ValueError("Profile content does not match its version digest.")
        return self


class BenchmarkRegistryDocument(APIModel):
    schema_version: Literal["cascaderouter.registry.v1"] = "cascaderouter.registry.v1"
    origin: Literal["local", "test"]
    approved: Literal[True]
    case_sets: tuple[BenchmarkCaseSet, ...] = Field(min_length=1, max_length=16, repr=False)
    evaluation_profiles: tuple[EvaluationProfile, ...] = Field(min_length=1, max_length=16)
    models: tuple[ModelVersion, ...] = Field(min_length=2, max_length=32)

    @field_validator("approved", mode="before")
    @classmethod
    def explicit_approval(cls, value):
        if type(value) is not bool or value is not True:
            raise ValueError("Approval must be explicitly true.")
        return value

    @field_validator("case_sets", "evaluation_profiles", "models", mode="before")
    @classmethod
    def bounded_registry(cls, value, info):
        return _sequence(value, 32 if info.field_name == "models" else 16)

    @model_validator(mode="after")
    def unique_identifiers(self):
        collections = (self.case_sets, self.evaluation_profiles, self.models, *(item.cases for item in self.case_sets))
        if any(len({item.identifier for item in items}) != len(items) for items in collections):
            raise ValueError("Registry identifiers must be unique.")
        return self


class RecordedAnalysisResults(APIModel):
    analysis_id: AnalysisId
    analysis_digest: Digest
    registry_digest: Digest
    case_set: VersionedReference
    evaluation_profile: VersionedReference
    measurements: tuple[BenchmarkMeasurement, ...] = Field(min_length=1, max_length=1024)

    @field_validator("measurements", mode="before")
    @classmethod
    def bounded_measurements(cls, value):
        return _sequence(value, 1024)

    @model_validator(mode="after")
    def unique_measurements(self):
        keys = [item.unit_key() for item in self.measurements]
        if len(keys) != len(set(keys)):
            raise ValueError("Recorded unit identities must be unique.")
        return self


class RecordingDocument(APIModel):
    schema_version: Literal["cascaderouter.recordings.v1"] = "cascaderouter.recordings.v1"
    provenance: BenchmarkProvenance
    approved: Literal[True]
    source_id: Identifier
    recorded_at: datetime
    recordings: tuple[RecordedAnalysisResults, ...] = Field(min_length=1, max_length=16)

    _approval = field_validator("approved", mode="before")(BenchmarkRegistryDocument.explicit_approval)

    @field_validator("recorded_at", mode="before")
    @classmethod
    def aware_recording(cls, value):
        return ScanResponse.supplied_timestamp(value)

    @field_serializer("recorded_at", when_used="json")
    def recording_time(self, value):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    @field_validator("recordings", mode="before")
    @classmethod
    def bounded_recordings(cls, value):
        return _sequence(value, 16)

    @model_validator(mode="after")
    def recording_provenance(self):
        if len({item.analysis_id for item in self.recordings}) != len(self.recordings):
            raise ValueError("Recording analyses must be distinct.")
        if any(item.provenance != self.provenance for record in self.recordings for item in record.measurements):
            raise ValueError("Record provenance cannot be relabelled.")
        return self


def content_digest(model: APIModel, *, exclude: set[str] | None = None) -> str:
    """Canonical structured-content identity; never a source-code fingerprint."""
    data = model.model_dump(mode="json", exclude=exclude or set())
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


EvaluationStatus = Literal["passed", "failed", "skipped", "inconclusive", "not_run"]
EvaluationReason = Literal[
    "matched", "mismatch", "output_unavailable", "ground_truth_unavailable", "operator_excluded",
    "invalid_json", "schema_mismatch", "profile_unavailable", "invalid_expected_output", "resource_limit",
]


class CaseEvaluation(APIModel):
    status: EvaluationStatus
    reason: EvaluationReason
    checks_ran: tuple[Literal["exact", "json", "json_schema"], ...] = Field(default=(), max_length=3)
    validation_status: Literal["passed", "failed", "not_run"]

    @field_validator("checks_ran", mode="before")
    @classmethod
    def checks(cls, value):
        return _sequence(value, 3)

    @model_validator(mode="after")
    def actual_checks(self):
        if len(self.checks_ran) != len(set(self.checks_ran)):
            raise ValueError("Checks must be distinct.")
        if self.status in ("passed", "failed") and not self.checks_ran:
            raise ValueError("Decisive evaluation requires actual checks.")
        if self.status in ("not_run", "skipped") and self.checks_ran:
            raise ValueError("Unrun/excluded cases have no checks.")
        if self.status == "passed" and (self.reason != "matched" or self.validation_status != "passed"):
            raise ValueError("A pass requires matching evidence.")
        return self


def _decimal_value(value):
    if type(value) is str and re.fullmatch(r"(?:0|[1-9][0-9]{0,23})(?:\.[0-9]{1,18})?", value):
        return Decimal(value)
    if type(value) is Decimal and value.is_finite() and not value.is_signed() and value.adjusted() <= 23 and value.as_tuple().exponent >= -18:
        return value
    raise ValueError("Financial values require bounded nonnegative decimal strings.")


class PinnedPricing(APIModel):
    identifier: Identifier
    version: Identifier
    model_id: ModelIdentifier
    provenance: BenchmarkProvenance
    source_id: Identifier
    effective_at: datetime
    currency: Literal["USD"] = "USD"
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    digest: Digest

    _prices = field_validator("input_usd_per_million", "output_usd_per_million", mode="before")(_decimal_value)
    _model = field_validator("model_id")(LLMNode.safe_model_identifier)

    @field_validator("effective_at", mode="before")
    @classmethod
    def aware_price(cls, value):
        return ScanResponse.supplied_timestamp(value)

    @field_serializer("effective_at", when_used="json")
    def price_time(self, value):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    @field_serializer("input_usd_per_million", "output_usd_per_million", when_used="json")
    def prices(self, value):
        return format(value, "f")

    @model_validator(mode="after")
    def pinned(self):
        if any(rate > Decimal("100000000") or rate.as_tuple().exponent < -12 for rate in (self.input_usd_per_million, self.output_usd_per_million)):
            raise ValueError("Pricing exceeds the arithmetic budget.")
        if content_digest(self, exclude={"digest"}) != self.digest:
            raise ValueError("Pricing content does not match its pinned identity.")
        return self


class CostCalculation(APIModel):
    availability: Literal["available", "unavailable"]
    amount_usd: Decimal | None = None
    reason: Literal["missing_usage", "missing_pricing", "pricing_not_effective"] | None = None
    pricing_reference: VersionedReference | None = None
    pricing_digest: Digest | None = None

    @field_validator("amount_usd", mode="before")
    @classmethod
    def decimal_amount(cls, value):
        return None if value is None else _decimal_value(value)

    @field_serializer("amount_usd", when_used="json")
    def amount(self, value):
        return None if value is None else format(value, "f")

    @model_validator(mode="after")
    def honest_cost(self):
        if self.availability == "available":
            if self.amount_usd is None or self.reason is not None or self.pricing_reference is None or self.pricing_digest is None:
                raise ValueError("Calculated cost requires usage and pinned pricing evidence.")
        elif self.amount_usd is not None or self.reason is None or self.pricing_reference is not None or self.pricing_digest is not None:
            raise ValueError("Unavailable cost must remain null with a controlled reason.")
        return self


class RecordingEvidence(APIModel):
    source_id: Identifier
    captured_at: datetime
    input_tokens: Count | None = None
    output_tokens: Count | None = None
    latency_ms: Annotated[float, Field(ge=0, le=86400000, allow_inf_nan=False)] | None = None
    streaming: bool = False
    ttft_ms: Annotated[float, Field(ge=0, le=86400000, allow_inf_nan=False)] | None = None
    pricing_reference: VersionedReference | None = None

    @field_validator("captured_at", mode="before")
    @classmethod
    def capture_time(cls, value):
        return ScanResponse.supplied_timestamp(value)

    @field_serializer("captured_at", when_used="json")
    def capture_json(self, value):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    @model_validator(mode="after")
    def streaming_evidence(self):
        if self.ttft_ms is not None and (not self.streaming or (self.latency_ms is not None and self.ttft_ms > self.latency_ms)):
            raise ValueError("TTFT requires actual, consistent streaming evidence.")
        return self


class OfflineRecordedUnit(APIModel):
    recording_id: Identifier
    node_id: NodeId
    model_id: ModelIdentifier | None
    case_id: Identifier
    input_digest: Digest
    captured_output: Annotated[str, Field(max_length=8192)] | None = Field(default=None, repr=False)
    output_digest: Digest | None = None
    evidence: RecordingEvidence
    digest: Digest

    _model = field_validator("model_id")(LLMNode.safe_model_identifier)

    @model_validator(mode="after")
    def integrity(self):
        if self.captured_output is None:
            if self.output_digest is not None:
                raise ValueError("Missing output cannot claim an output digest.")
        else:
            try:
                encoded = self.captured_output.encode("utf-8")
            except UnicodeError:
                raise ValueError("Output encoding is invalid.") from None
            if len(encoded) > 16384 or hashlib.sha256(encoded).hexdigest() != self.output_digest:
                raise ValueError("Output does not match its bounded content digest.")
        if content_digest(self, exclude={"digest"}) != self.digest:
            raise ValueError("Recording content changed.")
        return self

    def unit_key(self):
        return self.node_id, self.model_id, self.case_id


class OfflineRecordedAnalysis(APIModel):
    analysis_id: AnalysisId
    analysis_digest: Digest
    registry_digest: Digest
    case_set: VersionedReference
    evaluation_profile: VersionedReference
    records: tuple[OfflineRecordedUnit, ...] = Field(min_length=1, max_length=1024, repr=False)

    @field_validator("records", mode="before")
    @classmethod
    def bounded_records(cls, value):
        return _sequence(value, 1024)

    @model_validator(mode="after")
    def unique_units(self):
        keys = [item.unit_key() for item in self.records]
        if len(keys) != len(set(keys)):
            raise ValueError("Recorded unit associations must be unique.")
        return self


class OfflineRecordingDocument(APIModel):
    schema_version: Literal["cascaderouter.offline-recordings.v1"] = "cascaderouter.offline-recordings.v1"
    provenance: BenchmarkProvenance
    source_id: Identifier
    recorded_at: datetime
    pricing_records: tuple[PinnedPricing, ...] = Field(default=(), max_length=32)
    recordings: tuple[OfflineRecordedAnalysis, ...] = Field(min_length=1, max_length=16, repr=False)

    _time = field_validator("recorded_at", mode="before")(ScanResponse.supplied_timestamp)

    @field_serializer("recorded_at", when_used="json")
    def document_time(self, value):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    @field_validator("recordings", "pricing_records", mode="before")
    @classmethod
    def bounds(cls, value, info):
        return _sequence(value, 16 if info.field_name == "recordings" else 32)

    @model_validator(mode="after")
    def references(self):
        records = [unit for analysis in self.recordings for unit in analysis.records]
        prices = {(item.identifier, item.version): item for item in self.pricing_records}
        if (len(records) > 1024 or len({item.recording_id for item in records}) != len(records)
                or len(prices) != len(self.pricing_records)
                or len({item.analysis_id for item in self.recordings}) != len(self.recordings)
                or any(item.provenance != self.provenance for item in self.pricing_records)):
            raise ValueError("Recording identifiers, versions or provenance are inconsistent.")
        for record in records:
            ref = record.evidence.pricing_reference
            if ref is not None and ((ref.identifier, ref.version) not in prices or prices[ref.identifier, ref.version].model_id != record.model_id):
                raise ValueError("A pricing reference is unknown or belongs to another model.")
        return self


class AssetApproval(APIModel):
    asset_id: Identifier
    root_index: Annotated[int, Field(ge=0, le=15)]
    relative_path: Annotated[str, Field(min_length=1, max_length=4096)]
    kind: Literal["registry", "offline_recordings"]
    provenance: Literal["local", "recorded", "test"]
    digest: Digest

    _path = field_validator("relative_path")(_relative_path)


class BenchmarkApprovalManifest(APIModel):
    schema_version: Literal["cascaderouter.approvals.v1"] = "cascaderouter.approvals.v1"
    approved_by: Identifier
    approved_at: datetime
    assets: tuple[AssetApproval, ...] = Field(min_length=1, max_length=32)

    _time = field_validator("approved_at", mode="before")(ScanResponse.supplied_timestamp)

    @field_serializer("approved_at", when_used="json")
    def approval_time(self, value):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    @field_validator("assets", mode="before")
    @classmethod
    def bounded_assets(cls, value):
        return _sequence(value, 32)

    @model_validator(mode="after")
    def unique_assets(self):
        if len({item.asset_id for item in self.assets}) != len(self.assets) or len({(item.root_index, item.relative_path) for item in self.assets}) != len(self.assets):
            raise ValueError("Approval entries must be unique.")
        return self


class MetricPopulation(APIModel):
    availability: Literal["available", "unavailable"]
    unit: Literal["ms", "tokens", "USD"]
    sample_count: Annotated[int, Field(ge=0, le=1024)]
    minimum: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    maximum: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    mean: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    total_tokens: Count | None = None
    total_usd: Decimal | None = None
    reason: Literal["empty_population", "arithmetic_limit"] | None = None

    @field_validator("total_usd", mode="before")
    @classmethod
    def total_money(cls, value):
        return None if value is None else _decimal_value(value)

    @field_serializer("total_usd", when_used="json")
    def total_json(self, value):
        return None if value is None else format(value, "f")

    @model_validator(mode="after")
    def population(self):
        values = (self.minimum, self.maximum, self.mean, self.total_tokens, self.total_usd)
        if self.availability == "unavailable":
            if any(value is not None for value in values) or self.reason is None:
                raise ValueError("Unavailable statistics have null values and a reason.")
            if (self.reason == "empty_population") != (self.sample_count == 0):
                raise ValueError("An empty population must have no samples.")
        elif self.sample_count == 0 or self.reason is not None:
            raise ValueError("Available statistics require actual samples.")
        elif self.unit == "ms" and (any(value is None for value in values[:3]) or any(value is not None for value in values[3:])):
            raise ValueError("Latency statistics require a measured population.")
        elif self.unit == "tokens" and (self.total_tokens is None or any(value is not None for value in (*values[:3], self.total_usd))):
            raise ValueError("Token totals require actual counts.")
        elif self.unit == "USD" and (self.total_usd is None or any(value is not None for value in values[:4])):
            raise ValueError("Cost totals require decimal amounts.")
        return self


class OfflineMetrics(APIModel):
    provenance: BenchmarkProvenance
    planned_cases: Count
    planned_units: Count
    processed_units: Count
    valid_recorded_outputs: Count
    evaluated_units: Count
    passed: Count
    failed: Count
    skipped: Count
    inconclusive: Count
    not_run: Count
    processing_complete: bool
    evaluation_complete: bool
    latency_ms: MetricPopulation
    ttft_ms: MetricPopulation
    input_tokens: MetricPopulation
    output_tokens: MetricPopulation
    cost_usd: MetricPopulation

    @model_validator(mode="after")
    def counts(self):
        if (self.processed_units > self.planned_units or self.valid_recorded_outputs > self.processed_units
                or self.evaluated_units > self.processed_units
                or self.passed + self.failed + self.skipped + self.inconclusive + self.not_run != self.processed_units
                or self.processing_complete != (self.processed_units == self.planned_units)
                or self.evaluation_complete != (self.passed + self.failed == self.planned_units)):
            raise ValueError("Metric coverage and counts must agree.")
        for name, unit in (("latency_ms", "ms"), ("ttft_ms", "ms"), ("input_tokens", "tokens"), ("output_tokens", "tokens"), ("cost_usd", "USD")):
            if getattr(self, name).unit != unit or getattr(self, name).sample_count > self.processed_units:
                raise ValueError("Metric populations must use the declared units and coverage.")
        return self


class BenchmarkVersionRegistration(APIModel):
    kind: Literal["case_set", "profile", "pricing", "recording"]
    identifier: Identifier
    version: Identifier
    digest: Digest
    provenance: Literal["local", "test", "recorded"]


BenchmarkMeasurement.model_rebuild()
BenchmarkSummary.model_rebuild()
JobResponse.model_rebuild()


# Offline optimization consumes the existing immutable plan and measurements.
# No caller-submitted metrics, model choices, paths or executable rules are accepted.
OptimizationReason = Literal[
    "lowest_recorded_cost", "baseline_lowest_cost", "no_eligible_alternative",
    "baseline_ineligible", "candidate_evidence_incomplete", "quality_failed",
    "quality_unavailable", "cost_unavailable", "threshold_not_met",
    "evidence_unavailable", "test_evidence", "approval_unavailable",
    "threshold_unconfigured", "benchmark_incomplete",
]


def optimization_threshold(value):
    value = _decimal_value(value)
    if value > 1 or value.as_tuple().exponent < -6:
        raise ValueError("Quality thresholds require a decimal from zero to one with at most six fractional digits.")
    return value


class OptimizationRequest(APIModel):
    analysis_id: AnalysisId
    run_id: RunId
    case_set: VersionedReference
    evaluation_profile: VersionedReference


class OptimizationCandidate(APIModel):
    model: ModelVersion
    provenance: BenchmarkProvenance
    eligibility: Literal["eligible", "rejected", "insufficient"]
    reasons: tuple[OptimizationReason, ...] = Field(max_length=4)
    planned_cases: Annotated[int, Field(ge=1, le=64)]
    passed_cases: Annotated[int, Field(ge=0, le=64)]
    failed_cases: Annotated[int, Field(ge=0, le=64)]
    unresolved_cases: Annotated[int, Field(ge=0, le=64)]
    quality_pass_rate: Decimal | None = None
    cost_total_usd: Decimal | None = None
    latency_ms: MetricPopulation
    measurement_digest: Digest | None = None

    @field_validator("reasons", mode="before")
    @classmethod
    def bounded_reasons(cls, value):
        return _sequence(value, 4)

    @field_validator("quality_pass_rate", mode="before")
    @classmethod
    def rate(cls, value):
        return None if value is None else optimization_threshold(value)

    @field_validator("cost_total_usd", mode="before")
    @classmethod
    def cost(cls, value):
        return None if value is None else _decimal_value(value)

    @field_serializer("quality_pass_rate", "cost_total_usd", when_used="json")
    def decimals(self, value):
        return None if value is None else format(value, "f")

    @model_validator(mode="after")
    def consistent_candidate(self):
        if (self.passed_cases + self.failed_cases + self.unresolved_cases != self.planned_cases
                or self.latency_ms.unit != "ms" or self.latency_ms.sample_count > self.planned_cases
                or len(self.reasons) != len(set(self.reasons))):
            raise ValueError("Candidate coverage must agree with its evidence.")
        if (self.quality_pass_rate is not None) != (self.unresolved_cases == 0):
            raise ValueError("Quality requires decisive evidence for every planned case.")
        if self.quality_pass_rate is not None:
            with localcontext() as context:
                context.prec = 80
                rate = (Decimal(self.passed_cases) / self.planned_cases).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
            if self.quality_pass_rate != rate:
                raise ValueError("The observed pass rate must match actual case counts.")
        expected = "rejected" if self.failed_cases else "insufficient" if self.unresolved_cases or self.cost_total_usd is None else "eligible"
        if self.eligibility != expected:
            raise ValueError("Eligibility must follow actual quality and cost coverage.")
        required_reasons = {name for name, condition in (("quality_failed", self.failed_cases),
                            ("quality_unavailable", self.unresolved_cases), ("cost_unavailable", self.cost_total_usd is None)) if condition}
        if set(self.reasons) - {"threshold_not_met"} != required_reasons:
            raise ValueError("Candidate reasons must describe actual evidence gaps.")
        if self.eligibility == "eligible":
            if (self.reasons or self.passed_cases != self.planned_cases or self.quality_pass_rate != 1
                    or self.cost_total_usd is None or self.measurement_digest is None):
                raise ValueError("Eligibility requires complete passing, costed evidence.")
        elif not self.reasons:
            raise ValueError("Exclusion requires a controlled reason.")
        return self


class RoutingDecision(APIModel):
    analysis_id: AnalysisId
    node_id: NodeId
    provenance: BenchmarkProvenance
    status: Literal["recommended", "baseline_retained", "inconclusive", "unavailable"]
    reason: OptimizationReason
    baseline_model_id: ModelIdentifier
    selected_model_id: ModelIdentifier | None = None
    differs_from_baseline: bool = False
    quality_threshold: Decimal | None
    candidates: tuple[OptimizationCandidate, ...] = Field(max_length=9)
    recorded_savings_usd: Decimal | None = None

    _model_ids = field_validator("baseline_model_id", "selected_model_id")(LLMNode.safe_model_identifier)

    @field_validator("candidates", mode="before")
    @classmethod
    def bounded_candidates(cls, value):
        return _sequence(value, 9)

    @field_validator("quality_threshold", mode="before")
    @classmethod
    def threshold(cls, value):
        return None if value is None else optimization_threshold(value)

    @field_validator("recorded_savings_usd", mode="before")
    @classmethod
    def money(cls, value):
        return None if value is None else _decimal_value(value)

    @field_serializer("quality_threshold", "recorded_savings_usd", when_used="json")
    def decimals(self, value):
        return None if value is None else format(value, "f")

    @model_validator(mode="after")
    def truthful_selection(self):
        models = {item.model.identifier: item for item in self.candidates}
        if len(models) != len(self.candidates) or any(item.provenance != self.provenance for item in self.candidates):
            raise ValueError("Candidate identities and provenance must be distinct and consistent.")
        for item in self.candidates:
            if self.quality_threshold is None or (("threshold_not_met" in item.reasons) != (
                    item.quality_pass_rate is not None and item.quality_pass_rate < self.quality_threshold)):
                raise ValueError("Threshold exclusions must follow the configured threshold.")
        decisive = self.status in ("recommended", "baseline_retained")
        if not decisive:
            if self.selected_model_id is not None or self.differs_from_baseline or self.recorded_savings_usd is not None:
                raise ValueError("Unresolved decisions cannot assert a model selection or savings.")
        else:
            baseline, selected = models.get(self.baseline_model_id), models.get(self.selected_model_id)
            if (self.quality_threshold is None or baseline is None or selected is None
                    or baseline.eligibility != "eligible" or selected.eligibility != "eligible"
                    or any(item.eligibility == "insufficient" for item in self.candidates)):
                raise ValueError("Decisions require an eligible baseline and complete comparable candidates.")
            changed = self.selected_model_id != self.baseline_model_id
            if self.differs_from_baseline != changed or (self.status == "recommended") != changed:
                raise ValueError("Decision status must describe the actual selection.")
            if (changed and self.reason != "lowest_recorded_cost") or (not changed and self.reason not in ("baseline_lowest_cost", "no_eligible_alternative")):
                raise ValueError("Decision reasons must describe the actual selection.")
            with localcontext() as context:
                context.prec = 80
                saving = baseline.cost_total_usd - selected.cost_total_usd
            if saving < 0 or self.recorded_savings_usd != saving or (changed and saving == 0):
                raise ValueError("Savings require an established lower recorded cost.")
            if any(item.eligibility == "eligible" and item.cost_total_usd < selected.cost_total_usd for item in self.candidates):
                raise ValueError("Selected model must minimize eligible recorded cost.")
            expected_model = min((item for item in self.candidates if item.eligibility == "eligible"),
                                 key=lambda item: (item.cost_total_usd, item.model != baseline.model, item.model.identifier))
            if selected != expected_model:
                raise ValueError("Tied minimum costs must follow the deterministic tie rule.")
        return self


class OptimizationResult(APIModel):
    schema_version: Literal["cascaderouter.optimization.v1"] = "cascaderouter.optimization.v1"
    objective_version: Literal["all-checks-then-cost.v1"] = "all-checks-then-cost.v1"
    configuration_version: Literal["zero-cost.optimizer.v1"] = "zero-cost.optimizer.v1"
    configuration_digest: Digest
    run_id: RunId
    benchmark_digest: Digest
    plan: BenchmarkPlan
    approval_manifest_digest: Digest | None
    recording_dataset_digest: Digest | None
    quality_threshold: Decimal | None
    provenance: BenchmarkProvenance
    status: Literal["complete", "inconclusive", "unavailable"]
    decisions: tuple[RoutingDecision, ...] = Field(min_length=1, max_length=16)
    nodes_considered: Annotated[int, Field(ge=1, le=16)]
    nodes_eligible: Annotated[int, Field(ge=0, le=16)]
    nodes_recommended: Annotated[int, Field(ge=0, le=16)]
    nodes_retained: Annotated[int, Field(ge=0, le=16)]
    nodes_inconclusive: Annotated[int, Field(ge=0, le=16)]
    nodes_unavailable: Annotated[int, Field(ge=0, le=16)]
    decisions_complete: bool
    diagnostics: tuple[OptimizationReason, ...] = Field(default=(), max_length=4)

    @field_validator("decisions", "diagnostics", mode="before")
    @classmethod
    def bounds(cls, value, info):
        return _sequence(value, 16 if info.field_name == "decisions" else 4)

    _threshold = field_validator("quality_threshold", mode="before")(RoutingDecision.threshold)

    @field_serializer("quality_threshold", when_used="json")
    def decimal_threshold(self, value):
        return None if value is None else format(value, "f")

    @model_validator(mode="after")
    def consistent_result(self):
        if (self.provenance != self.plan.provenance or self.nodes_considered != len(self.decisions)
                or tuple(item.node_id for item in self.decisions) != tuple(sorted(self.plan.node_ids))
                or any(item.analysis_id != self.plan.analysis_id or item.provenance != self.provenance
                       or item.baseline_model_id != self.plan.models[0].identifier or item.quality_threshold != self.quality_threshold
                       for item in self.decisions)):
            raise ValueError("Decisions must retain the exact plan and provenance.")
        for name, state in (("nodes_recommended", "recommended"), ("nodes_retained", "baseline_retained"),
                            ("nodes_inconclusive", "inconclusive"), ("nodes_unavailable", "unavailable")):
            if getattr(self, name) != sum(item.status == state for item in self.decisions):
                raise ValueError("Decision counts must agree.")
        if self.nodes_eligible != sum(any(candidate.eligibility == "eligible" for candidate in item.candidates) for item in self.decisions):
            raise ValueError("Eligible-node count must reflect validated candidates.")
        complete = self.nodes_recommended + self.nodes_retained == self.nodes_considered
        expected = "complete" if complete else "unavailable" if self.nodes_unavailable == self.nodes_considered else "inconclusive"
        if self.decisions_complete != complete or self.status != expected:
            raise ValueError("Incomplete decisions cannot claim completion.")
        for decision in self.decisions:
            if decision.candidates and tuple(item.model for item in decision.candidates) != self.plan.models:
                raise ValueError("Candidates must preserve exact planned model versions.")
            if any(item.planned_cases != len(self.plan.case_ids) for item in decision.candidates):
                raise ValueError("Candidate coverage must use the exact planned case population.")
        if self.nodes_recommended + self.nodes_retained and self.provenance == "recorded" and (
                self.approval_manifest_digest is None or self.recording_dataset_digest is None):
            raise ValueError("Recorded decisions require retained approval and dataset identities.")
        return self


class RoutingPolicyArtifact(APIModel):
    status: Literal["available", "partial", "unavailable"]
    reason: Literal["no_eligible_routes", "serializer_unavailable", "serialization_failed"] | None = None
    route_count: Annotated[int, Field(ge=0, le=16)]
    yaml_content: Annotated[str, Field(max_length=524288)] | None = None
    digest: Digest | None = None

    @model_validator(mode="after")
    def consistent_artifact(self):
        if self.status == "unavailable":
            if self.reason is None or self.route_count != 0 or self.yaml_content is not None or self.digest is not None:
                raise ValueError("Unavailable policy cannot claim routes or bytes.")
        elif (self.reason is not None or self.route_count == 0 or self.yaml_content is None
              or len(self.yaml_content.encode("utf-8")) > 524288
              or hashlib.sha256(self.yaml_content.encode("utf-8")).hexdigest() != self.digest):
            raise ValueError("Policy bytes require an integrity digest and actual routes.")
        return self


class OptimizationResponse(APIModel):
    result: OptimizationResult
    policy: RoutingPolicyArtifact

    @model_validator(mode="after")
    def consistent_response(self):
        routes = self.result.nodes_recommended + self.result.nodes_retained
        if self.policy.status != "unavailable" and (self.policy.route_count != routes
                or (self.policy.status == "available") != self.result.decisions_complete):
            raise ValueError("Policy completeness must match the decisions.")
        return self
