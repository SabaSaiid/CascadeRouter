# Source-verified patch proposals (Phase 4.7)

`POST /api/patches` proposes literal model-ID changes at scanner-confirmed
OpenAI-compatible `chat.completions.create` calls. It never writes target source,
applies a patch, runs a target test, imports a target module, launches a subprocess
or calls a provider. Static parsing proves syntax and the approved edit boundary;
it does not prove application correctness, model compatibility or a successful migration.

## References and approval

The request accepts an existing `analysis_id`, persisted `optimization_id`, optional
distinct `node_ids` (1–16), and `transformation: "literal_model_id.v1"`. Omitting
nodes selects the optimization plan's nodes. Source text, paths, replacement IDs,
decisions and executable transformations are rejected as extra fields.

Optimization responses now include an immutable `opt_` content identity. Patch
creation and retrieval independently revalidate the optimizer's exact retained
analysis/job, current configuration, approved registry, cases/profile versions,
recording and policy evidence. Existing offline replay reproduces measurements;
it does not run the target application. Approval is checked again after source
verification. Test evidence is rejected even with test benchmark injection enabled.
No production patch capability is claimed without genuine approved recordings.
The implementation tests use explicitly synthetic `test` evidence for pure
transformation/storage checks; they never relabel it as `recorded`.

## Source identity

New complete API scans capture SHA-256, file identity, size and nanosecond metadata
from the scanner's original guarded open handles. A private observer compares
both the initial scanner pass and existing graph reread. The resulting
`cascaderouter.sources.v1` manifest binds the analysis payload digest and root
identity. It is inserted atomically with the immutable analysis. Public scan
responses and diagnostics do not expose the manifest or fingerprints. Partial
scans do not authorize proposals. Historical records have no invented evidence:
they return `409 source_evidence_unavailable`, requiring a new scan and associated
benchmark/optimization references.

Patch creation and review authorize the current repository and perform two fresh
passes through the same guarded scanner. Every source version, root identity,
file set and public call identity must match. The first pass invokes the pure
transformer; the second detects changes during generation. Existing no-follow
reads, opened-handle containment, pinned directories, SDK-shadow checks and all
source/AST/traversal budgets remain active. A final path identity/size/mtime check
also rejects replacement during a read. On Windows, handle ctime is compared
between handle reads and scans; path ctime can have different semantics and is
not compared to handle ctime. POSIX also compares path ctime.

This is bounded, point-in-time evidence, not an atomic filesystem snapshot or a
lock against future edits. Source changes after verification invalidate later
review. Hard-link isolation and hostile operator-owned storage remain outside the
existing local trust boundary.

## Transformation and review artifact

The current literal must equal the approved decision's baseline and the decision
must recommend a different safe model ID for that exact node. Dynamic expressions,
unsupported calls, implicit concatenation, multiline/triple-quoted literals and
unsupported encodings receive explicit omission reasons. Only single-token string
literals encoded as UTF-8, UTF-8 with BOM, or ASCII are supported. String prefixes
`r` and `u` can be replaced by a safely serialized plain string. No wrapper,
fallback, SDK call or workflow is generated.

AST UTF-8 byte columns select the literal span, including Unicode before the
argument. Non-overlapping edits are spliced in memory. BOMs, LF/CRLF/CR newlines,
comments and all unrelated bytes remain identical. The proposed bytes are parsed
with the Python 3.11 grammar and their AST must equal the original AST with only
the approved constant values changed. Proposed files remain within 1 MiB.

The sensitive review artifact is **`literal-spans.v1`**, a bounded textual list of
relative file names, original byte spans, node IDs and removed/added literal
tokens. It deliberately excludes surrounding source lines because those can
contain prompts or credentials. It is a review format, not an executable command
or a unified diff accepted by `git apply`. Full source is not stored or returned.

The manifest includes analysis/source/optimization/policy digests, real UTC
creation time, transformation/schema/format versions, provenance, each file's
original/proposed SHA-256 and every selected node's edit or controlled omission.
Statuses are `proposed`, `partial` and `unavailable`. Zero eligible edits produce
an empty artifact and `unavailable`; partial coverage is explicit. The complete
flag describes requested-node coverage only, never runtime validation.

## API and persistence

`POST /api/patches` returns `201` with ID, status, changed/omitted counts,
completeness and `/api/patches/{patch_id}`. An unavailable proposal still has an
honest manifest when valid recorded evidence exists but no node is editable.
`GET /api/patches/{patch_id}` validates stored digests, reauthorizes references,
revalidates evidence/source and deterministically regenerates the artifact before
returning the immutable manifest and sensitive review text. A stale artifact is
not exposed as current. There is no apply endpoint.

`POST /api/patches/{patch_id}/validate` accepts an existing proposal ID and no
body (or an empty JSON object). Caller source, paths, spans, commands and query
parameters are rejected. It returns `201` for a newly retained static observation,
including `invalid`, `stale` or `unavailable` outcomes; HTTP success describes the
report operation. `result.status` describes validation. Production authorization
still requires recorded, currently approved optimization evidence; test benchmark
injection cannot enable this endpoint. No genuine production evidence was supplied
for the component/transport tests, whose reports retain `test` provenance.

`GET /api/patch-validations/{validation_id}` returns the immutable observation,
including its original `checked_at`, after checking storage/proposal bindings,
current repository scope and current recorded-evidence approval. It does not
refresh source or candidate checks. A historical `source_identity: verified`
describes that observation; it makes no claim about source freshness now. Use
POST again for a new observation. Test reports cannot satisfy production access.

Unknown IDs return `404`; malformed/extra input `422`; forbidden roots `403`;
stale, corrupt or inconsistent inputs `409`; missing production approval/test
evidence `503`; configured capacity exhaustion `429`; oversized bodies `413`.
All use existing fixed errors and request IDs. Diffs and raw exceptions are never
logged. Existing loopback Host/Origin checks, body limits, worker admission and
deadlines apply; this is local service access control, not multi-user authentication.

SQLite schema version 4 transactionally extends versions 1–3 with source manifests,
optimizations and patches. Separate tables have foreign keys, immutable update/
delete triggers and parameterized inserts. Patch ID collisions conflict; identical
optimization content may reuse its ID. Hashes cover canonical records and exact
UTF-8 review bytes; retrieval validates both payload and stored identity columns.
Hashes detect corruption; authenticity comes from trusted local storage and
independent approval validation, never a digest supplied by an HTTP client.

Private manifests are capped at 4 MiB. Review text is capped at 512 KiB and the
configured `max_job_result_bytes`; the entire persisted response must also fit
that configured limit. Optimization and patch counts each use `max_jobs`.
Artifacts stay in the existing trusted database outside every permitted source
root. There is no new storage path, retention deletion, dependency, provider,
credential or frontend change.

## Validation

Use the existing full-suite command in [api-contract.md](api-contract.md#local-test-command).
Focused tests are `tests/unit/test_patch_generator.py`,
`tests/unit/test_patch_storage.py`, `tests/security/test_patch_sources.py` and
`tests/integration/test_patches_api.py`. They use temporary source and state only.
Windows junction tests run locally; unavailable symlink privileges are reported
as explicit skips. Python 3.11 grammar parsing under Python 3.14 does not establish
Python 3.11 runtime success. No production recordings were supplied or manufactured.
