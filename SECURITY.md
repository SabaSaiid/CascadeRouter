# Security model and limits

This describes the current local implementation, supported by repository tests.
It is not an independent security audit, an operating-system sandbox certificate,
or a production-readiness claim. Current evidence and unclosed requirements are
in the authoritative [release-gate register](docs/release-gates.json).

## Static analysis and proposals

The scanner parses bounded Python source with AST analysis. Scanning, graph
construction, optimization, proposal generation and static validation do not import
or execute a target application, run its tests, or invoke a model provider.
Unsupported source or flow is omitted/rejected with controlled diagnostics rather
than executed to discover its behavior. Graph edges represent supported static
data dependencies, not runtime reachability, execution order or complete coverage.
See `backend/compiler/ast_scanner.py`, `dag_builder.py` and
[the public contract](docs/api-contract.md).

A `literal-spans.v1` proposal is immutable review metadata bound to retained analysis,
optimization, source manifests and original byte spans. It is not an applied patch
or a standard unified-diff apply command. Candidates exist in memory; syntax/AST
checks establish the documented static properties only. They do not establish
behavior, model compatibility, runtime safety, benchmark quality or zero semantic
regression. Unsupported encodings and omitted nodes retain their restrictions.
There is no apply, rollback, target-run or commit endpoint.

`POST /api/patches/{patch_id}/validate` creates an observation. HTTP 201 does not
mean checks passed: the result may be validated, partial, invalid, stale or
unavailable. Historical report retrieval rechecks current authority and integrity
but preserves the old observation time; it does not establish current freshness.
See [patch validation](docs/patch-validation.md) for per-stage meanings and limits.

## Authorization and filesystems

The supported backend entry point binds numeric loopback and disables proxy-header
trust. Host/Origin checks, peer rate accounting, streamed-body bounds, finite worker
admission, deadlines and controlled errors are enforced in `backend/api/boundaries.py`
and the service layer. This remains a local application: loopback is not multi-user
authentication. Do not expose it through a remote bind, public proxy or tunnel.

Repository roots and storage are explicitly injected through validated non-secret
JSON. No default home/workspace grants access. `RepositoryAccess` rechecks canonical
containment and identity; existing guards reject traversal, symlinks/reparse points
and detected source replacements. The same current policy protects stored analyses,
jobs, optimizations, proposals and historical reports. An identifier/hash is not
permission. This policy is not per-user tenant ownership.

Source manifests and two guarded verification passes detect the tested classes of
staleness and changes during transformation. They are point-in-time observations,
not an atomic repository snapshot or protection against every filesystem race.
Windows and POSIX provide different primitives. Symlink-privilege and POSIX-only
cases remain explicitly unverified where skipped; successful junction/identity tests
do not prove universal filesystem isolation.

SQLite storage is trusted operator-owned state outside all scan roots. Validated
identities, reference bindings, transactions and immutable triggers detect/reject
specified corruptions. They do not protect against every privileged attacker with
control of the host, interpreter, database and implementation. Keep that state
private, do not alter it manually, and do not treat hashes as independent approval.

## Evidence, privacy and runtime routing

Test/demo data is synthetic and labeled; it cannot authorize production routing or
source proposals. Recorded provenance alone is insufficient: genuine local data and
current operator approval bindings are required. Missing measurements remain null
or unavailable, and completed processing is separate from passed evaluation.
The optimizer enforces existing eligibility, exact verified cost and deterministic
tie semantics. It does not obtain live provider outputs or invent cost/quality.

No provider credentials, billing configuration, hosted inference, telemetry or
external search is required. Backend settings do not load dotenv values. Controlled
API errors omit input values, source snippets, absolute paths and exception traces;
logs use fixed messages/request IDs. The public scan contract retains its authorized
repository reference and bounded metadata; do not confuse metadata redaction with
a guarantee that all user-supplied identifiers contain no private information.
Private manifests/candidate bytes are not public scan or validation payloads.

The separate `backend/runtime/cascade_router.py` API requires explicit registrations
of permitted local executors and fallback authorization. The UI does not activate
it or deploy a policy. There is no implicit hosted fallback or new permission
created by a passing test, policy artifact or static validation report.

## Evidence and reporting

Relevant tests include `tests/security/`, `test_client_artifact_authorization.py`,
`test_client_http_boundaries.py`, `test_client_job_recovery.py` under
`tests/integration/`, and the patch/source/storage unit suites. They use isolated
fixtures; intentional attack mutations are not normal source-writing operations.
The Phase 4.10 report records their actual coverage and platform skips. Tests and
local checks are evidence about those cases, not proof of universal authorization
correctness or an independently audited security guarantee.

When reporting a suspected issue to the project maintainers through an already
approved channel, include a minimal synthetic reproduction and affected gate/code
path. Do not include credentials, private source, operator config values or private
database contents. This document does not invent a security inbox, response SLA or
external reporting service.
