# Backend scan contract v1

## Implementation status and authority

`backend/schemas.py` implements the first-party Pydantic v2 contract identifier
`cascaderouter.scan.v1`. This is the Phase 4.1 contract for team review. The models,
configuration and unit tests remain authoritative. Phase 4.2 adds the local
FastAPI factory, repository authorizer, compiler adapter and immutable SQLite
snapshots. Provider execution, job engines, optimization and patching are absent.

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

## Implemented `POST /api/scan`

Its request model is `ScanRequest`:

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
once by the scan service using UUID4. It identifies an analysis record; it is not a scanner
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

### Mapping from existing compiler metadata

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
The adapter maps a compiler diagnostic's code/location, not its arbitrary
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
errors can still retain inputs/context. The HTTP exception handlers emit
`ErrorResponse`, not raw exception strings, stack traces or `ValidationError.errors()`.
The HTTP status mapping is documented below.

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

There is no default permitted root. The scan service calls
`require_repository_roots()` before enabling repository access; empty policy raises
a controlled `ConfigurationError`. This method returns configured policy and is
not a path authorizer.

At most 16 absolute local roots can be injected. Validation opens directory
metadata/handles without enumerating contents or reading files. Missing paths,
files, final symlinks/reparse points, UNC/device paths, whole filesystem roots and
duplicates are rejected. Roots are resolved and excluded from ordinary repr/dumps.
`safe_report()` reports limits, policy presence and root count without root paths
or the storage directory.

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
these values. Scan workers, body size and scan deadlines are enforced by the
HTTP/services layer; provider/job limits remain reserved and inactive.

The authorizer enforces root containment and identity at time of use, including
ancestor substitutions. It reuses the scanner's directory guards and retains the
graph builder's guarded reread/fingerprint verification. Provider secrets belong
only in a future server-side provider phase.

## Local application, storage and HTTP boundaries (Phase 4.2)

`backend.main.create_app(settings=None)` accepts an explicit `BackendConfig`.
Its lifespan creates and closes the authorizer, SQLite service and bounded
executor. With no settings, health works and scans/retrieval return `503`.
Missing root policy, missing storage or incompatible storage never broaden access.

| Endpoint | Behavior |
|---|---|
| `GET /api/health` | Liveness and initialization capability flags, no provider calls or paths |
| `POST /api/scan` | Authorize, analyze once, validate, persist, then return `ScanResponse` |
| `GET /api/analyses/{analysis_id}` | Validate ID and retrieve the original immutable response under the current root policy |
| `GET /openapi.json` | Generated request, response and controlled error schemas |

Health reports initialization readiness, not a fresh database probe or available
worker capacity. Benchmark and optimization capabilities are always false.
Retrieval preserves the original timestamp, analysis ID and `data_source: live`:
it is the retained result of actual static analysis, not a new scan or mock. It
does not re-open old source files. A newly configured policy must still contain
the stored repository path; otherwise retrieval returns `403`.

Absolute repository requests must be under an explicit permitted root. Relative
requests resolve against the single permitted root; multiple roots require an
absolute request (`422` for ambiguous relative paths). `.` explicitly selects
that one configured root. Parent traversal, UNC/device paths, drive-relative
paths, final/ancestor symbolic links, junctions and reparse points are rejected.
Windows trailing-dot/space components and alternate-stream syntax are rejected
before filesystem access.
Missing/non-directory authorized children return `422`; changed root identities
return `409`. Neither the CWD nor a default home/workspace/drive grants access.
Authorization paths are limited to 64 components below their permitted root,
matching the scanner's default depth budget and bounding guard handle usage.

Windows directory handles use `FILE_LIST_DIRECTORY` and deny delete sharing
across both compiler passes. Zero-access metadata handles did not block renames
in the tested environment and were corrected. POSIX no-follow descriptors anchor
component lookup. A private scoped identity requirement also verifies the selected
repository before each compiler pass; root identity/containment is checked again
after analysis. Source files are never imported or executed. Ordinary compiler
omissions, including syntax errors or unsupported graph flow, produce truthful
`200` partial results. Detected stale source/fingerprint/call-site conflicts are
rejected with `409` before persistence. This remains a static subset, not an atomic
repository snapshot or a runtime graph.

| Status | Controlled code / meaning |
|---|---|
| `422` | `invalid_request`, or `repository_unavailable` for an authorized absent/invalid child |
| `403` | `repository_forbidden` |
| `404` | `not_found` |
| `409` | `source_conflict`, including duplicate analysis IDs and incompatible/stale results |
| `413` | `request_too_large` |
| `429` | `capacity_exceeded` |
| `503` | `capability_unavailable`, including deadline and storage availability failures |
| `500` | `internal_error`, with a fixed message |

Errors contain a genuine per-request `req_` UUID and the established flat
`ErrorResponse`. Validation inputs, paths, exception text and tracebacks are never
returned. Unexpected request failures log only a fixed sentence plus request ID.
Unknown routes and disallowed methods also use controlled error bodies (`404`/`405`).

