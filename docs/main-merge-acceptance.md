# Main integration merge: resolution and acceptance

Repository: `D:\CascadeRouter`, branch `integration/cascade-router-zero-cost`.
This resolves the already-active merge; no second merge was started.

| Identity | Verified commit |
| --- | --- |
| Integration / first parent | `c93f5f400683cf4908c12a710dbb6fbaded8dfda` |
| Active `MERGE_HEAD` / second parent | `5c5f09a86a554affac75cce4743cdf13d1d92450` |
| Common ancestor | `7cd6cd3024f0c9c11506901582e424077242b497` |
| `backup/integration-before-main-sync-20261029` | `c93f5f400683cf4908c12a710dbb6fbaded8dfda` |

This record covers the **first merge only** and does **not** incorporate PR #5.
Before this merge was committed, the already-fetched `origin/main` advanced to
`616ae073a0d4dc505a791c06e0914d429d5b49b4`. That commit requires a separate,
subsequently validated merge; it does not change this active merge's second parent.

The final merge hash is reported after commit; resolve it from the commit containing
this document. Both parents' complete source/history remain reachable. No reset,
abort, stash, clean, rebase, cherry-pick, branch switch or history rewrite occurred.

## Complete path review and selected contracts

[main-merge-review.json](main-merge-review.json) records **all 78 original merge
paths**, including 17 conflicts and 61 automatically staged paths. Each entry
records its resolution/reason, SHA-256 of the incoming source and the common-base
and integration source identities (null when absent). Python import inventories
and counts of test functions describe source review, not executed test counts.

Every original merge path resolves to the accepted integration version or, for
60 upstream-only paths, remains unadopted. This was a per-file compatibility
decision, not a blanket `--ours` operation. No incoming source is silently discarded:
the incoming commit and source hashes identify the original content for review.

| Area | Decision and upstream behavior reviewed |
| --- | --- |
| CI | Keep Node 24, required acceptance checks, JUnit summaries and visible build/test failures. Main's backend failure visibility already exists; reject its unapproved 95% gate, Node 20 and frontend `|| true`/install fallback. |
| README / startup | Keep explicit JSON configuration, supported loopback CLI, failure-preserving child cleanup and no automatic installs/dotenv creation. Main's loopback fix is already satisfied. |
| Scanner | Keep bounded SDK-provenance recognition, source identities and guarded reads. Main has incompatible `RepoScan`/`DiscoveredCall` shapes; current tests cover its BOM/budget/filesystem/provenance scenarios. |
| Graph | Keep named, evidenced straight-line dependencies and incomplete-boundary diagnostics. Main's branch fix belongs to its interprocedural/sequence graph; it does not authorize those edges in this contract. |
| Evaluator | Keep strict bounded JSON/schema checks, exact ground truth and explicit unavailable/inconclusive states. Port malformed-schema and embedded-answer scenarios without adopting heuristic extraction or weighted quality. |
| Metrics / optimizer | Keep pinned Decimal evidence, missing-value availability, strict minimum cost and existing deterministic ties/baseline behavior. Reject estimated tokens/prices, a 2% latency tie window and implicit fallback-tier substitution. |
| Policy / patch generator | Keep digest-bound policy and source-verified `literal-spans.v1` edits, shared static verifier and immutable artifacts. Existing CRLF/BOM/Unicode regressions cover the upstream source-preservation concern; do not adopt callee/import rewrites or unified-diff substitution. |
| Config / schemas / app | Keep current Pydantic contracts, explicit root/storage authority, rate/body limits, durable services, validation/history endpoints and disabled CDN documentation. Main's dotenv/provider/billing settings, live/mock numeric contracts and legacy routes are incompatible. |
| Runtime / optimization service | Keep explicit local executor/fallback authority and recorded-evidence verification. Main's SDK dispatch and automatic sandbox regression path violate the non-execution contract. |
| Test configuration | Preserve every accepted integration assertion/fixture and explicit runner setup. Main's autouse dotenv fixture, live-key collection configuration and tests of absent legacy APIs are not compatible. |

