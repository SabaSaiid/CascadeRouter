# Phase 4.9 local validation record

Starting branch `integration/cascade-router-zero-cost`, clean HEAD
`59c7ddd9f085efdf4821433ce5ca27bb9aac2b97`. Every implementation unit was tested and
reviewed before its separate conventional commit. No previous commit was rewritten.
The final acceptance commit adds this record, CI wiring, local HTTP integration,
accessibility markup checks, documentation and bounded financial-value guards.

## Independent commit gates

| Commit | Purpose | Gate at that commit (all exit 0) |
| --- | --- | --- |
| `679b93d` | Contract audit, generated schema foundation | Backend contract drift: 1 passed |
| `31b631f` | Typed local transport, runtime response checks | transport.test.mjs: 25 passed; backend contract drift: 1 passed |
| `1591830` | Explicit demo, no fallback or mount-triggered work, request generations | operation.test.mjs + transport.test.mjs: 30 passed |
| `c546ab4` | Scan and stored-analysis workflow | scan.test.mjs + scan-render.test.mjs + operation.test.mjs: 9 passed |
| `9b6d4e5` | Observed graph edges and partial evidence | graph.test.mjs + graph-render.test.mjs + scan-render.test.mjs: 4 passed |
| `c1f3934` | Local benchmark lifecycle, metrics and backend optimization | benchmark.test.mjs + benchmark-render.test.mjs + transport.test.mjs: 32 passed; supplemental typecheck: 0 diagnostics |
| `90e637e` | Canonical proposal review, static validation and history | patches.test.mjs + patches-render.test.mjs: 15 passed; backend test_patch_validation_api.py: 17 passed; supplemental typecheck: 0 diagnostics |

Frontend focused commands used `node --test frontend/tests/<named files>` from the
root. Each gate had zero failed/cancelled/skipped tests. Earlier development test
failures were corrected before committing, without suppressing assertions: the
actual patch ID is 32 hex characters (validation IDs use 64), and configured patch
storage returns 404 for unknown IDs before evidence approval. The live HTTP test
now asserts those exact documented categories. Product source was not changed to
turn missing evidence into success.

## Final commands and actual outcomes

PowerShell, from `D:\CascadeRouter`:

```powershell
$python = 'C:\Users\LENOVO\AppData\Local\Programs\Python\Python314\python.exe'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTEST_ADDOPTS = ''
$taskTemp = Join-Path ([IO.Path]::GetTempPath()) ('cascade-phase49-final-'+[guid]::NewGuid().ToString('N'))
$taskReport = Join-Path ([IO.Path]::GetTempPath()) ('cascade-phase49-'+[guid]::NewGuid().ToString('N')+'.xml')
& $python -B -m pytest -p no:cacheprovider tests/ -q -ra --tb=short --ignore=tests/fixtures/ --junitxml $taskReport --basetemp $taskTemp
```

**1,174 passed, 0 failures, 0 errors, 8 skipped; exit 0** (53.23 seconds;
3,788 dependency deprecation warnings). JUnit independently records 1,182 tests,
0 failures/errors and 8 skips. Six skips concern Windows symlink permissions:
3 scanner cases and 1 each for benchmark assets, patch sources and repository
access. Two repository-access cases require POSIX namespace replacement; Windows
pins prevent that rename. No new bridge test was skipped. The focused generated
contract/fixture + real local HTTP bridge command also passed 11 tests, exit 0:

```powershell
& $python -B -m pytest -p no:cacheprovider tests/unit/test_frontend_contract.py tests/integration/test_frontend_local_backend.py -q --tb=short -rs --basetemp $taskTemp
```

Use a fresh basetemp for each invocation, as in the actual runs.

```powershell
$env:CASCADE_TEST_TOOLS = 'C:\Users\LENOVO\AppData\Local\Temp\cascade-ui-tools-mZA2yh'
npm.cmd test --prefix frontend
npm.cmd run typecheck --prefix frontend
```

Frontend: **63 passed, 0 failed, 0 cancelled, 0 skipped; exit 0**.
Typecheck: **0 diagnostics; exit 0**. These use Node 24.16.0, npm 11.13.0,
TypeScript 6.0.3, React/ReactDOM 19.3.0 and matching cached type declarations.
The optional tooling directory was extracted only from pre-existing local cache;
no dependency declaration, lockfile or registry fetch was changed. React 19.3.0 is
a supplemental render tool, not proof of the locked 19.3.1 runtime. Tests use
server-rendered markup and operation/client state checks, not a browser.

```text
npm.cmd ci --offline --ignore-scripts --no-audit --fund=false --logs-dir <fresh temp>
npm.cmd run build --prefix frontend
npm.cmd run lint --prefix frontend
```

The offline install (run in `frontend/`) returned **exit 1, ENOTCACHED** for locked
Vite 8.3.5. Build returned **exit 1** because `tsc` was unavailable; lint returned
**exit 1** because `oxlint` was unavailable. These checks did not pass. No download,
downgrade, suppressed failure or successful-build claim substitutes for them.

`git diff --check` and staged whitespace review pass after correcting a document
EOF blank line. Dependency maps, lockfile, requirements, backend implementation
and existing scanned sample fixtures are unchanged from the starting commit.
Commit bodies have no co-author trailers. The branch remains local and unpublished.

## Safety and limitations

The live integration uses the real configured loopback backend, with a temporary
Python file that raises immediately if executed/imported. It checks one actual
static finding, stored retrieval, honest unavailable/not-found errors, unchanged
source bytes and absence of generated files. Existing source/patch security suites
also pass. No target application was executed/imported, no target source was
modified by a workflow, and no proposal was applied. Production UI operations
contact only the configured loopback service, refuse redirects, and omit credentials.
No provider integration, paid dependency, fabricated production evidence or external
network request was introduced. CI configuration was updated but not run remotely.

Python actually used: **3.14.3**, not 3.11. Python 3.11 runtime validation, clean
backend dependency resolution, clean exact-lock frontend install/build/lint,
real-browser interactions/layout/keyboard and hosted CI remain outstanding.
Genuine approved recorded data was unavailable for a production benchmark-to-patch
journey; those backend gates remain enforced and the UI reports their restrictions.
No complete browser end-to-end or production benchmark success is claimed.
