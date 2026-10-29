# Phase 4.11 final acceptance and handoff

**Recommendation: blocked from release.** Further internal testing can continue,
but passing available tests does not establish production readiness. The single
authoritative [release-gate register](release-gates.json) records each requirement,
procedure, observation, environment, status, impact and remediation. The
[structured observations](phase411-observations.json) reconcile current results;
the preceding [Phase 4.9](phase49-validation.md) and
[Phase 4.10](phase410-acceptance.md) records remain historical evidence.

## Repository identity and scope

The starting gate verified `D:\CascadeRouter`, a clean working tree, branch
`integration/cascade-router-zero-cost` and exact HEAD
`2ff0b949dcbcc050a78e73d984a07d8ac226d034`. All existing history is preserved.
The final full run tested committed base
`aeeb76144e9a2971a51db884138c307c2f00e99d` plus the evidence checker and its tests
in the working tree. Subsequent changes only reconcile observations and documentation.
Resolve the final handoff commit and branch using:

```powershell
git branch --show-current
git log -1 --format='%H %s' -- docs/phase411-handoff.md
git status --short
```

The final response supplies the resulting full HEAD; embedding a commit's own hash
in its contents is not possible. No tag, release date, new version, built package
or publication is assigned. [Source inventory](source-inventory.json) verifies
65 selected committed inputs and 621,437 canonical Git-blob bytes with SHA-256
identities. It excludes tests, release records, operator data, scanned repositories
and built distributions; it is not a package checksum or proof of build success.

## Actual final validation

Windows environment: Python **3.14.3**, Node **24.16.0**, npm **11.13.0**.
Installed backend metadata: FastAPI 0.115.6, Uvicorn 0.34.0, Pydantic 2.12.5 and
PyYAML 6.0.3. No optional pytest-cov installation or coverage result is claimed.
Frontend renderer/typecheck tests reused existing supplemental TypeScript 6.0.3
and React/ReactDOM 19.3.0. These are not the exact production dependency installation.

| Check | Actual outcome | Exit |
| --- | --- | --- |
| One final repository run | 1,280 passed; 0 failed; 0 errored; 8 skipped; 53.89 seconds | 0 |
| Final frontend run | 86 passed; 0 failed/errored/cancelled/skipped | 0 |
| Supplemental TypeScript | 0 diagnostics; exact-install gate remains blocked | 0 |
| Generated OpenAPI/frontend contract | Matched | 0 |
| Static offline input audit | 121 locked packages, 20 source files checked; not a build | 0 |
| Canonical source inventory | 65 selected inputs unchanged | 0 |
| Backend preflight | Required backend prerequisites present | 0 |
| Release / CI-backend preflights | Python 3.11 absent; release also lacks exact frontend installation | 1 / 1 |
| Read-only cache inventory | 37 SHA-512-verified tarballs; 84 missing of 121; 0 corrupt/unavailable/invalid | 1 |
| Register / observation consistency | Bookkeeping valid, recommendation remains blocked | 0 / 0 |
| Register with `--require-ready` | Required gates still open | 1 |
| Exact-lock production build / lint | Blocked; prerequisites absent, not executed this phase | not run |

Counts were reconciled with actual JUnit reports. Repository categories are compiler
221 passed/3 skipped, integration 144 passed/0 skipped, security 78 passed/5 skipped
and unit 837 passed/0 skipped. All have zero failures/errors. There were 3,778
deprecation warnings; they were not hidden or treated as compatibility proof.

The eight skips are three compiler symlink cases reporting errno 22, three security
symlink cases reporting Windows privilege error 1314, and two POSIX namespace
replacement cases that cannot perform their rename while Windows pins are held.
No required Node acceptance case skipped in the final run. The separate platform
gate remains open; available security tests do not prove universal guard correctness.

