# Evidence-based offline routing (Phase 4.5)

`POST /api/optimize` compares only persisted, approved offline benchmark evidence.
It performs no inference, provider request, model download, source execution,
source import, dotenv/environment lookup or automatic policy application. The
mandatory zero-cost policy continues to apply to later backend phases.

No genuine production recordings were supplied during this phase. Default
optimization is unavailable; tests never authorize synthetic production evidence.

## Explicit objective and configuration

The versioned objective is `all-checks-then-cost.v1` under configuration
`zero-cost.optimizer.v1`. Configure `optimization_quality_threshold` explicitly
as a decimal string between `"0"` and `"1"`, with at most six fractional places,
in the existing approved non-secret startup JSON. For example, `"0.92"` is an
operator choice, not an implicit backend default. Omission leaves optimization
unavailable with `threshold_unconfigured`. Requests cannot override this policy.

The baseline is `plan.models[0]`, the explicitly registered comparison model.
It does not assert that this is the model currently used by the application.
Every candidate must be a registered model/version selected by that same plan.
Models absent from the evidence are never inferred to be available.

For each node, compare the exact same planned cases from one completed run,
analysis snapshot, case-set version/digest and evaluation-profile version/digest.
No cross-run joins or differing versions are combined. Every planned case must
have integrity-identified captured output and a decisive passing evaluation with
actual checks and passing required validation. Failed required checks exclude a
candidate even if the threshold is lower. Skipped, unrun and inconclusive cases
leave quality insufficient; they are never removed to improve the denominator.

`quality_pass_rate` is the observed passed/planned case fraction, available only
when all cases have decisive evaluations. It is rounded to six decimal places
using Decimal `ROUND_HALF_EVEN`. It describes this finite case set, not a model
quality score, statistical guarantee, generalization claim or quality-parity claim.
Eligibility requires all cases to pass, so the observed eligible rate is one and
must meet the configured threshold. This deliberately conservative first objective
does not use the threshold to excuse failed required checks.

Each eligible candidate also needs a cost for every planned case, calculated
by the existing Decimal engine from actual usage and pinned, traceable pricing.
Compare total recorded USD over the same case population; no current-price lookup,
missing-value imputation, inferred tokens or estimated cost is used. Sums and
differences use an isolated precision-80 Decimal context with no monetary rounding.
Financial fields serialize as decimal strings. Known zero costs are valid.

An ineligible baseline produces `inconclusive`, never an improvement claim.
Insufficient evidence for any otherwise viable alternative makes the minimum
inconclusive. Decisively failed alternatives are excluded. Otherwise choose the
minimum-cost eligible model; ties favor the baseline, then model identifier in
lexical order. An eligible baseline with no eligible alternatives is retained.

`recorded_savings_usd` is baseline minus selected cost for these captured cases
only. It is null for unresolved decisions; an established zero is retained. There
are no percentage savings, projected/live savings or performance-improvement claims.
There is no authoritative latency target in the current backend configuration.
Latency remains a descriptive measured population with sample count and units;
missing latency stays unavailable. No cost/latency weights are invented.

## Input authentication and resource boundary

The endpoint retrieves immutable analysis/job records from the existing SQLite
store and applies the current repository-root policy. It requires the exact
analysis ID, analysis payload digest and included node identities. References to
different case/profile versions return `409 source_conflict`.

Production additionally requires the built-in approved offline executor, local
registry, operator-controlled manifest, genuine `recorded` provenance and current
asset integrity. Test provenance always returns unavailable, including when
`allow_test_benchmarks=True`. The optimizer has no test-acceptance switch.

Before deciding, the service revalidates the current registry, registered model
versions, immutable version catalog, plan and manifest/capture hashes. It reuses
the offline evaluator to reproduce each stored measurement from the protected
captures, including its evaluation, usage, latency, pricing calculation and
integrity references. It also recomputes the aggregate and compares it exactly.
Structurally valid but altered result flags/costs cannot become recommendations.
Missing catalog entries are rejected, never auto-registered. Approval is rechecked
after the decision. The immutable in-memory input is used throughout the decision.

Existing no-follow reads, size/depth limits and junction/substitution safeguards
apply to asset verification. Existing request-body limits, finite scan-worker
admission and request deadlines apply to optimization. Work is bounded by the
plan (16 nodes, 9 models, 64 cases, at most 1,024 units) and the configured
`max_benchmark_units`. The total JSON response must fit `max_job_result_bytes`.
There is no background optimization queue or additional worker pool.

