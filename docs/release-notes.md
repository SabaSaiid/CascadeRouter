# Unreleased preparation record — Phase 4.11

No project release version, release date, tag, built package or publication is
assigned by this record. The frontend package's existing `0.0.0` is not a new
release designation. Release is blocked by the authoritative
[gate register](release-gates.json); passing local tests do not close other gates.

## Implemented capabilities

- Bounded non-executing Python scanning and conservative static dependency graphs,
  separate completeness diagnostics and immutable retained analyses.
- Local persistent benchmark plans/jobs, controlled cancellation/recovery, explicit
  test/recorded provenance, offline captured-output evaluation and truthful metrics.
- Eligibility-first verified-cost optimization, existing deterministic ties and
  backend-authorized policy artifacts; no latency-weighted substitute objective.
- Source-verified `literal-spans.v1` proposals, private version manifests and
  in-memory static syntax/AST validation with integrity-bound historical reports.
- Typed loopback frontend integration, honest errors and missing-evidence states,
  explicit scan demo, guarded request lifecycle and provenance-aware review.
- Opt-in local runtime executor registration and explicit fallback authorization;
  the UI does not activate dispatch, apply source or execute target applications.

## Actual API surface

The current generated OpenAPI exposes these operations (availability remains
subject to configuration, authority, evidence and capacity):

| Method | Path | Workflow |
| --- | --- | --- |
| GET | `/api/health` | Local liveness and capability flags |
| POST | `/api/scan` | Authorized static scan and persistence |
| GET | `/api/analyses/{analysis_id}` | Retained analysis under current policy |
| POST | `/api/benchmark` | Explicit local benchmark plan |
| GET | `/api/runs/{run_id}` | Durable lifecycle/evidence snapshot |
| POST | `/api/runs/{run_id}/cancel` | Cooperative cancellation request |
| POST | `/api/optimize` | Evidence-authorized decisions and policy review |
| POST | `/api/patches` | Reference-only proposal creation |
| GET | `/api/patches/{patch_id}` | Protected canonical proposal review |
| POST | `/api/patches/{patch_id}/validate` | Static observation, not application |
| GET | `/api/patch-validations/{validation_id}` | Historical observation under current authority |

`GET /openapi.json` provides the local generated contract. Default Swagger/ReDoc
HTML and OAuth redirect pages are now disabled: they referenced external CDN
assets. Three HTTP regressions demonstrated and verified this offline correction;
the generated API contract remains unchanged. No documentation package was added.

## Changes in this preparation phase

This phase consolidates release gates, adds non-installing runtime and exact-cache
diagnostics, replaces obsolete provider/sandbox setup guidance, documents actual
trust limits and prepares source identities. Required CI acceptance prerequisites
and final results are recorded in the final handoff. Prior Phase 4.9 and 4.10
reports retain their original scoped results, environments and failure evidence.
The original hosted CI failure cause is still unknown.

The preceding 33 commits across Prompts 2–5 were verified by counting
`0afd041639910030137cfbb45fabfde3ecb29be4..2ff0b949dcbcc050a78e73d984a07d8ac226d034`.
Their accepted work is preserved; no history is rewritten. This phase's commits
and final test outcomes are listed in the handoff, without invented coverage,
performance improvements, paid-provider measurements or production benchmark data.

## Artifact inventory and compatibility

[source-inventory.json](source-inventory.json) records **65 selected committed source
inputs, 621,437 canonical Git-blob bytes**, each with computed SHA-256 and size.
It covers backend source, frontend source/scripts and explicit build/contract inputs.
It excludes operator data, target repositories, tests, changing release records and
built distributions. `python -B -m scripts.source_inventory` verifies the original
commit, current committed inputs and absence of scoped uncommitted changes.
Canonical Git bytes avoid confusing Windows checkout newline conversion with a
different committed artifact. This is not a complete archive or build checksum.

No production bundle/package checksum, package size, new version or release date
is claimed. Re-run inventory generation only after deliberate committed-source
review; hashes do not grant runtime authorization or evidence approval.

Python 3.11 runtime, exact-lock frontend installation/build/lint, clean dependency
resolution, browser interaction/accessibility, suitable-platform filesystem checks,
genuine approved recorded production workflows and hosted CI remain unclosed.
Current observations and remediation live in the gate register, not duplicated
here as a second release verdict. See [SECURITY.md](../SECURITY.md) for trust limits.