The JUnit files are retained as `cascade-phase411-backend.xml` and
`cascade-phase411-frontend.xml` in the host temporary directory. Their actual
SHA-256 hashes and counts are in the structured observations. They are diagnostic
artifacts, not published release artifacts. Temporary fixtures and local storage
are isolated from target repositories; renderer-owned build directories are now
removed after use, with boundary/identity checks. Diagnostic pytest artifacts and
small supplemental typecheck declarations remain in host temporary storage.

### Exact final commands executed

From `D:\CascadeRouter`, using the actual installed interpreter:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTEST_ADDOPTS=''
$env:CASCADEROUTER_REQUIRE_NODE_ACCEPTANCE='1'
$taskTemp=Join-Path ([IO.Path]::GetTempPath()) ('cascade-p411-final-'+[guid]::NewGuid().ToString('N'))
$taskJUnit=Join-Path ([IO.Path]::GetTempPath()) 'cascade-phase411-backend.xml'
& 'C:\Users\LENOVO\AppData\Local\Programs\Python\Python314\python.exe' -B -m pytest -p no:cacheprovider tests/ -q -ra --tb=short --ignore=tests/fixtures/ --junitxml $taskJUnit --basetemp $taskTemp
```

From `D:\CascadeRouter\frontend`:

```powershell
$env:CASCADE_TEST_TOOLS='C:\Users\LENOVO\AppData\Local\Temp\cascade-ui-tools-mZA2yh'
$taskJUnit=Join-Path ([IO.Path]::GetTempPath()) 'cascade-phase411-frontend.xml'
node --test --test-reporter=spec --test-reporter=junit --test-reporter-destination=stdout --test-reporter-destination=$taskJUnit tests/*.test.mjs
npm.cmd run typecheck
```

The supplemental path was an existing local tool directory. It was not extracted,
installed or downloaded in this phase and is not a portable setup instruction.
From the root, the following verification commands were also executed (each exit 0):

```powershell
python -B frontend/scripts/sync_contracts.py --check
python -B frontend/scripts/check_offline_inputs.py
python -B -m scripts.source_inventory
python -B scripts/release_gates.py
python -B -m scripts.check_release_evidence
git diff --check
```

Here `python` resolved to the Python 3.14.3 interpreter identified above. Other
observed commands and deliberate blocked outcomes were:

```powershell
python -B -m scripts.release_preflight --profile backend  # exit 0
python -B -m scripts.release_preflight --profile release  # exit 1
python -B -m scripts.release_preflight --profile ci-backend  # exit 1
npm.cmd run --silent check:cache --prefix frontend  # exit 1
python -B scripts/release_gates.py --require-ready  # exit 1
```

No clean install, production build or lint was attempted again without its
prerequisites. The preceding Phase 4.10 exit-1 attempts remain historical evidence.
No browser automation or hosted CI success is claimed. Evidence reconciliation
checks bookkeeping; it neither executes gates nor authenticates observations.

## Meaningful changes and independent acceptance

All focused gates below passed before their commits; expected blocked diagnostic
commands and red regression demonstrations are separate from acceptance success.

| Commit | Purpose and acceptance |
| --- | --- |
| `d815b9a9bff776ef775fb657af92681a649c7bf7` | Authoritative release register and validator; 9 Python cases passed |
| `4e86dc4136aa752dca15506866c6a6f8125eef34` | Non-installing required/optional runtime/tool preflight; 9 Python cases passed |
| `fa5f034e84b21f73689fd1746558bce3d9b9f7c1` | Locked offline cache byte-integrity diagnostics; 7 Node cases passed, actual inventory 37/84 |
| `2152eccaca53f6f6721e6958369e95caed22ef16` | Accurate local setup replacing obsolete provider instructions; 4 startup/client cases, CLI help, scripts and link checks passed |
| `1ce62b79ba239b7d5de0df543fe1d42ccebf82af` | Tested security/trust limits replacing sandbox claims; 4 source/static/history cases and links passed |
| `9f4361cc1a744d5be9db071084975ae0760b26ea` | Disable CDN-backed default FastAPI documentation; 3 regressions failed before fix, then docs/contract 16 passed, drift check passed |
| `4aa823a1f869c8f2ddf1026a4ae54e017dbd0cd5` | Verified source inventory and factual release notes; 12 Python cases and actual identity check passed |
| `aeeb76144e9a2971a51db884138c307c2f00e99d` | Required CI Node acceptance and owned renderer-temp cleanup; missing-prerequisite regression failed before fix, then 20 Python and 3 Node cases passed |
| Commit containing this handoff | Observation consistency guards; 9 Python cases passed before the single final full run; final receipts/counts and documentation reconciled |

The previous 33 commits across Prompts 2–5 were verified against the range in
[release notes](release-notes.md). This phase adds nine meaningful units, bringing
the sequence to 42. No existing commit was amended, reset, duplicated or rewritten.

## Verified behavior and trust limits

The final suite exercised static scanning, source/graph retention, typed loopback
API calls, controlled unavailability, truthful benchmark/optimizer restrictions,
durable recovery, proposal/source-version checks, validation/history integrity and
frontend evidence/status rendering. Source-preservation and execution-sentinel
tests passed within their documented platform scope. Test-only injected evidence
is still test provenance and does not grant production proposal authority.

Two confirmed gaps were corrected: default FastAPI `/docs` and `/redoc` HTML
referenced external CDN assets, and required Node acceptance could previously
silently skip when CI prerequisites were missing. Those HTML/OAuth routes now
return 404 while local `/openapi.json` remains available; required acceptance now
fails explicitly when unavailable. No public Pydantic schema was replaced.

No target application was executed or imported, no operator target source was
modified, and no patch was applied. Tests create and deliberately mutate isolated
attack fixtures to verify stale-source rejection; CascadeRouter operations preserve
their scanned input bytes. Normal candidate work remains in memory and
static validation establishes neither behavioral correctness nor current freshness
when a historical report is retrieved. Path guards and trusted storage are not a
complete OS sandbox or independent security audit; see [SECURITY.md](../SECURITY.md).

No provider integration, external inference/search request, credential, telemetry,
dependency download, fabricated evidence, dependency-version change or co-author
attribution was introduced. Only loopback tests contacted the local backend.
No push, fetch, merge, rebase, cherry-pick, branch change, PR or release occurred.

## Prioritized remaining work

1. **P1 — exact frontend artifacts and clean dependency validation.** Provision
   approved offline platform-relevant locked artifacts, install in a clean approved
   environment, then run exact-lock typecheck, build and lint. The inventory includes
   optional OS/CPU tarballs; not all 121 are needed on every platform. Do not change
   locked versions or enable downloads to hide missing packages. Backend requirements
   remain ranges: approve a reproducible resolved/hash-locked set separately.
2. **P1 — Python 3.11.** No runnable interpreter was found on PATH, in ordinary
   per-user/system Python311 locations, or the repository environment. Use an already
   approved Python 3.11 environment to run compatibility and clean-install checks;
   Python 3.14 success is not that evidence.
3. **P1 — real browser acceptance.** Provide approved local driver/tooling and the
   exact built UI. Exercise keyboard/focus, errors, cancellation, provenance and
   proposal/validation/history flows. Browser binaries alone and SSR/native-markup
   assertions do not establish browser accessibility coverage.
4. **P1 — genuine approved recorded evidence.** An authorized operator must supply
   genuine local cases/recordings and approvals to validate the production
   benchmark-to-proposal journey. Synthetic success must never close this gate.
5. **P2 — filesystem coverage and hosted CI.** Run the eight skipped filesystem
   cases on suitable authorized Windows/POSIX environments. Separately authorize a
   future hosted run and retain commit-specific logs. Current commits were not run
   by GitHub Actions; the original hosted failure cause remains unknown.

These are unresolved release requirements, not permissions to install, publish or
weaken controls in this task. The gate register remains the status authority.
