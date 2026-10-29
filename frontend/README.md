# CascadeRouter local workbench

React 19, TypeScript 6, Vite 8 and the existing dark design tokens. Node 24+ is
required for the built-in test runner's native TypeScript support. No new package
or hosted service is required. Backend contracts remain authoritative.

## Local setup

Use a trusted pre-provisioned environment. From `frontend/`, `npm ci --offline`
uses only the existing npm cache and lockfile. If a locked package is absent, stop
and provision the approved cache separately; do not enable downloads or substitute
package versions to hide the failure. No credential or provider configuration is
needed. On PowerShell use `npm.cmd` if script policy blocks `npm.ps1`.

Run `npm run dev`; the dev server binds `127.0.0.1:5173` with a strict port. Preview
and development must stay on loopback; do not override the host with a LAN address.
The UI defaults to `http://127.0.0.1:8000`. To use another approved local port, set
`$env:VITE_API_BASE_URL='http://127.0.0.1:8001'` before starting Vite. Only HTTP
localhost, 127.0.0.1 or ::1 origins are accepted. Paths, URL credentials, queries,
remote hosts and redirects are rejected. Backend Host/Origin checks remain intact;
this client does not extend the backend's allowed origin list.

From the repository root, start the configured backend with:

```powershell
python -B -m backend.main --config C:\CascadeData\backend.json
```

The explicitly supplied non-secret JSON config must name existing authorized
repository roots and a separate existing storage directory outside all scan roots:

```json
{
  "permitted_repository_roots": ["C:/CascadeData/projects/sample-app"],
  "storage_directory": "C:/CascadeData/state"
}
```

These are examples for your operator to configure, not directories created by the
UI. Starting `python -B -m backend.main` without configuration exposes health only.
See [API setup](../docs/api-contract.md), [offline benchmarks](../docs/offline-benchmark.md)
and [optimization approval](../docs/optimization.md) for the existing operator
contracts. Do not run a scanned application's entry point or tests.

## Actual workflow and evidence

1. Check local service readiness, then supply an authorized repository path or a
   stored analysis ID. No scan, benchmark or optimization is submitted on mount.
2. Review actual findings, coverage diagnostics and individual dependency edges.
   Partial scans do not establish full coverage; missing edges do not prove
   independence. Returned repository absolute paths and source snippets are not
   displayed. Relative finding locations use AST UTF-8 byte columns.
3. Select one finding and explicitly enter local registry model IDs, case-set ID
   and evaluation-profile ID. There is no backend catalog-list endpoint and no
   provider menu. Submitting identical plans in this mounted view reuses an
   idempotency key. Keys are not persisted across page reloads: retain the run ID
   and retrieve it before resubmitting after an uncertain outcome.
4. Retrieve/refresh a stored run manually. There is no automatic retry or polling.
   Completed processing and passed evaluation are distinct. Request cancellation
   cooperatively; stopping the browser wait does not terminate backend work.
5. Optimize a completed run with its matching loaded analysis. The backend alone
   decides eligibility and verified cost selection; the UI adds no threshold,
   latency weights, invented quality score or extrapolated savings. Policy review
   does not activate runtime routing or authorize fallback dispatch.
6. Create a proposal only when a persisted optimization binds approved recorded
   evidence, or enter an existing proposal ID. Review the actual `literal-spans.v1`
   artifact and omissions. The UI cannot apply, overwrite, roll back or commit it.
7. Validate a proposal by ID, then retrieve its report later by validation ID.
   Validation may be validated, partial, invalid, stale or unavailable. HTTP 201
   records an observation, not a passing check. Historical retrieval does not
   verify current freshness. Static parse/AST validity does not prove behavior,
   model compatibility, runtime safety, benchmark quality or a successful migration.
   [Full limitations](../docs/patch-validation.md).

The optional scan demo is labeled DEMO/mock and disables all backend operations.
Synthetic test evidence remains TEST and cannot authorize production proposals.
RECORDED describes provenance, not automatic production approval; that authority
stays with backend configuration and immutable approval bindings. Missing local
cases, recordings, costs, quality, approval or storage produce real restrictions,
not fabricated results. No supplied genuine production evidence is bundled here.

Errors use controlled categories and recovery guidance, never raw server text,
exception stacks, credentials or private filesystem paths. Retry the form after
correcting configuration; wait before retrying capacity/rate errors. A stale source
requires rescan/new proposal evidence. No failure silently switches to demo data.
New scans/mode changes invalidate dependent state; obsolete requests cannot replace
newer results. Controls use native forms/buttons, labels, status announcements,
visible focus outlines, responsive tables and keyboard-operable disclosure elements.

## Validation

From `frontend/` with approved dependencies installed:

```text
npm test
npm run typecheck
npm run lint
npm run build
```

Tests use Node's existing runner, actual generated contracts, deterministic test
fixtures, and React server rendering. They check native keyboard semantics and
accessible markup; they are not browser keyboard, layout or assistive-technology
certification. `CASCADE_TEST_TOOLS` is an optional test-only path to an existing
cached TypeScript/React installation. If used, disclose its actual versions;
that supplemental check does not validate the production lockfile or Vite build.

From the root, use `python -B frontend/scripts/sync_contracts.py --check` for
OpenAPI drift. Regenerate only when deliberately reviewing backend contract changes.
Run CascadeRouter's own `tests/` suite (ignore `tests/fixtures/`); it includes a real
loopback TypeScript-client/backend contract test with byte-preservation assertions.
It never executes/imports the temporary scanned application. See the
[integration record](../docs/frontend-integration.md) for validation limitations.

Phase 4.10 adds a static offline input check:
`python -B frontend/scripts/check_offline_inputs.py` from the repository root.
It checks lock declarations, supported version ranges, scripts and static imports;
it does not install dependencies or establish production build success. See the
[acceptance and risk register](../docs/phase410-acceptance.md) for actual client/API,
restart, authorization and evidence-parser coverage, and the
[reproducibility investigation](../docs/phase410-reproducibility.md) for exact cache
blockers and browser/Python 3.11 status. CI now retains separate frontend JUnit
test counts and build status; unavailable reports never become passing counts.
