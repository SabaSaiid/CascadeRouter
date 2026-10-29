# Phase 4.10 acceptance and residual risks

Starting gate: `D:\CascadeRouter`, branch `integration/cascade-router-zero-cost`,
clean HEAD `39c11dc31bdf76e207a70e5afcb961fc432669e2`. Existing commits were preserved.
This record distinguishes tested behavior from missing release evidence. It does
not declare production readiness or a successful production benchmark journey.

## Verified boundary coverage

| Area | Evidence and actual limit |
| --- | --- |
| Client -> scan -> graph -> durable analysis | `tests/integration/test_frontend_local_backend.py` adds full/partial cases through real HTTP and the actual TypeScript client. Returned dependency edges, diagnostics, private-manifest availability and reopened analysis agree. Temporary source bytes/file sets remain unchanged. |
| Client -> local jobs -> metrics -> optimizer | `test_client_benchmark_acceptance.py` exercises actual test-only offline evaluation, passed/failed outcomes, idempotency, missing measurements, persistence and `test_evidence` optimization restrictions. No synthetic output is approved production evidence. |
| Proposal/report authority | `test_client_artifact_authorization.py` stores actual internally checked **test** artifacts, then verifies 4 real API denials (503) without approval stubs. Restarting with different roots verifies 9 scope denials (403), including historical reports. Existing observations remain unchanged. |
| HTTP boundary | `test_client_http_boundaries.py` verifies streamed chunked 413, malformed/origin 422, repository escape 403 and peer-based 429 despite forwarding-header spoofing. Denials establish no stored success and cannot open the excluded test source. Errors/logs omit test-private inputs. |
| Lifecycle/restart | `test_client_job_recovery.py` verifies queued safe recovery, interrupted running/cancelling work, concurrent cancellation, terminal immutability and corrupted identity rejection after restart. Bounded admission may return 429; tests retain that contract. |
| Frontend evidence integrity | `test_frontend_job_evidence.py` and `frontend/tests/job-contract.test.mjs` share 12 negative vectors. Pydantic and the client reject contradictory summaries, provenance, coverage, unit evaluations, times and failure states. No parser failure becomes mock success. |
| Storage/migrations/source races | Existing storage, job, patch-storage and validation-storage tests retain transactional migration/reload checks. `tests/security/test_patch_sources.py` and `test_patch_validation.py` retain identity substitution, double-pass source-change, rollback, cancellation and approval-revocation checks. No new production authority stub or filesystem bypass was added. |
| UI/accessibility | Existing operation and React server-rendered tests cover cancellation, stale publication, native forms/buttons, labels, status announcements, demo restrictions and all validation outcomes/history wording. They do not establish browser layout, keyboard focus or assistive-technology behavior. |
| CI reports | `tests/unit/test_ci_summary.py` verifies actual case counts, nested suites, missing/malformed/ambiguous reports, failed-step outcomes, contradiction detection and append behavior. Both actual local JUnit reports also pass the shared formatter. |

Only the frontend response parser required product corrections. A focused Node
regression failed before the first fix: field shape alone permitted contradictory
job facts that the backend model rejects. A later three-case regression also
failed: constructor, __proto__ and toString matched inherited schema members,
allowing forbidden extra JSON fields. The parser now checks the existing job
cross-field contract and uses own schema properties only. Neither finding
demonstrated prototype pollution or a backend authorization bypass. The backend
already rejects these records; no backend permission, optimizer objective, tie
rule, source guard or schema changed. Other changes address test/reporting gaps.

The test harness was corrected to existing semantics when initial assumptions were
wrong: partial scans have unavailable private manifests, simple deterministic
executors need not provide aggregate metrics, concurrent work may hit bounded
admission, and terminal SQL records are immutable. The corruption fixture modifies
only an isolated temporary database and restores its exact schema transactionally
before serving requests; runtime read-integrity checks must reject it. Assertions
were not suppressed and production guards were not relaxed.

## Independent commit gates

All focused gates below passed with exit 0, zero failures/errors/skips. Counts are
per invocation and overlap; they must not be added together as unique coverage.

| Commit | Accepted unit | Focused gate |
| --- | --- | --- |
| `3980fed` | Scan/graph/partial persistence across the actual client | `tests/integration/test_frontend_local_backend.py`: 3 passed |
| `a8f8e7e` | Benchmark provenance and durable optimizer restrictions | `tests/integration/test_client_benchmark_acceptance.py`: 2 passed |
| `b082636` | Proposal/history authority and policy restart | `tests/integration/test_client_artifact_authorization.py`: 1 passed |
| `0fcd2c5` | Real-wire request and peer boundaries | `tests/integration/test_client_http_boundaries.py`: 2 passed |
| `22298d4` | Recovery, concurrent cancellation and corruption | `tests/integration/test_client_job_recovery.py`: 5 passed |
| `a74034f` | Confirmed frontend evidence parser defect | Differential Pydantic vectors: 12 passed; Node job/transport/operation: 43 passed; live benchmark/recovery: 7 passed; frontend: 75 passed; supplemental typecheck: 0 diagnostics |
| `c21d2f5` | Offline lock/script/import consistency and artifact inventory | `tests/unit/test_offline_frontend_inputs.py`: 16 passed; static audit CLI exit 0, build explicitly unverified |
| `ff7e550` | Confirmed inherited schema-member lookup defect | Node schema/transport: 29 passed; authoritative frontend contract tests: 13 passed |
| Final acceptance commit | CI result visibility and this risk register | `tests/unit/test_ci_summary.py`: 13 passed; actual frontend CI command: 78 passed; full repository gate below |

