# CascadeRouter IDE

CascadeRouter statically analyzes Python LLM call sites and supported data
dependencies, retains local benchmark evidence, produces evidence-based routing
recommendations, and reviews source-verified model-literal proposals. Normal
operations parse target source without importing or executing it. No patch is
applied, no target tests run, and no hosted inference is provided.

**Release recommendation: blocked from release.** The authoritative
[release-gate register](docs/release-gates.json) distinguishes observed local results
from unverified requirements. The [Phase 4.10 record](docs/phase410-acceptance.md)
and [reproducibility investigation](docs/phase410-reproducibility.md) are historical
evidence, not proof that a clean build or browser journey passed.

## Required local tools and offline prerequisites

Use an approved existing Python 3.11 environment for release validation, Node 24+
for native TypeScript tests, and npm supporting lockfile v3 (preflight minimum 9).
The locally observed Python 3.14.3 runtime is useful for internal testing but does
not satisfy the Python 3.11 release gate. No provider credentials are needed.
Backend dependencies are declared in `requirements.txt`; those ranges are not a
resolved reproducible Python lock. Frontend dependencies use `frontend/package-lock.json`.

From this repository root (PowerShell examples; use `npm.cmd` if policy blocks npm.ps1):

```powershell
python -B -m scripts.release_preflight --profile backend
python -B -m scripts.release_preflight
npm.cmd run check:cache --prefix frontend
python -B scripts/release_gates.py
python -B scripts/release_gates.py --require-ready
```

The backend profile checks backend prerequisites and reports optional frontend
checks separately. The default release profile requires Python 3.11 and the exact
installed frontend tools. It exits nonzero when prerequisites are blocked. Cache
inventory checks local bytes against locked hashes, including optional OS/CPU
artifacts; not every optional artifact is required on every platform. It never
contacts a registry. Register validation alone checks bookkeeping; `--require-ready`
also fails while required release gates remain open. None of these commands builds
the UI, runs acceptance tests, installs anything, or certifies release readiness.

For developers who **already have approved local artifacts**, the following is an
offline provisioning procedure, **not a clean installation verified in this task**:

```powershell
# Use an existing approved interpreter/environment and trusted wheelhouse.
python -m pip install --no-index --find-links C:\ApprovedWheelhouse -r requirements.txt
python -m pip check
npm.cmd ci --prefix frontend --offline --ignore-scripts --no-audit --fund=false
```

Stop if artifacts are missing. Do not enable downloads or change locked versions to
force success. Install scripts are disabled; any platform-specific script genuinely
needed must be reviewed and supplied as an approved offline step. Re-run preflight,
then the actual typecheck/build/lint/tests. Supplemental cached tools are optional
validation aids and cannot close exact-lock build or clean-environment gates.

## Configure and run the backend

Create an explicit non-secret JSON configuration naming existing authorized roots
and an existing operator-owned storage directory **outside every scan root**:

```json
{
  "permitted_repository_roots": ["C:/CascadeData/projects/sample-app"],
  "storage_directory": "C:/CascadeData/state",
  "bind_host": "127.0.0.1",
  "bind_port": 8000
}
```

These example directories are not created by the UI. With installed prerequisites:

```powershell
python -B -m backend.main --help
python -B -m backend.main --config C:\CascadeData\backend.json
```

The supported entry point binds loopback and disables proxy-header trust. Without
`--config`, startup exposes health with scan/retrieval disabled. No dotenv values
are loaded. See the [API contract](docs/api-contract.md) for configuration, limits,
errors and durable storage. Do not start a target application or its test runner.

## Configure and run the frontend

After exact offline dependencies are installed:

```powershell
$env:VITE_API_BASE_URL='http://127.0.0.1:8000'
npm.cmd run dev --prefix frontend
```

Open the local UI at `http://127.0.0.1:5173`. The API address defaults to the value
above; only explicit loopback HTTP origins are accepted. The development port is
strict. No remote API, credentials, telemetry or Google Fonts request is required.
See [frontend setup and workflows](frontend/README.md) for controls and recovery.
A failed API call remains a failure; it never silently selects demo results.

## Available workflows

- Scan an authorized repository or retrieve its immutable analysis. Review findings,
  component completeness, diagnostics and actual data-dependency edges. Missing
  edges do not establish independence or execution order.
- Select a finding and explicitly supply configured local model/case/profile IDs.
  Submit, retrieve, refresh or cancel a local benchmark job. Test evidence stays
  TEST; recorded provenance still needs backend approval. Missing metrics stay
  unavailable, never zero. Processing completion does not mean quality passed.
- Request optimization of a completed run with its matching analysis. The backend
  determines eligibility and verified cost; no frontend quality threshold, latency
  weighting or synthetic savings is substituted. Policy review does not activate it.
- Create/review an authorized stored proposal in `literal-spans.v1`, request static
  validation, then retrieve a historical report. These actions never apply a patch.
  Static validity does not establish behavior; historical reports do not rescan now.

No provider invocation, target regression runner, automatic patch application,
rollback, commit/push control, public hosted demo or model/case catalog endpoint is
implemented. Missing genuine approved evidence remains a controlled restriction.
The scan demo is explicitly synthetic and disables backend operations.

## Run the trusted repository tests

From this root, with installed test prerequisites:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTEST_ADDOPTS=''
$taskTemp=Join-Path ([IO.Path]::GetTempPath()) ('cascade-tests-'+[guid]::NewGuid().ToString('N'))
python -B -m pytest -p no:cacheprovider tests/ -q -ra --tb=short --ignore=tests/fixtures/ --basetemp $taskTemp
npm.cmd test --prefix frontend
npm.cmd run typecheck --prefix frontend
npm.cmd run lint --prefix frontend
npm.cmd run build --prefix frontend
python -B frontend/scripts/sync_contracts.py --check
python -B frontend/scripts/check_offline_inputs.py
```

Use a fresh temporary base per run. These commands test CascadeRouter; they do not
run `tests/fixtures/sample_repo` as an application. For a focused local API check,
replace `tests/` with `tests/integration/test_frontend_local_backend.py`. That test
uses isolated source/storage and real loopback HTTP. Native TypeScript acceptance
requires Node 24+. Browser interaction, clean environments, Python 3.11, genuine
approved production evidence and hosted CI require separate recorded validation.

[Patch validation](docs/patch-validation.md), [offline benchmarks](docs/offline-benchmark.md),
[optimization](docs/optimization.md), and [local runtime routing](docs/runtime-routing.md)
document their detailed contracts. The Git history retains the earlier hackathon
vision; the old hosted-provider setup, rates and sandbox-success claims are not
current operator instructions. No release tag or published package is implied.

[Security model and limits](SECURITY.md) distinguish tested repository guards,
point-in-time static checks and trusted local storage from a complete OS sandbox
or independent security certification.

The [unreleased preparation notes](docs/release-notes.md) inventory available APIs,
compatibility caveats and selected committed-source artifacts. Verify those source
identities with `python -B -m scripts.source_inventory`; this is not a build check.