Phase 4.7 adds an immutable optimization record to the existing SQLite store.
The additive response field `optimization_id` is `opt_` plus the SHA-256 digest
of the canonical validated response excluding that field. The result and policy
digests retain their original meanings. Repeated identical responses reuse the
same ID without overwriting anything. Records bind the retained analysis and job;
all other record IDs remain immutable. Capacity exhaustion returns `429`.

The public scan contract does not retain per-file source fingerprints. Here,
source identity means the exact immutable analysis payload bound to the original
capture, not proof that today's working directory is unchanged. A policy is bound
to that snapshot and is not automatically applied. Deployment/current-source
validation for patch proposals is now provided by [patches.md](patches.md), using
private evidence captured only during new scans. Runtime deployment and application
remain separate gates. Operator approval of bytes
cannot prove historical measurement authenticity; protected settings/manifest
permissions and review of genuine capture origins remain necessary.

## API contract

The shared Pydantic models are `OptimizationRequest`, `OptimizationResult`,
`RoutingDecision`, `OptimizationCandidate`, `RoutingPolicyArtifact` and
`OptimizationResponse` in `backend/schemas.py`. There is no alternate benchmark
measurement format. The result retains the existing `BenchmarkPlan` unchanged.

Example request shape (identifiers must reference real retained entities):

```json
{
  "analysis_id": "analysis_00000000000000000000000000000000",
  "run_id": "run_00000000000000000000000000000000",
  "case_set": {"identifier": "approved-cases", "version": "v1"},
  "evaluation_profile": {"identifier": "approved-profile", "version": "v1"}
}
```

No paths, costs, quality numbers, model selections or approval labels are accepted.
The response contains `result`, `policy` and the persisted `optimization_id`.
Per-node statuses are `recommended`,
`baseline_retained`, `inconclusive` and `unavailable`; unresolved decisions have
null selected model and savings. Eligibility/exclusion reasons are controlled
codes. Each candidate retains its actual planned model version, coverage counts,
available observed pass rate, cost, measured latency population and digest of its
canonical case-sorted existing measurements.

Overall `status` is `complete` only when every node decision is decisive; otherwise
it is `inconclusive`, or `unavailable` when all node decisions are unavailable.
Counts report nodes considered, with an eligible candidate, recommended, retained,
inconclusive and unavailable. Diagnostics are separate from model decisions.
Every decision retains the original `test`/`recorded` provenance. The result also
binds the benchmark digest, plan, configuration, approval manifest and capture
dataset digests. Raw prompts, expected outputs, recorded outputs, source text,
pricing source contents, exception text and host asset paths are absent.

`200` can honestly report unavailable/inconclusive decisions. Known test jobs,
unfinished jobs, missing threshold and missing approved execution have controlled
reasons. Unknown persisted IDs return `404`; malformed/extra request fields `422`;
unauthorized retained repository paths `403`; stale/inconsistent/corrupt inputs
`409`; unavailable storage/assets `503`; capacity violations `429` and oversized
bodies `413`. Unexpected failures use the existing sanitized `500` boundary.

Health `optimization_available` reports initialized approved production capability
plus an explicitly configured threshold. It is not a per-run eligibility decision
or a fresh integrity probe. The frontend's current types/client remain unchanged;
they still expect older mock fields and silently substitute mocks on errors. A
coordinated consumer update is required. This backend never returns those mocks,
fabricated regression success or invented fallback models. Patch diffs are exposed
only through the separate authorized patch API.

## Pure YAML policy generation

PyYAML is already declared in requirements and installed in the verified local
environment. `generate_policy` uses `safe_dump`, with stable key/node ordering,
and round-trips its own bounded output through a duplicate-key-rejecting
`SafeLoader` subclass. No external YAML, custom constructors, unsafe tags or
executable validators are accepted. Missing serializer is a controlled
`serializer_unavailable` artifact; failed validation is `serialization_failed`.
No dependency is installed to work around either condition.

The returned content is intended for `.cascaderouter.yaml`, but no file is written.
`cascaderouter.policy.v1` includes analysis/run/input/configuration identities,
explicit provenance, validated routes, actual measured evidence and omitted-node
reasons. It emits no unverified fallback, runtime capability or regression status.
Test algorithm fixtures can generate explicitly test-labelled YAML only in unit
tests; the production endpoint never emits a route based on test evidence.

An artifact is `available` only for complete decisions, `partial` when eligible
routes coexist with omitted unresolved nodes, and `unavailable` when there are no
eligible routes or no safe serialization capability. The artifact has its own byte
digest and route count. A partial policy is never presented as universally complete
or safe. Runtime wrappers, patch generation, application and regression execution
remain outside Phase 4.5.
