# Backend scan contract v1

## Implementation status and authority

`backend/schemas.py` implements the first-party Pydantic v2 contract identifier
`cascaderouter.scan.v1`. This is the Phase 4.1 contract for team review. The models,
configuration and unit tests exist; **no FastAPI application, routes, compiler
adapter, provider execution, job engine, optimizer or patch system exists yet**.

The earlier conceptual examples in `docs/architecture.md` and the existing
`frontend/src/types.ts` are not exact definitions of this contract. Frontend
alignment is a later coordinated change. Compiler dataclasses remain provisional
internal interfaces, unchanged by this phase.

## Validation and serialization

Models use strict types, reject unexpected fields, hide input values in the text
of Pydantic validation errors and freeze their fields. Collections are immutable
tuples internally. JSON arrays supplied as Python lists are explicitly normalized
to tuples; JSON output uses arrays, including ordered two-element edge arrays.
Strings/numbers/booleans are not coerced to one another.

The canonical wire methods are `model_dump(mode="json")` and `model_dump_json()`
with their default exclusion options. Every declared optional field is present
as `null` when unavailable, regardless of whether its constructor argument was
omitted or explicitly null. Empty collections serialize as `[]`. Fields absent
from the contract, including snippets and docstrings, are absent entirely.
Do not use `exclude_none`, `exclude_unset` or `exclude_defaults` for API responses.
Do not use validation-bypassing construction or unvalidated model-copy updates
with untrusted inputs.

Ordering is preserved, never interpreted as runtime execution order. Serialization
of a fixed validated record is deterministic. Timestamps and analysis identifiers
are required caller-supplied transport metadata, with no clock/random defaults.
Aware datetimes or RFC3339 strings are accepted and normalized to UTC with six
fractional digits and a `Z` suffix. Naive datetimes are rejected. Future services
must create genuine metadata once and retain it with the analysis; schema
validation cannot prove provenance or establish that an operation actually ran.

## Planned `POST /api/scan`

The endpoint is not implemented. Its request model is `ScanRequest`:

```json
{"repository_path": "approved-empty-repository"}
```

The only accepted field is a nonblank string of at most 4096 characters without
control characters. Absolute and relative path syntax is accepted by the model;
this acceptance is **not filesystem authorization**. There are no source-code,
command, credential, executable-payload or arbitrary-options fields. A path is
data and must never be interpolated into a shell command.

Illustrative response for an authorized empty repository (the transport metadata
below is an example, not an executed operation):

```json
{
  "schema_version": "cascaderouter.scan.v1",
  "analysis_id": "analysis_00000000000000000000000000000000",
  "timestamp": "2026-10-28T12:00:00.000000Z",
  "repository_path": "approved-empty-repository",
  "nodes": [],
  "graph_edges": [],
  "scanned_files_count": 0,
  "discovered_files_count": 0,
  "total_source_bytes_read": 0,
  "detected_framework": null,
  "data_source": "live",
  "scan_complete": true,
  "graph_complete": true,
  "complete": true,
  "scan_diagnostics": [],
  "graph_diagnostics": []
}
```

`analysis_id` uses `analysis_` plus 32 lowercase hexadecimal characters, supplied
by the future service. It identifies an analysis record; it is not a scanner
node ID, a source fingerprint, or proof of an atomic repository snapshot.

Counts are strict nonnegative integers no larger than JavaScript's exact integer
limit (`2**53 - 1`). Scanned files cannot exceed discovered files, and distinct
node source files cannot exceed scanned files. Reading an invalid file can consume
bytes without incrementing the successfully scanned-file count.

Public arrays are bounded: 20,000 nodes, 10,000 edges, 50,000 initial scanner
diagnostics and 1,000 graph diagnostics. Oversized results are rejected rather
than silently truncated. Future service/compiler options must respect these
response capacities or return a controlled error.

`detected_framework` is `"OpenAI SDK"` or null. A non-null label requires included
scanner-confirmed nodes. There is no default framework label and no inference of
an agent framework from an SDK call. Unknown frameworks remain null.

## Nodes and resolution metadata

`LLMNode` includes:

