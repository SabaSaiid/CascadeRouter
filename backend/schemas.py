"""First-party API contract v1, shared by routes, adapter and persistence.

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
    optimization_available: Literal[False] = False


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
    evaluation_status: Literal["passed", "failed", "inconclusive", "unavailable"]
    quality_score: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None

    _safe_id = field_validator("model_id")(LLMNode.safe_model_identifier)

    @model_validator(mode="after")
    def score_availability(self):
        if self.evaluation_status == "unavailable" and self.quality_score is not None:
            raise ValueError("Unavailable evaluation has no score.")
        return self

    def unit_key(self) -> tuple[str, str, str]:
        return self.node_id, self.model_id, self.case_id


class BenchmarkSummary(APIModel):
    provenance: BenchmarkProvenance
    evaluation_status: Literal["passed", "failed", "inconclusive"]


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


class BenchmarkCaseSet(APIModel):
    identifier: Identifier
    version: Identifier
    cases: tuple[LocalBenchmarkCase, ...] = Field(min_length=1, max_length=64)

    @field_validator("cases", mode="before")
    @classmethod
    def bounded_cases(cls, value):
        return _sequence(value, 64)


class EvaluationProfile(APIModel):
    identifier: Identifier
    version: Identifier
    criteria_id: Identifier


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