The upstream-only provider/factory modules, prompt-capture harness, subprocess
sandbox/regression helpers, alternate stores/case/recording protocols and dependent
tests were deliberately not activated. In particular, prompt capture imports target
modules and regression runs target tests, even when a fake client/copy is used.
The live Nebius smoke test was not collected or run. Legacy tests are not counted
as skipped, passing or exercised coverage for this merge; their incompatible
implementations are not part of this tree. Accepted integration tests remain intact.

Upstream sample agent/case/target-test files would change the existing static-fixture
inventory and serve the rejected capture pipeline. They remain in the second-parent
history; no sample target was imported or run. Historical main-only live demo/setup
and 428-test/98%-coverage documents remain there rather than becoming current
operator instructions. Unnecessary legacy package initializers and an unrelated
`0.1.0` designation were not introduced.

The selected production/backend/frontend/configuration/dependency/fixture/CI inputs
are unchanged relative to the first parent. New content comprises this review,
the path/evidence register, a README pointer, **11 test-only evaluator regressions**
and a reproducible test-only Python network guard. The regressions adapt scenarios
from `098b54d` and `b9477ba` to actual `LocalBenchmarkCase` / `EvaluationProfile`
APIs: malformed profiles must remain inconclusive without claimed checks; prose,
multiple JSON values, fences and unfinished reasoning cannot fabricate strict-JSON
success. No previously passing assertion was weakened.

## Observed acceptance

Actual tools: **Python 3.14.3, Node 24.16.0, npm 11.13.0**. Frontend checks reused
existing supplemental **TypeScript 6.0.3 and React/ReactDOM 19.3.0**; no dependency
was downloaded, installed, added or substituted in the lockfile.

| Check | Passed | Failed | Errors | Skipped | Exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| Focused compiler/graph/evaluator/metrics/optimizer/policy/runtime/patch/schema/API/security/CI tests | 897 | 0 | 0 | 8 | 0 |
| Full appropriate repository suite | 1,291 | 0 | 0 | 8 | 0 |
| Frontend contract/render/lifecycle tests | 86 | 0 | 0 | 0 | 0 |

The focused run took 36.85 seconds with 3,755 deprecation warnings; the full run
took 49.47 seconds with 3,778 warnings. The additional 11 cases explain the delta
from Phase 4.11's historical 1,280 passing cases. No tests failed or errored.
The eight skips are three compiler symlink cases (errno 22), three security symlink
cases (Windows privilege error 1314), and two POSIX namespace-replacement cases
where Windows pins prevent rename. No required Node acceptance case skipped.

Supplemental TypeScript reported **0 diagnostics, exit 0**. Generated contract,
static offline input and source-inventory checks each exited 0; the inventory still
verifies **65 selected committed inputs / 621,437 canonical Git bytes**. Bash syntax
and CI static review passed. Both staged/working whitespace checks passed.

Counts originate from actual JUnit files, not predictions. The path register's
`acceptance` field retains their counts, SHA-256, temporary basenames, runtimes and
network observations. Files `cascade-merge-focused.xml`, `cascade-merge-full.xml`
and `cascade-merge-frontend.xml` remain in host temporary storage for local audit.

### Actual test commands

The Python runs used these environment settings from the repository root:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTEST_ADDOPTS=''
$env:CASCADEROUTER_REQUIRE_NODE_ACCEPTANCE='1'
$taskGuard=Get-Content (Join-Path ([IO.Path]::GetTempPath()) 'cascade-merge-guard-location.json') -Raw | ConvertFrom-Json
$env:PYTHONPATH=$taskGuard.directory
```

`$taskGuard.directory` points to an agent-created test helper, not target content.
The exact bytes exercised by both runs are now retained as
[scripts/pytest_loopback_guard.py](../scripts/pytest_loopback_guard.py), with SHA-256
in the path register. A separate denial probe verified rejection before any DNS
or socket operation. For future runs, use `-p scripts.pytest_loopback_guard` instead
of the temporary module and omit the temporary `PYTHONPATH`; still set the report
environment variable below. The actual commands used the temporary module name:

```powershell
$env:CASCADE_MERGE_NETWORK_REPORT=Join-Path ([IO.Path]::GetTempPath()) 'cascade-merge-focused-network.json'
$taskBase=Join-Path ([IO.Path]::GetTempPath()) ('cascade-merge-focused-'+[guid]::NewGuid().ToString('N'))
$taskReport=Join-Path ([IO.Path]::GetTempPath()) 'cascade-merge-focused.xml'
python -B -m pytest -p no:cacheprovider -p cascade_merge_offline_guard tests/compiler/test_ast_scanner.py tests/unit/test_main_evaluator_regressions.py tests/unit/test_evaluator.py tests/unit/test_metrics.py tests/unit/test_router_optimizer.py tests/unit/test_policy_generator.py tests/unit/test_runtime_router.py tests/unit/test_patch_generator.py tests/unit/test_patch_validator.py tests/unit/test_schemas.py tests/unit/test_ci_summary.py tests/unit/test_release_preflight.py tests/integration/ tests/security/ -q -ra --tb=short --ignore=tests/fixtures/ --junitxml $taskReport --basetemp $taskBase

