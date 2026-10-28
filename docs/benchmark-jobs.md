# Persistent local benchmark jobs (Phase 4.3)

## Mandatory zero-cost boundary

All subsequent backend phases, including optimization, routing policies and
regression validation, must remain local and provider-independent. No inference
or search provider integration, credentials, billing configuration or outbound
provider calls are implemented or authorized. The unused OpenAI SDK requirement
has been removed. Scanning OpenAI syntax does not import that SDK or target code.

Production execution now supports **approved offline captured-output evaluation**,
with [Phase 4.4 approval, metrics and schema details](offline-benchmark.md). No approved
datasets or genuine recordings were supplied during this implementation, so the
default product registry/executor is unconfigured and job creation is unavailable.
Health identifies missing registry/executor, unapproved execution or unavailable
lifecycle/storage with controlled reason codes, without exposing asset paths.
The backend does not invent cases, expected outputs, model availability, model
outputs, latency, tokens, costs, evaluations or successful benchmark outcomes.

`test` and `recorded` are distinct benchmark provenances. Scan provenance remains
unchanged. Test executors/registries require explicit `create_app` injection with
`allow_test_benchmarks=True`; test assets cannot be enabled by startup JSON.
Production accepts exactly the built-in `OfflineBenchmarkExecutor`, with an
operator-manifest approval capability, recorded provenance and a local registry.
The older measurement-only `ReplayExecutor` is retained for test compatibility;
caller-supplied recorded labels do not authorize production execution.
There is no provider plugin, dynamic executor import, shell
command, target-test execution, subprocess runner or implicit mock fallback.

## HTTP and shared contracts

The existing loopback, root policy, streamed-body limits, HTTP admission and
controlled `ErrorResponse` boundary apply to all job routes. The shared models
are in `backend/schemas.py`, version `cascaderouter.benchmark.v1`.

| Endpoint | Behavior |
|---|---|
| `POST /api/benchmark` | `202` after durable acceptance; returns run ID, actual accepted state, provenance and relative status URL |
| `GET /api/runs/{run_id}` | `200` persisted plan, execution state, actual progress, measurements and optional terminal summary/error |
| `POST /api/runs/{run_id}/cancel` | `200` current state; cancellation requested and cancellation finished remain distinct |

`BenchmarkRequest` requires `analysis_id`, `node_ids`, `baseline_model_id`,
`candidate_model_ids`, `benchmark_case_set_id`, `evaluation_profile_id`; optional
`idempotency_key` is non-secret bounded metadata. Unknown fields and coercions are
rejected. IDs use explicit bounded syntax. At most 16 distinct nodes, 8 distinct
candidates and 64 cases per resolved case set are permitted; the baseline cannot
also occur among candidates. The complete node/model/case cross product must fit
`max_benchmark_units` (default 256, maximum 1,024).

An analysis must exist, have `data_source: live`, be complete in both compiler
components, and belong to the current permitted-root policy. Every selected node
must occur in that immutable snapshot. Partial/synthetic analyses are rejected
with `409`. The baseline is an explicit registered comparison model, not a claim
that the compiler resolved the application's current model. Every model must be
registered, and the executor must validate actual recorded coverage before a job
is created. Syntax alone never establishes availability.

Unknown analysis/run: `404`; unknown case/profile/model/node: `422`; unauthorized
analysis path: `403`; incompatible state/plan/idempotency conflict: `409`; excessive
body: `413`; queue/work/retained-record limit: `429`; missing prerequisites or
lifecycle owner: `503`. Unexpected request errors remain fixed `500` responses.
Unknown run-ID shapes return `422`. No raw executor exception is public or logged.

Exact idempotent retries return the same run with `202`, including its current
terminal state if already finished. Reusing a key with different request or
resolved plan returns `409`. Keys are never overwritten. Registry or execution
version changes can make an old retry incompatible; the status URL remains the
way to retrieve its original record. A lost HTTP response after acceptance can
leave a valid running job; use an idempotency key to retry safely.

## Plans, local cases and recorded evidence

