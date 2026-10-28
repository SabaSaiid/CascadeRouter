# Explicit local runtime routing (Phase 4.6)

`backend/runtime/cascade_router.py` is an opt-in library for trusted host code.
Scanning, graph building, optimization and FastAPI do not invoke it automatically.
This phase adds no endpoint, inference implementation, model runtime, provider SDK,
credential discovery, environment/dotenv access, model download or network call.
No genuine local inference implementation is present. Default execution is
unavailable until an application explicitly supplies and authorizes an eligible
local adapter. All deterministic fake adapters in tests retain `test` provenance.

## Registrations and permission

An `ExecutorRegistration` contains a frozen, shared `RuntimeAdapterSpec` and an
in-process synchronous callable `operation(input_data, context)`. The callable
must already exist in trusted host code. Strings, import paths, coroutine
functions and duplicate adapter IDs are rejected; no plugin/module discovery or
policy-supplied executable code is supported. At most 32 registrations are kept.
The callable is omitted from registration repr and never serialized.

Metadata specifies an adapter ID, exact existing `ModelVersion`, capability
`local_in_process`, actual `local` or `test` provenance, a finite positive maximum
duration (at most 120 seconds), cancellation support, output kind (`text` or
`json_value`) and the exact evaluation-profile reference/content digest. A model
identifier alone does not create execution capability. Registration declares
capability; it does not prove request success or authenticate a model's internals.

`CascadeRouter` defaults to `mode="local"`. Production requires a `recorded`
optimization result and matching `local` registrations. Explicit `mode="test"`
requires test policies and test registrations; it cannot produce local provenance.
There is no automatic test registration or fallback to synthetic data. Tests of
the usable in-process interface do not establish genuine local model availability.

Execution also requires an independent `RuntimeAuthorization` from the trusted
host. It pins analysis ID/digest, optimization digest, policy byte digest and a
bounded list of node/adapter bindings. It is not inferred from YAML or created by
the runtime. The host must obtain authenticated optimization evidence, verify
current approval using the existing service, independently approve these exact
identities and control the registration/authorization objects. The library does
not reload approval manifests, read data files or establish historical recording
authenticity. Merely parsing a policy, or constructing Pydantic objects from
untrusted labels, grants no authority.

## Policy and fallback binding

The library consumes the existing typed `OptimizationResponse` and immutable
`ScanResponse`, not a path, URL or executable configuration. Shared strict models
check versions, unknown fields, decision counts, eligibility, thresholds and
measurement consistency. The exact policy artifact must equal regeneration by
the existing safe policy generator. Regeneration round-trips its own bounded YAML
using the existing duplicate-key-rejecting `SafeLoader` subclass. Supplied YAML
bytes are never separately deserialized. Duplicate/altered fields, unsafe tags,
unknown routes, changed decisions and contradictory policy assignments fail closed.

The analysis payload digest and node IDs must match the result and independent
host authorization. The policy remains bound to that retained snapshot; this is
not proof that today's working directory is unchanged. Deployment/current-source
verification remains a later phase.

`cascaderouter.policy.v1` has no fallback field. It is unchanged. A host may
explicitly set `fallback_adapter_id` on `RuntimeRouteBinding`, an execution
permission outside the generated YAML. Both adapter models must be eligible
candidates in the same validated decision, with matching registered versions and
the same evaluation-profile reference/digest and output kind. The primary must
match the generated selection. Fallback is never inferred from baseline status,
model size, a hierarchy or apparent provider availability.

All authorized primary/fallback bindings are validated before any operation.
Missing adapters, mismatched models, repeated adapter/model attempts, duplicate
nodes, unsupported profile/type changes and excessive attempts reject the policy.
The binding is flat: one primary and at most one fallback, without recursive
routes. An inconclusive/omitted node cannot be bound. Partial optimization policies
can execute only explicitly authorized decisive nodes, not omitted routes.

## Explicit call and validation contract

The host calls:

```python
with CascadeRouter(settings, registrations, authorization=permission) as router:
    result = router.execute(
        node_id, retained_analysis, authenticated_optimization, input_data,
        validation=validation_contract, cancellation=cancellation_event,
    )
    if result.status == "succeeded":
        application_value = result.result_data
```

These names refer to existing trusted objects, not bundled model implementations
or fabricated recordings. `cancellation` is an optional `threading.Event`.
The method returns an explicit `RuntimeResult`; hosts integrate it deliberately.
No decorators, hooks, policies or source files are installed or changed.

`RuntimeValidationContract` supplies the exact pinned `EvaluationProfile`, output
kind and one of two explicit modes. All rules are prevalidated before execution.
The existing evaluator's bounded JSON/schema allowlist and prohibition of all
reference resolution, regex and executable validators apply unchanged.

