# Zero-cost offline evaluation (Phase 4.4)

The engine evaluates explicitly supplied local cases against captured outputs
from approved recordings. It performs no inference, model download, tokenization,
provider call or outbound request. No verified local model runtime exists in this
repository, so no `local` execution provenance or capability is claimed. Case
origin `local` describes operator-supplied data, not model execution.

No genuine recordings or production case sets were supplied during implementation.
Default production creation remains unavailable. All new fixtures are synthetic,
isolated temporary files with `test` provenance. Negative spoofing tests do not
turn those fixtures into production evidence.

## Approval and registration

Production requires both structural/integrity validation and an independent
operator approval manifest. A document's `approved` or `provenance` field alone
does not authorize execution. Startup configuration is explicit, never dotenv or
environment-based. There is no HTTP endpoint for uploading or approving datasets.

1. Configure `permitted_benchmark_data_roots`: at most 16 existing absolute local
   directories below filesystem roots. Empty policy denies asset loading.
2. Place `benchmark_registry_path` and `benchmark_recordings_path` beneath those
   roots and outside source roots. Storage must be outside source and data roots.
3. Independently review the genuine capture source, input/output associations,
   ground truth, evaluation rules and any historical pricing evidence.
4. Configure `benchmark_approval_manifest_path` in an operator-controlled location
   outside both source and data roots. Protect it from dataset writers using OS
   permissions. Configured paths grant no authority without matching approvals.
5. Pin the exact raw SHA-256 of each reviewed asset in that manifest. Updating
   content requires explicit approval and new immutable versions/recording IDs.

`BenchmarkApprovalManifest` (`cascaderouter.approvals.v1`) contains `approved_by`,
an aware `approved_at`, and bounded `assets`. Each entry has `asset_id`,
`root_index`, canonical relative POSIX `relative_path`, `kind` (`registry` or
`offline_recordings`), required provenance (`local`/`recorded`) and raw-byte
`digest`. It contains no commands, import names or executable predicates.
Duplicate entries, traversal and absolute/UNC/device paths are rejected.

The loader pins directory identities, uses existing Windows sharing guards or
POSIX no-follow directory descriptors, checks opened file identities and bounded
reads, and rechecks identity/containment after reading. Links, junctions and
replacement paths fail closed. Manifest and asset hashes are reverified at job
acceptance and execution. Changed, missing or revoked assets cannot silently
become new evidence. Once a unit sequence begins, it uses the already validated
immutable in-memory document, not mutable files between units.

The manifest proves operator approval of bytes; it cannot mathematically prove
that historical measurements are authentic. Operator-controlled settings, manifest
permissions and genuine capture review remain trust requirements. This is not a
hostile-storage or multi-user sandbox.

## Case and capture contracts

All contracts remain in `backend/schemas.py`; scan/request IDs and job endpoints
are unchanged. Additive optional fields preserve older stored job reads.

`BenchmarkRegistryDocument` keeps `cascaderouter.registry.v1`. Offline case sets
require explicit `provenance` (`local`, or `test` in tests), `validation_version:
offline.v1`, and `content_digest`. Cases have bounded IDs/input, an optional
supplied expected output, and optional `skip_reason: operator_excluded`.
Profiles require a built-in `mechanism`, optional `validation_schema_json` and
`content_digest`; their criteria IDs are metadata, never Python import paths.

Structured digests use `content_digest(model, exclude={"content_digest"})` over
validated default-inclusive JSON fields with sorted keys. They differ from the
manifest's digest of the entire file's raw bytes. A digest can be populated after
constructing a case/profile with its digest omitted; the completed model verifies
the supplied value. Registry file size is at most 1 MiB; case sets have at most
64 cases and profiles at most 16 entries. Input/expected text is bounded to 8,192
characters and 16 KiB UTF-8; schema text is at most 16 KiB.

`OfflineRecordingDocument` uses `cascaderouter.offline-recordings.v1`, replacing
the measurement-only legacy document for production. It contains explicit
provenance/source/timestamp, optional pinned pricing, and per-analysis groups.
Groups bind the original analysis ID/digest, registry digest and case/profile
versions. Every unit has a globally unique `recording_id`, node/model/case
association, input digest, captured output or explicit null, output digest,
traceable `RecordingEvidence` and a structured unit digest. Unknown model IDs
remain unknown and cannot be substituted from a requested model label.

Raw captured output is limited to 8,192 characters/16 KiB. Each dataset has at
most 1,024 units, 16 analysis groups and 32 pricing records, capped at 4 MiB.
Duplicate/conflicting IDs, stale references, mismatched input/output digests,
unknown pricing references and cross-model pricing are rejected. Capture evidence
names a source and an aware timestamp; success flags and arbitrary quality scores
are not accepted as a substitute for evaluating the captured output.

No prompts, expected outputs, captured outputs or full validation schemas enter
ordinary job status, diagnostics or SQLite job payloads. Results contain safe
recording IDs, integrity digests, controlled reason codes and bounded summaries.
No endpoint for raw output retrieval is introduced.

## Deterministic evaluation

`backend/compiler/evaluator.py` supports:

