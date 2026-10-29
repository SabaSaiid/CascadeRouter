# Frontend integration audit and scope (Phase 4.9)

Baseline: `59c7ddd`, React 19 / TypeScript 6 / Vite 8. The dark workbench CSS
tokens are retained; workflow sections now reflow at zoom and narrow widths. There
was no frontend test script or UI test framework. State was held in `App.tsx`; `services/api.ts` was the only client.
The backend's Pydantic models, routes and generated OpenAPI remain authoritative.

## Verified starting gaps

| Journey | Existing frontend | Actual backend integration required |
| --- | --- | --- |
| Scan/analysis | Mount-triggered sample scan; errors silently return mock success; non-null model/framework assumptions | `POST /api/scan`, `GET /api/analyses/{analysis_id}`; explicit user action, nullable metadata, completeness and diagnostics |
| Agent graph | Edge pairs collapsed into one invented sequence in RepositoryPane | Render individual backend `graph_edges`, disconnected nodes and incomplete graph status; never infer sequence or cross-function edges |
| Benchmark | NVIDIA catalog/prices and fixed quality threshold; fabricated run IDs/progress; incomplete request | Full `BenchmarkRequest`, persisted `JobResponse`, `GET /api/runs/{run_id}`, cooperative POST cancellation |
| Metrics | Missing quality becomes zero; frontend independently selects winners/latency ties | Availability/sample counts, exact Decimal cost strings, test/recorded provenance, processing versus evaluation coverage |
| Optimization | Sends a caller threshold and claims regression-tested patches | `POST /api/optimize` with analysis/run/case/profile references; actual server eligibility and policy only |
| Patches | Fake combined unified diff and pytest log in optimization fixtures | Reference-only creation/review; preserve `literal-spans.v1`; no application or target execution |
| Static validation | No controls or schema | POST `/api/patches/{patch_id}/validate`; GET `/api/patch-validations/{validation_id}`; point-in-time static observations |

`services/mockData.ts` contains useful illustrative synthetic fixtures, but those
were used as an automatic fallback. They must be retained separately from product
API handling and identified as test/demo data. Data-source selection cannot turn
test data into recorded evidence or provider activity. The header's hosted-provider
label, spend cap, placeholder source button and regression-success messaging do
not correspond to backend capabilities. Google Fonts requests in `index.html`
also violate offline operation and must be removed.

## Contract and implementation decisions

The shared client will use explicit numeric-loopback/localhost HTTP configuration,
bounded requests, cancellation, controlled errors and response-shape validation.
Redirects must fail rather than permit a local URL to redirect to an external host.
No error payload or exception text is displayed or logged. New scans/mode changes
invalidate dependent state and stale requests. No automatic POST runs on mount.

There is no registry/catalog-list endpoint. Benchmark forms therefore need explicit
operator-supplied model IDs, case-set ID and evaluation-profile ID. They must not
invent defaults or provider menus. Health readiness is reported by `/api/health`;
readiness alone is not proof of production evidence. Optimization and patch gates
remain server-side. No browser control may enable hosted runtime dispatch.

`scripts/sync_contracts.py` derives TypeScript and bounded response-schema data from
the current OpenAPI without starting a server or executing target applications.
The backend contract-drift test checks the generated artifact. Runtime validators
must additionally protect the evidence/completeness invariants consumed by views.

## Available validation environment

Starting local tools: Python 3.14.3, Node 24.16.0, npm 11.13.0 (`npm.cmd` on
PowerShell). Frontend dependencies were absent. An offline, script-disabled
`npm ci` failed with `ENOTCACHED` for locked Vite 8.3.5. Nothing was downloaded;
package versions and the lockfile were not changed to hide this limitation.
Node's built-in test runner is available. Exact-lock builds, clean installations,
browser interaction and hosted CI must be reported separately from source/unit
checks. Python 3.11 runtime and clean-environment backend validation remain pending.

## Implemented integration

All product operations now use the generated contracts and shared local transport.
Scan and stored-analysis views show actual findings, explicit coverage and guarded
relative locations. Graph review preserves individual data-dependency edges,
fan-in/fan-out and findings without observed edges. No execution sequence is inferred.
The explicit demo is scan-only; legacy illustrative fixtures are archived in
`frontend/tests/fixtures/legacy-demo.txt`, outside the product module graph.

Benchmark submission supplies every required reference. Run state is manually
refreshed, not fabricated or polled automatically. Immutable plan provenance and
measurement populations are shown with missing values intact. Operator IDs remain
manual because no catalog API exists. There is no provider-specific flow.
Optimization consumes the actual run plan and renders backend decisions/policy;
there is no frontend optimizer or policy activation.

Proposal creation remains gated by persisted recorded/approved evidence, and the
server retains final authority. Review uses the canonical literal-spans artifact.
Static validation and historical reports are separate operations with subject IDs,
observation time, runtime/grammar distinction, omission reasons and per-file stages.
The UI offers no apply, rollback, source-edit, target-run or commit endpoint.

Operation generations and synchronous unmount cleanup prevent obsolete publication.
Repeated in-flight actions are suppressed. Identical benchmark plans reuse a key
within the mounted view; keys are intentionally not persisted across reloads. Read
stored runs after uncertain submissions. API failures never select fixtures.
Client errors are fixed categories; raw backend messages are not rendered/logged.
Responses are size-bounded and shape-checked; evidence invariants reject impossible
measurement/completeness/status combinations. Financial strings are not rounded or
used in floating-point comparisons. Requests omit credentials and refuse redirects.

## Validation coverage and remaining gates

Frontend tests exercise parsing, every controlled HTTP category, unavailable and
timeout failures, response bounds, cancellation/stale results, demo boundaries,
partial graphs/scans, missing and invalid measurements, deterministic submission
keys, actual request bodies, all five validation outcomes and historical semantics.
React server-rendered checks cover labels, native forms/buttons, named regions,
status announcements and no apply controls. Backend tests validate fixtures against
real Pydantic models and prevent OpenAPI drift. A real local HTTP integration starts
the actual backend, exercises the TypeScript transport and verifies that a scanned
file containing an execution tripwire remains byte-identical and unimported.

Local supplementary render/type checks use cached TypeScript 6.0.3 and React/DOM
19.3.0; the lockfile requests React/DOM 19.3.1 and is unchanged. The exact-lock offline
install failed because Vite 8.3.5 was not cached. Production build and Oxlint could
not run because the locked installation was unavailable. No downgrade or network
installation was used to hide that failure. Python 3.11 runtime, clean-environment
dependency resolution, exact-lock build/lint, browser interaction/layout/keyboard,
and hosted CI remain outstanding. Synthetic test success does not demonstrate a
production benchmark, approved optimization or validated production migration.

CI keeps the existing backend Python 3.11 and frontend build checks, adds the local
client/contract tests, and uses Node 24 for native TypeScript. No coverage gate,
new dependency or hosted execution of target applications is introduced. Hosted CI
has not been run locally and is not claimed to pass. See `frontend/README.md` for
commands, operator setup and user-facing outcome explanations.

Exact local commands, counts, per-commit gates and failed tooling checks are retained
in [the Phase 4.9 validation record](phase49-validation.md).
