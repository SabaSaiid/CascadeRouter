# Phase 4.10 reproducibility investigation

Verified locally on 2026-10-29. No dependencies, browsers or interpreters were
installed or downloaded. Package versions, package-lock.json and requirements.txt
are unchanged. This is an evidence inventory, not a successful production build.

## Static inputs

`python -B frontend/scripts/check_offline_inputs.py` returns exit 0:
`status=consistent`, 121 locked packages, 20 source files, no errors, and
`production_build_verified=false`. It compares root dependency declarations,
ordinary exact/caret/tilde versions, required scripts, integrity declarations and
static source import specifiers. It does not resolve dependencies, run lifecycle
scripts, validate bundler plugins or replace TypeScript/Vite compilation.
Its 16 focused tests cover real inputs and deliberately inconsistent copies,
including an attempted `|| true` test-command substitution.

## Exact local artifacts

A read-only probe used npm's already installed `cacache` module and the existing
local cache. For each locked resolved tarball key it read local bytes and checked
SHA-512 against the unchanged lockfile. **37 of 121 matched; 84 returned ENOENT.**
Direct missing artifacts include Vite 8.3.5, Oxlint 1.89.0, React 19.3.1 and
ReactDOM 19.3.1. The cache directory is the local npm-cache under AppData/Local.
No registry request was made. The Phase 4.9 failed offline `npm ci` need not be
repeated to establish that these exact artifacts remain absent.

Actual commands `npm.cmd run build --prefix frontend` and
`npm.cmd run lint --prefix frontend` each returned exit 1: `tsc` and `oxlint`,
respectively, were unavailable in the project installation. They did not run to
completion. Lock consistency does not change these failed/unavailable checks.

The existing supplemental tool directory from Phase 4.9 remains available. Tests
and a typecheck use TypeScript 6.0.3 and React/ReactDOM 19.3.0 from that directory,
with `CASCADE_TEST_TOOLS` explicitly set. This is not the locked React runtime and
does not establish reproducible installation, lint or production bundle success.

## Browser and interpreter inventory

Chrome and Edge executables are present in their ordinary Program Files paths.
The local ms-playwright directory contains ffmpeg/winldd support artifacts, no
browser build, and a link to a package path that no longer exists. No project
browser driver/test dependency or built application bundle is available. No
browser interaction or layout test was run; no cloud browser or download was used.
The real TypeScript-client/loopback API tests are contract integration, not a
browser-to-backend journey. React server-rendered accessibility checks are also
not browser keyboard/focus or assistive-technology certification.

The actual interpreter is Python 3.14.3. Python 3.11 was not found on PATH, in the
inspected ordinary per-user/system Python311 locations, or PythonCore registry
inventory. The per-user Programs/Python inventory contains Python314. The
WindowsApps py.exe launcher could not be executed. No Python 3.11 check ran;
the compiler's Python 3.11 grammar target is not that runtime validation.

Node is 24.16.0 and npm is 11.13.0. Clean-environment backend resolution/locking
and exact-lock frontend installation remain outstanding. Hosted CI has not run
in this task, and the cause of the historical hosted failure remains unknown.