- `exact`: exact Unicode string equality against a supplied expected output.
- `json`: strict JSON parsing plus structured equality against supplied expected
  JSON. Object-key order is ignored; array order matters. JSON numbers `1` and
  `1.0` compare equal, while booleans and numbers remain distinct.
- `json_schema`: the same JSON checks plus an explicitly supplied local schema.

The schema subset supports boolean schemas, `type`, `properties`, `required`,
boolean `additionalProperties`, `items`, `minimum`, `maximum`, `minLength`,
`maxLength`, `minItems`, `maxItems`, `enum` and `const`. `$schema` accepts only the
standard draft-2020-12 identifier as an inert annotation. Unknown keywords,
regex/pattern rules, dynamic validators and **all** `$ref`/`$dynamicRef` mechanisms,
including local references, are rejected. There is no resolver or network fallback.
This is a documented subset, not a full JSON Schema draft implementation.

Strict JSON rejects duplicate keys, non-finite constants, invalid Unicode and
oversized numeric tokens. Evaluation JSON is bounded to depth 16 and 4,096 tree
nodes; schemas to 512 nodes. Asset metadata is separately bounded to depth 24 and
100,000 nodes. No case text, output or rule is imported, evaluated with `eval`/
`exec`, executed as a shell command, or passed to caller-defined Python code.

Statuses are `passed`, `failed`, `skipped`, `inconclusive` and `not_run`. Missing
output is `not_run`; explicit exclusion is `skipped`; missing ground truth is
`inconclusive`. A schema-valid output with no expected output is **not** a quality
pass. Malformed output or a failed required schema check can fail an actual check.
Evaluation-budget exhaustion is inconclusive, rather than fabricated failure or
success. Checks that ran and structural validation status remain separate from
the overall quality decision. Numerical quality scores are not invented.

## Evidence metrics and decimal costs

`backend/compiler/metrics.py` reports planned cases/units, processed units,
integrity-valid captured outputs, completed deterministic checks, and per-status
counts. Counts refer to node/model/case units except `planned_cases`, which counts
distinct selected case IDs. Captured-output integrity does not imply valid JSON
or semantic correctness. `processing_complete` and `evaluation_complete` express
different coverage; skipped, inconclusive and unrun units never enter pass counts.

Latency and TTFT each report units (`ms`), actual sample count, minimum, maximum
and mean from available measurements only. Input/output token totals use their
own known-count populations. Missing observations are excluded, never imputed as
zero. Known observed zero remains available. Each population includes every
processed unit with that measurement available, regardless of evaluation outcome,
including skipped or unrun evaluations when genuine capture measurements exist.
Empty populations have null values with `empty_population`; unsupported arithmetic
has `arithmetic_limit` with its actual sample count. Token totals above the JSON exact-integer budget remain
unavailable. TTFT requires explicit streaming evidence and is never derived from
total latency. Capture latency is bounded to 24 hours; TTFT cannot exceed a known
total latency.

Cost requires both actual token counts and a referenced `PinnedPricing` record
matching the model, provenance, effective time, content digest and source/version.
USD rates are decimal strings per million tokens, capped at 100,000,000 with at
most 12 fractional digits. Calculation uses an isolated decimal context:
`(input_tokens * input_rate + output_tokens * output_rate) / 1000000`.
No floating-point financial arithmetic, live pricing lookup, guessed token count
or estimated charge is used. Missing usage/pricing or a not-yet-effective price
leaves cost unavailable with a controlled reason.

Accurate financial results are additive `calculated_cost.amount_usd` decimal
strings, with pricing reference/digest. The older floating `cost_usd` unit field
remains unavailable for this engine; it is not populated with a rounded proxy.
Aggregate `metrics.cost_usd.total_usd` is a decimal string over available calculated
costs only and reports its sample count. Historical cost calculation incurs no
API charge. No savings, improvement, ranking or quality-parity metrics are added.

## Persistence and lifecycle compatibility

SQLite schema 3 adds `benchmark_versions` to the existing database. Transactional
migrations from versions 1/2 preserve scans/jobs; legacy optional fields normalize
through validated models when comparing immutable plans. Existing complete jobs
remain readable with new fields unavailable. Older queued plans whose registry
or executor identities no longer match are conservatively unrecoverable.

The version catalog stores only kind, ID, version, provenance and content digest.
Same-version content changes are rejected across restarts; new content requires
a new case/profile/pricing version or recording ID. Test and production namespaces
remain distinct. Registration is transactional and capped at 16,384 retained
versions; automatic expiry is not implemented.

`OfflineBenchmarkExecutor` uses the existing fixed workers, finite queue, admission,
idempotency, exclusive ownership and cancellation contract. It verifies the exact
plan/data references before work, checks cancellation/deadlines between units,
and yields only actual processed unit results. Job completion requires iteration,
cleanup and terminal persistence, independent of evaluation quality. Aggregate
failures become controlled errors, never successful jobs or raw tracebacks.

No Python 3.11 runtime, hosted CI, live model benchmark or genuine production
dataset execution is implied by local tests. The installed test runtime is Python
3.14.3. Optimization and patch generation remain outside this phase.