`BenchmarkPlan` freezes the analysis ID/schema/digest, ordered selected nodes,
baseline-first versioned model list, case-set/profile IDs and versions, case IDs,
registry digest, executor-artifact digest and non-secret configuration version/
digest. The latter binds policy, job deadline, unit/result limits and queue/worker/
record limits. No source text, case prompt, expected output, credential, full
schema or model-output text is included in a job plan or result.

`BenchmarkRegistryDocument` (`cascaderouter.registry.v1`) requires explicit
`origin`, `approved: true`, versioned `case_sets`, `evaluation_profiles` and
`models`. Each local case has a bounded identifier, explicit `input_text` and an
optional supplied `expected_output`. Phase 4.4 case sets additionally pin provenance,
validation version and content digest; profiles pin a built-in mechanism, optional
local schema and content digest. The offline engine evaluates captured outputs;
the legacy replay interface performs no new evaluation. Input/expected text remains in trusted registry
memory and is bound by digest, never copied into SQLite jobs. IDs are unique and
registry JSON is capped at 1 MiB.

The legacy test-compatible `RecordingDocument` (`cascaderouter.recordings.v1`) requires `provenance`,
`approved: true`, a non-secret `source_id`, an aware `recorded_at`, and bounded
per-analysis recordings. Each binds the exact immutable analysis ID/digest,
registry digest, case-set/profile versions and unique unit measurements. The file
is capped at 4 MiB. Replay requires every requested unit to exist and returns
those supplied measurements verbatim. It does not measure replay wall time as
model latency, infer missing tokens/cost, reconstruct prompts or contact models.
Phase 4.4 production uses `OfflineRecordingDocument`, guarded data roots and a
separate operator manifest, rather than trusting this legacy document's approval
flag. Integrity cannot by itself prove that historical measurements are authentic.

Production startup JSON may explicitly name `benchmark_registry_path` and
`benchmark_recordings_path`, both absolute regular local JSON files outside every
permitted scan root. Phase 4.4 additionally requires `permitted_benchmark_data_roots`
and `benchmark_approval_manifest_path`; the latter must be outside data/source
roots and pin each approved asset's raw SHA-256 and provenance.
The existing `python -B -m backend.main --config ABSOLUTE_JSON`
entry point loads only those files. Symlinks/reparse points, unsupported schemas,
invalid approvals, oversized/changing files and `test` assets fail closed. Missing
or invalid assets leave health's `benchmark_available` false; there is no demo
dataset or fabricated recording created to make startup work.

`BenchmarkExecutor` is a typed, trusted synchronous iterator boundary for future
approved local implementations. It validates the plan, has an identity and
idempotency declaration, and yields only completed `BenchmarkMeasurement` units.
All executor work and cleanup must end with iterator completion; detached work is
outside this interface. A future local executor needs explicit review under the
same zero-cost policy. This phase implements no new inference runner.

## Truthful progress, quality and states

Each unit identifies node/model/case and provenance. Latency, input/output tokens
and cost have explicit availability plus a nullable value. Quality score is
nullable; evaluation is `passed`, `failed`, `inconclusive` or `unavailable`. Missing
values are never replaced with zero. The executor must supply each unit record;
the lifecycle does not pad missing units. Returned records must match the plan,
be unique, and preserve provenance.

Progress counts only validated unit records successfully committed to SQLite.
It contains completed/total units, not simulated percentages or guessed time.
Full payloads are not read on every watchdog tick; deadline checks use bounded
metadata. Progress/results are bounded by unit count and `max_job_result_bytes`
(default 1 MiB, maximum 8 MiB); plan/transport metadata has a separate 64 KiB cap.

| From | Allowed next states |
|---|---|
| `queued` | `running`, `cancelled`, `error`, `interrupted` |
| `running` | `cancelling`, `complete`, `error`, `interrupted` |
| `cancelling` | `cancelled`, `error`, `interrupted` |
| `cancelled`, `complete`, `error`, `interrupted` | None |

Both service transactions and SQLite triggers reject invalid transitions and
changes to immutable plan fields. A job becomes `complete` only after iteration
and cleanup have ended, all planned units exist, and its terminal result is
committed. Execution completion is separate from benchmark quality. The summary
is failed if any actual evaluation failed, passed only when all supplied
evaluations passed, and inconclusive otherwise. No average score is fabricated.
Error/cancelled/interrupted jobs retain actual partial measurements without a
successful terminal summary.