$env:CASCADE_MERGE_NETWORK_REPORT=Join-Path ([IO.Path]::GetTempPath()) 'cascade-merge-full-network.json'
$taskBase=Join-Path ([IO.Path]::GetTempPath()) ('cascade-merge-full-'+[guid]::NewGuid().ToString('N'))
$taskReport=Join-Path ([IO.Path]::GetTempPath()) 'cascade-merge-full.xml'
python -B -m pytest -p no:cacheprovider -p cascade_merge_offline_guard tests/ -q -ra --tb=short --ignore=tests/fixtures/ --junitxml $taskReport --basetemp $taskBase
```

From `D:\CascadeRouter\frontend`:

```powershell
$env:CASCADE_TEST_TOOLS='C:\Users\LENOVO\AppData\Local\Temp\cascade-ui-tools-mZA2yh'
$taskReport=Join-Path ([IO.Path]::GetTempPath()) 'cascade-merge-frontend.xml'
node --test --test-reporter=spec --test-reporter=junit --test-reporter-destination=stdout --test-reporter-destination=$taskReport tests/*.test.mjs
npm.cmd run typecheck
```

Root verification commands (exit 0):

```powershell
python -B frontend/scripts/sync_contracts.py --check
python -B frontend/scripts/check_offline_inputs.py
python -B -m scripts.source_inventory
python -B -m scripts.check_release_evidence
python -B scripts/release_gates.py
& 'C:\Program Files\Git\bin\bash.exe' -n start.sh
git diff --check
git diff --cached --check
```

`python` resolved to the installed Python 3.14.3 interpreter. No target test suite
was invoked. The full appropriate suite explicitly excludes `tests/fixtures/`.

## Security observations and remaining gates

Both Python test runs recorded **zero non-loopback connection attempts and zero
OpenAI/Nebius/Tavily SDK imports**. The guard covers Python DNS resolution,
TCP connect/connect_ex and UDP sendto; it does not instrument child processes or
constitute an OS sandbox. Child commands were reviewed as first-party CLI/client
acceptance tools. Node tests enforce loopback-only API URLs, reject remote hosts
and redirects, and contact only their temporary local backend when using real HTTP.
Static AST import review found no provider/HTTP SDK imports in retained backend code.

Source-preservation and execution-sentinel tests passed within their stated platform
coverage. No operator target application was executed/imported, no operator target
source was modified and no patch was applied. Tests create and deliberately mutate
isolated attack fixtures to exercise staleness; product operations preserve scanned
input bytes. Test evidence remains explicitly synthetic and cannot authorize
production proposals.

The authoritative [release register](release-gates.json), Phase 4.11 observations
and handoff retain their scoped historical results; this merge's new test counts
are recorded here and in the path register. **Release remains blocked.** Exact-lock
typecheck/build/lint, Python 3.11, clean dependency validation, browser interaction,
genuine approved production evidence, platform filesystem coverage and hosted CI
are not closed by this merge. No build/lint was attempted without prerequisites.
The original hosted CI failure's cause remains unknown. No paid dependency,
provider path, credential, billing setup, external inference or fabricated evidence
was introduced. No push, fetch, pull request, remote merge or co-author attribution
is authorized or performed by this reconciliation.