Focused Python invocations use the interpreter and isolated settings below, with
`-B -m pytest -p no:cacheprovider <listed paths> -q --tb=short -rs --basetemp <fresh temp>`
(the differential-vector invocation omitted `-rs`). Node focused invocation:
`node --test frontend/tests/job-contract.test.mjs frontend/tests/transport.test.mjs frontend/tests/operation.test.mjs`.

## Final locally executed gates

PowerShell from the repository root, with Python 3.14.3, Node 24.16.0, npm 11.13.0:

```powershell
$taskPython = 'C:\Users\LENOVO\AppData\Local\Programs\Python\Python314\python.exe'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTEST_ADDOPTS = ''
$taskTemp = Join-Path ([IO.Path]::GetTempPath()) ('cascade-p410-final-'+[guid]::NewGuid().ToString('N'))
$taskJUnit = Join-Path ([IO.Path]::GetTempPath()) 'cascade-phase410-backend.xml'
& $taskPython -B -m pytest -p no:cacheprovider tests/ -q -ra --tb=short --ignore=tests/fixtures/ --junitxml $taskJUnit --basetemp $taskTemp
```

**1,230 passed, 0 failed, 0 errors, 8 skipped; exit 0**, 47.38 seconds and 4,140
dependency deprecation warnings. Actual JUnit category counts:

| Category | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| Compiler | 221 | 0 | 0 | 3 |
| Integration/API | 133 | 0 | 0 | 0 |
| Security | 78 | 0 | 0 | 5 |
| Unit | 798 | 0 | 0 | 0 |

Six skips require Windows symlink privileges (3 scanner, 1 benchmark assets, 1 patch
sources, 1 repository access); two repository-access cases require POSIX namespace
replacement which Windows pins prevent. No new acceptance test was skipped.

Frontend CI test command, actually executed from `frontend/`:

```powershell
$env:CASCADE_TEST_TOOLS = 'C:\Users\LENOVO\AppData\Local\Temp\cascade-ui-tools-mZA2yh'
$taskJUnit = Join-Path ([IO.Path]::GetTempPath()) 'cascade-phase410-frontend.xml'
node --test --test-reporter=spec --test-reporter=junit --test-reporter-destination=stdout --test-reporter-destination=$taskJUnit tests/*.test.mjs
```

**78 passed, 0 failed/errors/cancelled/skipped; exit 0**. The final
`npm.cmd test --prefix frontend` invocation also passed 78 with exit 0. `npm.cmd run typecheck --prefix frontend` returned exit 0 with zero
diagnostics. These use the existing supplemental TypeScript 6.0.3/React 19.3.0 tools,
not the locked production runtime. CI uses installed project dependencies instead.

`python -B frontend/scripts/sync_contracts.py --check` and
`python -B frontend/scripts/check_offline_inputs.py` returned exit 0. The actual
JUnit files were rendered with `python -B scripts/summarize_tests.py --label Backend|Frontend
--report <actual report> --outcome success --output <temporary summary>`; both
returned exit 0 and reported respectively 1238/1230/0/0/8 and 78/78/0/0/0
for total/passed/failures/errors/skips. YAML parses locally; no test step has
continue-on-error, summaries run with always(), and build failure remains separate.
Hosted execution is unverified, and no historical CI failure cause was inferred.

Build and lint each returned **exit 1**, with missing `tsc` and `oxlint`. The exact
cache evidence and browser/interpreter inventory are in
[phase410-reproducibility.md](phase410-reproducibility.md). No install or lock
substitution was attempted. Whitespace/staged-diff checks passed before each commit.

## Prioritized unresolved release evidence

1. **P1 — Exact-lock production build/lint:** 84 locked tarballs absent locally;
   both commands exit 1. Static consistency and supplemental checks do not close
   this gate. Approved offline artifacts must be provisioned separately.
2. **P1 — Browser interaction:** no usable project driver or built exact-lock app
   was available. Chrome/Edge presence is not test coverage. Browser-to-backend,
   keyboard focus, layout and assistive-technology acceptance remain unverified.
3. **P1 — Supported interpreter and clean environment:** Python 3.11 was not run;
   the actual runtime is 3.14.3. Backend clean dependency resolution/locking and
   clean exact-lock frontend installation remain unverified. The inherited Python
   requirements are ranges, not a reproducible resolved lock.
4. **P1 — Genuine approved recorded workflow:** no genuine approved production
   evidence was available. Test artifacts correctly receive 503. No positive
   authorized production proposal/validation/history journey is claimed; pure
   test-only static checks and denial coverage do not grant that approval.
5. **P2 — Hosted/platform evidence:** hosted CI was not run; the historical failure
   cause is unknown. Eight OS-dependent tests remain skipped locally. Run the
   intended environments before closing these gates.
6. **P2 — Documented trust limits:** source verification is point-in-time and uses
   two guarded passes, not an atomic filesystem snapshot or universal race-proof
   sandbox. Storage is trusted operator-owned state; configured roots are a local
   authorization policy, not per-user tenant ownership or protection from every
   privileged filesystem attacker. See the source/patch API contracts.

No additional unresolved product defect was demonstrated by these checks. That is
not evidence that all defects are absent. No target application was executed or
imported, no workflow wrote target source, and no proposal was applied. Intentional
attack/input mutations were confined to isolated test fixtures. Production code,
schemas, storage migrations, dependency declarations, lockfile and original sample
fixtures remain unchanged except the identified frontend parser corrections.
No paid/provider integration, credentials, telemetry, external request, fabricated
production evidence, co-author trailer, push or history rewrite was introduced.