| Field | Meaning |
|---|---|
| `node_id` | Existing scanner ID: `llm_` plus 24 lowercase hex characters; copy verbatim |
| `file_path` | Canonical repository-relative POSIX path; no absolute path, backslash, traversal or control characters |
| `line_number` | Strict positive one-based source line |
| `column_number` | Strict nonnegative zero-based UTF-8 byte offset, not a character index |
| `call_signature` | Canonical supported OpenAI/AsyncOpenAI chat-completions signature |
| `current_model` | Safe literal model identifier, otherwise null |
| `function_name` | Optional qualified-name syntax prefix, capped by the scanner at 256 characters; null at module scope |
| `model_resolution`, `prompt_resolution`, `schema_resolution` | `missing`, `unresolved`, `literal` or `reference` |
| `model_reference`, `prompt_reference`, `schema_reference` | Primary syntax reference only for `reference` resolution; otherwise null |
| `model_references`, `prompt_references`, `schema_references` | Distinct bounded syntax references, at most 32 per collection |
| `limited_schema_summary` | Optional whitelisted response-format summary, never a full JSON Schema |

References are bounded Python names/attribute paths, not executable expressions.
A primary reference must occur in its corresponding collection. Missing/literal
metadata has no unresolved references; unresolved metadata may retain references
without asserting a primary resolved value.

Only literal model resolution permits a non-null `current_model`. Reference,
missing and unresolved model states require null. Safe literal export follows
the compiler's bounded identifier/recognizable-credential-prefix policy; it is
not a universal detector for every possible secret. The adapter must use actual
scanner results and must not evaluate references, invent fallback IDs, or recover
values from environment variables or application imports.

### Mapping from existing compiler metadata (adapter not implemented)

| Internal scanner value | Public value |
|---|---|
| Node identity, source location, signature, current model and function name | Same values |
| `model.kind/reference/references` | `model_resolution/reference/references` |
| `messages.kind/reference/references` | `prompt_resolution/reference/references` |
| `response_format.kind/reference/references` | `schema_resolution/reference/references` |
| `response_format.value.type` | `limited_schema_summary.format_type`, when present |
| `response_format.value.strict` | Summary `strict`, when present |
| `response_format.value.schema` | Summary `schema_shape`, preserving its `kind`, references, type and counts |

`schema_resolution` describes the response-format argument. An inner JSON-schema
shape has its own `kind`, preserving a missing schema, a direct schema reference
or an unresolved definition reference independently of the envelope.

The limited summary permits only format (`json_object`, `json_schema`, `text`),
JSON-schema strictness, inner resolution/reference metadata, an optional JSON type,
and property/required counts. It has no descriptions, property definitions,
examples, enums, defaults or prompt literals. `expected_schema` is deliberately
not a field; attempting to supply it is rejected. A future benchmark must obtain
an actual validation schema from an explicit approved case/profile source.

## Edges, evidence and coverage

`graph_edges` is an array of `[from_node_id, to_node_id]` pairs. Endpoints must
reference included nodes. Duplicate node IDs, duplicate pairs, self-edges and
unknown endpoints are rejected. IDs and ordering are never regenerated, filtered
or repaired by the model. The model does not infer edges or re-prove their evidence.

Edges represent the existing graph builder's statically supported data dependency,
not verified runtime reachability or execution order. Rich internal evidence,
ASTs, fingerprints, source options, raw bytes and model outputs have no public
response fields. They must not be placed in public diagnostics as a workaround.

`complete == (scan_complete and graph_complete)` is required; inconsistencies are
rejected. A component reporting omission diagnostics cannot claim completeness.
False component flags may exist without diagnostics; false is always conservative.
Completeness covers only the documented compiler subsets, not all Python behavior.

Initial diagnostics stay in `scan_diagnostics`; native graph and guarded-reread
diagnostics stay in `graph_diagnostics`. Both arrays have controlled code catalogs.
A future adapter maps a compiler diagnostic's code/location, not its arbitrary
message string. Scanner root `"."` location markers map to `location: null`;
ordinary relative directory paths can be retained without a line number.

`Diagnostic(code=...)` supplies a fixed safe message and warning/error level.
Wire round trips may include these fields only with their exact catalog values.
Unknown codes, custom messages, altered levels and extra exception fields are
rejected. New compiler codes require an explicit catalog review. Warning-level
omission diagnostics still mean incomplete coverage.

## Errors and data provenance

`ErrorResponse` is flat, for example:

```json
{
  "schema_version": "cascaderouter.scan.v1",
  "code": "repository_forbidden",
  "message": "The repository is outside the permitted policy.",
  "request_id": null
}
```

Optional genuine request identifiers use `req_` plus 32 lowercase hex characters.
The controlled error codes are `invalid_request`, `repository_forbidden`,
`repository_unavailable`, `not_found`, `source_conflict`, `request_too_large`,
`capacity_exceeded`, `capability_unavailable` and `internal_error`. Messages cannot
be populated from exceptions, provider responses, paths or input values.