## Admission, deadlines and cancellation

There are exactly `job_workers` background threads (default 2, maximum 8) and a
finite queue of `max_queued_jobs` (default 32, maximum 256). The queue is protected
by one condition lock. No task/thread is created per job. API validation and
SQLite calls share the existing bounded scan/HTTP worker pool. `max_jobs` (default
128, maximum 2,048) caps all retained job records, including terminal jobs.

Queue admission and SQL insertion execute while the queue lock is held. Queue
publication occurs inside the database transaction; workers cannot claim until
commit. Failed admission/commit removes any unpublished queue entry and rolls
back both job and idempotency key. A capacity rejection leaves no orphaned job.

The persisted UTC deadline starts at creation and includes queue waiting.
Queued deadline expiry becomes `error/deadline_exceeded`. A running deadline
requests cooperative cancellation, persists `cancelling` with reason `deadline`,
and retains the worker. After actual execution/cleanup ends it becomes `error`.
Explicit queued cancellation is immediately `cancelled`; explicit running
cancellation returns `cancelling` until work/cleanup ends, then `cancelled` unless
execution failed. The first cancellation reason is preserved. If completion was
already committed, later cancellation returns the unchanged terminal record.

Cancelling an HTTP coroutine never terminates a job worker. Non-cooperative or
blocked work can occupy a worker beyond its deadline; no replacement thread is
created. Shutdown stops admission, interrupts queued work, signals running work
and joins threads before closing storage. It honestly waits for non-cooperative
work, so shutdown has no hard duration guarantee. No claim of process isolation,
forced termination or hard CPU/I/O deadline is made.

## Persistence, ownership and restart

Jobs reuse `analyses.sqlite3`. Initialization validates the exact version-1 or
version-2 schema, migrates transactionally, and advances `user_version` to 3.
Version 3 adds an immutable benchmark-version catalog; scans and jobs are preserved.
Migration failure rolls back without losing immutable scan snapshots.
Unknown versions or schemas are never replaced implicitly. SQL values are
parameterized; foreign keys bind jobs to retained analyses. Terminal records,
plans and idempotency keys cannot be silently overwritten or deleted.

A `jobs.lock` file in the same trusted storage directory uses an OS advisory
exclusive lock for one lifecycle owner, including across local processes. A
second owner fails closed before recovery and cannot reclassify the first
owner's running jobs. The supported deployment is one application process.

On restart, `running` and `cancelling` become `interrupted`; they are never
automatically executed again. `queued` work resumes only when unexpired, executor
idempotency is explicitly true, current policy authorizes its immutable analysis,
all plan/configuration/registry/execution identities still match, and a bounded
queue slot exists. Otherwise it becomes controlled `interrupted` (or deadline
`error`). Claiming `queued -> running` commits before invoking the executor.

If a process exits before insertion commits, SQLite rolls it back. If it exits
after commit but before submission acknowledgement, the queued row is recovered
under the above rules. A crash after a running claim produces interrupted work,
not a second execution. Exactly-once arbitrary side effects are not promised.
Recovery tests simulate durable crash states and competing owners; no hosted
crash-recovery or Python 3.11 runtime result is implied.

Terminal-result write failure never produces `complete`. The service attempts a
controlled `error/storage_unavailable`, stops admission and signals active work.
If storage cannot persist even that failure, the last durable nonterminal state
remains for fail-closed restart recovery. No successful result is fabricated.

Storage/assets must be trusted operator-owned local state, outside scan roots;
this is not a multi-user authentication or hostile-storage sandbox. Retention is
bounded by record count; automatic expiry/deletion is not implemented, and the
inherited `job_retention_seconds` does not claim otherwise. Exhausted state needs
operator management while stopped. Provider-specific legacy configuration limits
remain inactive and do not enable outbound execution.

## Validation

Use the full command in [api-contract.md](api-contract.md#local-test-command).
Lifecycle fixtures and temporary registries are explicitly `test`; no genuine
recording or invented performance measurement is presented as product evidence.
Tests use temporary SQLite state and in-process HTTP, with no external requests,
package installation or execution/import of scanned applications. The local
runtime is Python 3.14.3; Python 3.11 validation remains pending.
