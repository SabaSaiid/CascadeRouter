# Updated main / PR #5: second merge acceptance

This is a separate merge after the completed
[first main reconciliation](main-merge-acceptance.md). Both preserve the branch
`integration/cascade-router-zero-cost` and all pre-merge history.

| Merge | First parent | Second parent |
| --- | --- | --- |
| First, committed as `8af490f6e4af51b94b933cb6a6e12b99d3f7a959` | `c93f5f400683cf4908c12a710dbb6fbaded8dfda` | `5c5f09a86a554affac75cce4743cdf13d1d92450` |
| Second, commit containing this report | `8af490f6e4af51b94b933cb6a6e12b99d3f7a959` | `616ae073a0d4dc505a791c06e0914d429d5b49b4` |

The first merge did **not** incorporate PR #5. The second incoming commit is
the actual `Merge pull request #5` commit; its parents are `5c5f09a...` and
`f07df782d98bfafec89cb301426ddcbbc9b1531b`. The merge base for this second operation
is `5c5f09a86a554affac75cce4743cdf13d1d92450`. No fetch was performed by the agent:
the local `origin/main` reference was verified against the requested `616ae07`
before starting the second `git merge --no-ff --no-commit origin/main`.

## Individually reconciled change

The complete incoming delta is **README.md only**. It was the sole conflict;
there were no automatically staged non-conflicting changes. The base, integration
and incoming versions were read and compared. All 467 incoming lines were reviewed.
[updated-main-merge-review.json](updated-main-merge-review.json) records source
SHA-256 identities, incoming parent identities and the accepted/rejected content.

The useful PR #5 navigation/layout and license information is incorporated, with
paths verified against this branch: current API modules, durable services,
compiler/runtime boundaries, frontend client/components, test/diagnostic tooling,
actual API guides and the existing MIT LICENSE. The integration README's verified
local setup, explicit configuration and available workflows remain intact.

Incoming descriptions of provider catalogs/billing, dotenv settings, target capture
and regression execution, SDK passthrough/fallback, heuristic quality, latency tie
windows, obsolete endpoints/request bodies and mock-success UI behavior are not
current capabilities. Historical 428-test/98%-coverage badges and Node 20/suppressed
build instructions were not presented as current results. No remote badges, new
provider setup, ownership reassignment or unsupported safety claim was added.
The source remains available in the incoming commit's Git history.

Relative to the first merge, only README.md and these two review records change.
Production code, API schemas, tests, workflows, dependencies, lockfiles, sample
source and the test-only network guard remain byte-identical in Git.

## Observed validation

Actual environment: Python **3.14.3**, Node **24.16.0**, npm **11.13.0**. Frontend
tests/typecheck used existing supplemental TypeScript **6.0.3** and React/ReactDOM
**19.3.0**. They do not verify an exact-lock installation or production build.

| Check | Passed | Failed | Errors | Skipped | Exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| Focused compiler/graph/metrics/optimizer/runtime/patch/schema/API/security/CI | 897 | 0 | 0 | 8 | 0 |
| Full appropriate repository suite | 1,291 | 0 | 0 | 8 | 0 |
| Frontend contract/render/lifecycle tests | 86 | 0 | 0 | 0 | 0 |

Supplemental TypeScript: **0 diagnostics, exit 0**. Focused tests took 36.50 seconds
and reported 3,755 deprecation warnings. The eight platform skips cover three
compiler symlink cases (errno 22), three security symlink cases (Windows privilege
error 1314) and two POSIX namespace-replacement cases prevented by Windows pins.
No required Node acceptance case skipped. The second full run completed in 53.00
seconds with 3,778 deprecation warnings. Counts and hashes were reconciled against
its actual JUnit report, independently of the first merge's passing run. Both
Python runs recorded zero non-loopback attempts and zero provider SDK imports.

Generated OpenAPI/frontend contract, canonical source inventory and historical
release-evidence consistency checks exited 0. The selected source inventory still
verifies 65 committed inputs and 621,437 canonical Git-blob bytes. Neither metadata
checks nor passing tests establish build success or universal security correctness.

### Actual commands for this second merge