`hide_input_in_errors` protects error text, but Pydantic's structured validation
errors can still retain inputs/context. A future HTTP exception handler must emit
`ErrorResponse`, not raw exception strings, stack traces or `ValidationError.errors()`.
No HTTP status mapping or handler is implemented in this phase.

`data_source` is required: `live`, `recorded` or `mock`. Live scan means actual
backend source analysis, not that a provider was contacted. Recorded means an
identified retained result; mock means explicitly synthetic fixtures. A service
must set provenance from the operation performed. Errors cannot switch silently
to mock results, and clients must not overwrite server provenance. A schema alone
cannot verify these operational facts.

No measurement model is introduced prematurely. Later measurement contracts must
use null for unavailable values, preserve actual/estimated provenance, and never
substitute zero or a passing quality score for missing evidence.

## Configuration and repository authorization

`BackendConfig` takes explicit keyword arguments only. It does not read host
environment variables, load dotenv, accept credential fields or contact providers.
Defaults bind to `127.0.0.1:8000`; only numeric loopback addresses are accepted.

There is no default permitted root. A future scan service must call
`require_repository_roots()` before enabling repository access; empty policy raises
a controlled `ConfigurationError`. This method returns configured policy and is
not a path authorizer.

At most 16 absolute local roots can be injected. Validation opens directory
metadata/handles without enumerating contents or reading files. Missing paths,
files, final symlinks/reparse points, UNC/device paths, whole filesystem roots and
duplicates are rejected. Roots are resolved and excluded from ordinary repr/dumps.
`safe_report()` reports limits, policy presence and root count without root paths.

| Setting | Default | Maximum |
|---|---:|---:|
| Request body bytes | 1 MiB | 16 MiB |
| Scan workers | 1 | 4 |
| Job workers | 2 | 8 |
| Queued jobs | 32 | 256 |
| Retained/active jobs | 128 | 2,048 |
| Concurrent provider requests | 4 | 16 |
| Requests per job | 64 | 1,024 |
| Output tokens per request | 1,024 | 8,192 |
| Provider response bytes | 1 MiB | 8 MiB |
| Scan timeout seconds | 30 | 120 |
| Provider timeout seconds | 30 | 120 |
| Job timeout seconds | 300 | 1,800 |
| Job retention seconds | 86,400 | 604,800 |

Numeric limits are strict positive integers. Queue/worker limits cannot exceed the
total job limit; provider timeout cannot exceed job timeout. Configuration validates
these values but does not implement admission, cancellation, deadlines or quotas.

Later services must enforce root containment and identity at time of use, including
ancestor substitutions, without trusting a one-time configuration/path check.
They must retain the existing scanner's no-follow/opened-handle protections and
the graph builder's required guarded reread/fingerprint verification. Request body
limits must be enforced before unbounded body parsing. Scanner budgets must not be
weakened. Provider secrets belong only in the future server-side provider phase.

## Dependency and CI status

The project retains pip and `requirements.txt`. Pydantic v2 plus the standard
library implements this foundation; no settings library or new lint stack was
added. Existing runtime/test dependency inputs are retained with upper bounds.
Future provider/API prerequisites remain listed but are not implemented services.

These ranges are **not a lock and do not establish reproducible installation**.
The available local interpreter is Python 3.14.3; no runnable Python 3.11 resolver
or suitable lock-generation tool was found. No packages/runtime were installed,
and no lock was created from an unrelated global environment. A clean Python 3.11
resolution, transitive hash lock, installation verification and platform checks
remain required before claiming reproducibility. The package index was not queried.

CI retains Python 3.11, installs the declared inputs once, checks dependency
consistency, and runs all compiler/unit tests with failure propagation and a fresh
temporary base. Plugin autoload is disabled because current tests are synchronous;
later asynchronous tests must explicitly enable their approved plugin. CI also
uses the existing frontend lock with `npm ci` and propagates build failures. The
existing Node 20 target is retained; the lock requires 20.19+ on that major.
There is no successful hosted-CI result implied by these configuration changes.

## Later endpoints (proposed, not implemented)

- `GET /api/health`: liveness/capabilities without provider requests.
- `POST /api/scan`: repository authorization, compiler orchestration and adapter.
- `POST /api/benchmark`: explicit cases/models and bounded job creation.
- `GET /api/runs/{run_id}`: actual job status and available results.
- `POST /api/runs/{run_id}/cancel`: controlled cancellation.
- `POST /api/optimize`: recommendations from actual eligible measurements.

Provider execution, job states, evaluation, persistence, runtime routing, patching
and regression execution require separate implementations and acceptance gates.
