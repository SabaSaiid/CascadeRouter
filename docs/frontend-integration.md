# Frontend integration audit and scope (Phase 4.9)

Baseline: `59c7ddd`, React 19 / TypeScript 6 / Vite 8. The existing dark three-pane
workbench and CSS tokens are retained. There was no frontend test script or UI
test framework. State was held in `App.tsx`; `services/api.ts` was the only client.
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

The implementation record and final usable flows are updated as integration lands.