From `D:\CascadeRouter`, with the installed Python 3.14.3 interpreter:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTEST_ADDOPTS=''
$env:CASCADEROUTER_REQUIRE_NODE_ACCEPTANCE='1'
$env:CASCADE_MERGE_NETWORK_REPORT=Join-Path ([IO.Path]::GetTempPath()) 'cascade-updated-main-focused-network.json'
$taskBase=Join-Path ([IO.Path]::GetTempPath()) ('cascade-updated-main-focused-'+[guid]::NewGuid().ToString('N'))
$taskReport=Join-Path ([IO.Path]::GetTempPath()) 'cascade-updated-main-focused.xml'
python -B -m pytest -p no:cacheprovider -p scripts.pytest_loopback_guard tests/compiler/test_ast_scanner.py tests/unit/test_main_evaluator_regressions.py tests/unit/test_evaluator.py tests/unit/test_metrics.py tests/unit/test_router_optimizer.py tests/unit/test_policy_generator.py tests/unit/test_runtime_router.py tests/unit/test_patch_generator.py tests/unit/test_patch_validator.py tests/unit/test_schemas.py tests/unit/test_ci_summary.py tests/unit/test_release_preflight.py tests/integration/ tests/security/ -q -ra --tb=short --ignore=tests/fixtures/ --junitxml $taskReport --basetemp $taskBase

$env:CASCADE_MERGE_NETWORK_REPORT=Join-Path ([IO.Path]::GetTempPath()) 'cascade-updated-main-full-network.json'
$taskBase=Join-Path ([IO.Path]::GetTempPath()) ('cascade-updated-main-full-'+[guid]::NewGuid().ToString('N'))
$taskReport=Join-Path ([IO.Path]::GetTempPath()) 'cascade-updated-main-full.xml'
python -B -m pytest -p no:cacheprovider -p scripts.pytest_loopback_guard tests/ -q -ra --tb=short --ignore=tests/fixtures/ --junitxml $taskReport --basetemp $taskBase
```

From `D:\CascadeRouter\frontend`:

```powershell
$env:CASCADE_TEST_TOOLS='C:\Users\LENOVO\AppData\Local\Temp\cascade-ui-tools-mZA2yh'
$taskReport=Join-Path ([IO.Path]::GetTempPath()) 'cascade-updated-main-frontend.xml'
node --test --test-reporter=spec --test-reporter=junit --test-reporter-destination=stdout --test-reporter-destination=$taskReport tests/*.test.mjs
npm.cmd run typecheck
```

Root verification commands:

```powershell
python -B frontend/scripts/sync_contracts.py --check
python -B -m scripts.source_inventory
python -B -m scripts.check_release_evidence
git diff --check
git diff --cached --check
```

The review JSON retains actual JUnit counts, SHA-256 identities, temporary report
basenames and Python network-guard observations. Diagnostic files remain in host
temporary storage; they are not release packages or manufactured benchmark evidence.
The network guard covers Python DNS/connect/connect_ex/sendto, not child processes
or a complete OS boundary. First-party local client/CLI commands and backend import
boundaries were reviewed; no provider or target-execution path was introduced.

## Safety and release status

No operator target application was imported/executed, no operator target source
was modified, and no proposal was applied. Isolated test attack fixtures may be
deliberately changed to verify stale-source rejection; this does not apply patches
to operator repositories. Test-only evidence does not gain production authority.

The [release register](release-gates.json) remains authoritative and **blocked from
release**. Its Phase 4.11 receipts remain historical; current merge results are
reported separately. Exact-lock typecheck/build/lint, Python 3.11, clean dependency
validation, browser interaction, genuine approved production evidence, platform
filesystem coverage and hosted CI remain unclosed. No blocked build/lint was
forced, and the historical hosted-CI failure cause is still unknown.

No dependencies were downloaded, no lockfiles or declared versions were changed,
and no paid integration, external inference, billing setup, credential, fabricated
metric/success or co-author trailer was added. No push, fetch, pull, remote merge
or pull request was performed. Both local merge commits preserve prior history;
the backup branch remains at the original integration HEAD.