Pure ASGI middleware counts actual body bytes before JSON parsing, including
chunked/no-length requests and falsely small lengths. Declared oversize is rejected
immediately. Duplicate/malformed lengths, length mismatches, simultaneous length
and transfer encoding, and unsupported content/transfer encodings are rejected.
Aggregate body admission is `min(8, floor(64 MiB / body_limit))`, at least one;
excess requests return `429`. Body receipt and worker wait share the configured
scan deadline. Actual compiler work runs off the event loop with at most
`scan_workers` admitted operations and no scan backlog. Retrieval uses the same
bounded pool. Provider/job settings do not activate unimplemented services.

An HTTP timeout returns `503`; coroutine cancellation and client disconnect are
not represented as thread termination. Running compiler work retains its slot
until it exits. A cancelled/timed-out operation checks its cancellation/deadline
before storage; cancellation can race a transaction that has already begun.
Such a transaction can complete, but cannot overwrite a snapshot. Shutdown waits
for running threads. Compiler budgets bound analysis work, but blocking OS I/O is
not a hard process deadline. A stuck worker consumes its slot; the service does
not create replacement threads. Admission limits are per application process;
run one process through the supported entry point.

Storage requires an existing absolute local directory outside **every** permitted
repository root. It uses `analyses.sqlite3`, schema `PRAGMA user_version = 1`,
parameterized values, transactions, a primary key and update/delete rejection
triggers. Unknown/corrupt schemas are unavailable and are never dropped or
migrated implicitly. Payloads are validated public `ScanResponse` JSON plus
timestamp/schema/completion metadata; no source, prompts, fingerprints, graph
evidence or credentials are persisted. Retrieval validates both JSON and metadata.
The default caps are 256 records (maximum 4,096) and 16 MiB per record (maximum
64 MiB); exhaustion returns `429`. There is no automatic expiration or deletion.
The future job-retention setting does not expire analysis snapshots. Operators
must manage this trusted state while the service is stopped.

Configuration and storage are trusted operator-owned local files/directories,
not writable by scanned projects or untrusted users. Loopback binding and strict
Host/Origin checks reduce browser-origin access; they are not multi-user
authentication or an OS sandbox. Allowed browser origins are exactly
`http://localhost:5173`, `http://127.0.0.1:5173` and `http://[::1]:5173`; CORS has
no wildcard/credentials. Host must be localhost or a numeric loopback address.
Remote deployment, proxies, authentication, hostile storage owners and hard-link
isolation require a separate design. The existing frontend still contains its
earlier mock fallback and older types; it is unchanged and needs a coordinated
consumer update. This backend never substitutes mocks.

### Explicit startup

Create approved repository roots and a separate trusted storage directory yourself.
Prepare an absolute, non-secret JSON file, for example (replace these placeholders
with existing absolute local paths; Windows accepts `D:/...`):

```json
{
  "permitted_repository_roots": ["/absolute/approved/repositories"],
  "storage_directory": "/absolute/private/analysis-state",
  "bind_host": "127.0.0.1",
  "bind_port": 8000,
  "scan_workers": 1,
  "scan_timeout_seconds": 30
}
```

From the project root with already installed dependencies:

```text
python -B -m backend.main --config /absolute/path/to/non-secret-settings.json
```

Only this explicitly named regular JSON file (at most 64 KiB) is loaded. Unknown
fields, credential fields and non-loopback bindings fail validation with a fixed
startup error and nonzero exit. No environment/dotenv values are loaded. No config
starts a loopback liveness-only app with scanning disabled. `start.sh` accepts
`--backend-config ABSOLUTE_JSON`, calls this entry point without reload, requires
preinstalled frontend dependencies and uses Bash 4.3+ `wait -n` to propagate the
first service exit and stop its sibling. Cleanup preserves failure/signal status.
It no longer creates `.env` or silently installs packages. No server was launched
as part of in-process API validation.

### Local test command

Run the full trusted test suite, excluding sample source as test inputs. On
PowerShell, using the already selected Python interpreter:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTEST_ADDOPTS=''
$taskTemp=Join-Path ([System.IO.Path]::GetTempPath()) ('cascaderouter-tests-'+[guid]::NewGuid().ToString('N'))
if(Test-Path -LiteralPath $taskTemp){throw 'Expected fresh temporary directory.'}
python -B -m pytest -p no:cacheprovider tests/ -q --tb=short -rs --ignore=tests/fixtures/ --basetemp $taskTemp
```

Tests use injected temporary policy/storage and FastAPI TestClient or pure ASGI
messages, never provider requests or target execution. Async boundary tests use
`asyncio.run` without requiring plugin autoload. Symbolic-link tests explicitly
skip when creation privileges are unavailable; junctions run on Windows and POSIX
namespace-replacement tests run on POSIX. Python 3.11 CI is configured but local
Python 3.14 execution does not validate that runtime.

## Dependency and CI status

The project retains pip and `requirements.txt`. Pydantic v2 plus the standard
library implements this foundation; no settings library or new lint stack was
added. Existing runtime/test dependency inputs are retained with upper bounds.
Provider prerequisites remain listed; provider execution is not implemented.

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

- `POST /api/benchmark`: explicit cases/models and bounded job creation.
- `GET /api/runs/{run_id}`: actual job status and available results.
- `POST /api/runs/{run_id}/cancel`: controlled cancellation.
- `POST /api/optimize`: recommendations from actual eligible measurements.

Provider execution, job states, evaluation, runtime routing, patching
and regression execution require separate implementations and acceptance gates.