- `expected_output` requires bounded supplied ground truth. Exact profiles accept
  text only; JSON profiles compare strict structured JSON. A missing/invalid
  expected output is inconclusive before execution.
- `structure` is an explicit parsing/schema contract for `json` or `json_schema`
  profiles. It has no expected output. Actual passing structural checks can satisfy
  this application contract, while the retained `CaseEvaluation` still says
  `inconclusive / ground_truth_unavailable` for semantic quality. No quality pass,
  confidence score or correctness guarantee is invented.

`text` preserves an actual string (JSON text only when the profile requests it).
`json_value` preserves ordinary JSON-compatible dicts, lists, scalars and null.
Successful outputs are copied without changing their application type. Raw bytes,
tuples, arbitrary objects, custom serializers, invalid Unicode, non-finite floats,
oversized integers, cycles and over-budget trees are rejected. Every attempt gets
a fresh copy of the original bounded input. Mutation by the primary cannot alter
fallback input, another caller's data or another returned result.

Only a decisive evaluation failure triggers an explicit fallback. Missing
validation/metadata, invalid or oversized output, execution exceptions, limits,
capacity, cancellation and deadlines never cause implicit retries. Both attempts
use the same contract. If both validations fail, the result is failed with two
truthful attempt records and no output.

## Resource ownership and truthful interruption

`BackendConfig` adds `runtime_timeout_seconds` (default 30, finite positive, at
most 120) and `runtime_max_attempts` (default 2, range 1..2). Configuring one attempt
with a fallback binding rejects that binding before primary execution.

The library reuses `job_workers` (1..8) for a fixed per-instance pool and immediate
admission; it has no unbounded request queue. Each adapter is also serialized
within that router instance, with immediate capacity failure rather than waiting
behind a busy adapter. The host owns any concurrency across different instances
or registrations that refer to shared adapter internals.

Input bytes use `max_request_body_bytes`; output bytes use the smaller of
`max_job_result_bytes` and the existing evaluator's 16 KiB budget. Limits count
canonical ASCII JSON bytes, including escaping. Scalars are encoded in small
blocks, containers are bounded to depth 16 and 4,096 nodes, and encoding never
invokes application serialization hooks. Policy/result input also respects
`max_job_result_bytes`, the artifact's 512 KiB ceiling and 16-node decision limit.

The configured timeout covers policy/contract validation, input preparation,
execution, output checks and fallback. An adapter attempt additionally uses its
declared maximum duration. Fallback receives only the remaining original request
budget. `InvocationContext` exposes a monotonic deadline, cancellation event and
`cancelled()` for cooperative adapters. Timeout enforcement is a waiting boundary,
not proof of forcible termination or compliance with a declared duration.

On timeout/cancellation the caller stops waiting and the event is set. Late output
is discarded and no fallback starts after cancellation. A blocked operation may
continue: `worker_still_running` and the snapshot of attempt execution/validation
states report that honestly. The worker slot remains held until all actual work
and validation finish. `close()` requests cancellation and waits for owned workers;
it can wait indefinitely for a non-cooperative adapter. Cancelling an asynchronous
host wait does not kill a Python thread; hosts should signal the event and close
the router deliberately. No subprocess or hard-kill mechanism is implemented.

## Result and security boundary

`RuntimeResult` separates execution from application validation. It reports node,
actual last adapter/model/provenance, attempts, fallback use, controlled reasons,
validation state and continuing-worker state. Attempt traces are at most two
entries and contain no request data or raw exceptions. Output appears only on
validated success (including a legitimate JSON null); status distinguishes that
null from unavailable output. It is excluded from repr. Successful data is for
the explicit host application, not an ordinary scan/job diagnostic endpoint.

There are no invented latency, usage, cost, quality, savings or inference claims.
Identical deterministic inputs/adapters yield identical traces; clock durations
and timestamps are not inserted as measurements. Arbitrary adapter exceptions,
including `SystemExit` raised inside the worker, become controlled failures without
raw exception text or logging sensitive values.

The host process, its already registered callables and its permission objects are
trusted. A callable can perform arbitrary Python behavior; this interface does
not sandbox it or prove it avoids network access. Hosts must review and authorize
only genuine local implementations with no paid/provider behavior and no detached
work beyond the call. No such external execution integration is shipped here.
Bounded attempts do not provide an OS security sandbox. Runtime wrappers, callables
and permission objects are never obtained by executing the scanned repository.
Patch generation/application and an HTTP execution service remain unimplemented.
