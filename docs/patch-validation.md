# Static patch validation (Phase 4.8)

Static validation checks a stored `literal-spans.v1` proposal against its retained
analysis, approved optimization and private source manifest. It establishes exact
literal boundaries, transient candidate identity, parse success and preservation
of the original AST outside approved model constants. It never applies a patch,
imports a target, runs application tests or proves behavior, model compatibility,
runtime safety, benchmark quality or a successful migration.

## Reference-only API

`POST /api/patches/{patch_id}/validate` accepts no body, JSON `null`, or `{}`.
Source, replacement text, paths, commands, spans and query parameters are rejected.
It returns `201` with `PatchValidationReport`: the report operation succeeded;
`result.status` describes the actual validation outcome. IDs must already exist.
No client-supplied report or candidate is accepted. Production requires the same
recorded-evidence approval as patch creation/review, including revalidation before
and after static checks. Test benchmark injection never grants this authority.

`GET /api/patch-validations/{validation_id}` returns a retained observation after
checking its integrity, proposal association, current repository scope and current
recorded-evidence approval. It accepts no query parameters. It preserves the
original observation, including `checked_at`; it does not rescan current source.
POST again to check freshness now. There is no apply, rollback or target-run route.

Both routes use the existing loopback Host/Origin controls, body/rate limits,
bounded scan-worker admission, deadlines and sanitized fixed errors. This is the
existing local authorization model, not multi-user authentication. Unknown IDs
return `404`, invalid requests `422`, forbidden scope `403`, corrupt storage or
reference associations `409`, unavailable approval `503`, body limits `413`, and
capacity limits `429`. Unexpected internal failures remain `500`, not a successful
validation. A stale validation observation is returned as `201` with `stale`;
existing patch-creation/review operations retain their original `409` behavior.

## Checks and outcomes

The service first validates stored payload/identity digests and reference bindings.
It derives repository paths from the retained analysis, never from review text or
patch file paths. `RepositoryAccess.authorize` and `verify_sources` reuse the
scanner's guarded reads and compare root/file identities, exact bytes, timestamps,
file sets and call identities in two passes. A change in either pass discards all
provisional candidate successes. Missing trustworthy source evidence is unavailable.

For included files the canonical generator checks the stored spans against the
scanner-confirmed model constants and approved decisions **before** splicing.
This rejects stale expected models, wrong byte offsets, overlap, malformed ranges,
unapproved substitutions and out-of-range edits. Empty-width insertions, deletions,
empty model replacements and arbitrary rewriting are outside `literal_model_id.v1`.
Canonical review text and omissions are independently regenerated and compared.

Candidates exist only in memory. Increasing, non-overlapping original byte ranges
avoid offset shifts with multiple edits. The shared checker verifies unrelated
bytes, BOM/newline preservation and the stored proposed SHA-256 before parsing.
It compares the parsed AST with a copy of the original containing only approved
constant changes. A digest mismatch does not receive a passing syntax result.

| Result status | Reason examples | Meaning |
| --- | --- | --- |
| `validated` | `statically_validated` | Every included file passed; no requested nodes were omitted. |
| `partial` | `partial_proposal` | Included files passed; the proposal has explicit omitted nodes. |
| `invalid` | `file_validation_failed`, `proposal_mismatch` | A span, candidate, syntax, AST or canonical-artifact check failed. |
| `stale` | `source_changed` | Source identity/freshness could not match the retained manifest. |
| `unavailable` | `source_evidence_unavailable`, `no_editable_files`, `file_validation_unavailable`, `resource_limit` | Evidence, supported edits or sufficient validation resources are unavailable. |

`structure`, `source_evidence` and `source_identity` describe distinct checks.
Per-file `spans`, `candidate`, `syntax` and `ast_preservation` describe established
results. `not_checked` means no completed determination is asserted;
`not_applicable` is used for unsupported encodings. Unsupported proposal nodes
retain their precise `omissions` reasons, such as `unsupported_encoding` or
`model_unresolved`, rather than receiving invented checks. Omission metadata in a
stale/unavailable observation remains the original proposal's metadata.

Syntax failures expose only a fixed code and bounded parser line/column, never
parser messages, source snippets or absolute filenames. Parser positions follow
Python's diagnostic convention; replacement spans remain original UTF-8 byte
offsets. Resource exhaustion is unavailable, not a quality or syntax failure.
Malformed/corrupt stored artifacts cannot establish a trustworthy report subject
and fail with the existing integrity error instead of a fabricated observation.

## Bounds, persistence and limitations

Existing limits remain: 16 requested edits/nodes and 16 files, 1 MiB original and
candidate files, 100,000 AST nodes, and the scanner's 500-file/25 MiB source budget.
UTF-8, UTF-8 BOM and ASCII literal edits preserve exact unrelated bytes and line
endings. Other encodings retain controlled omissions. No new configuration or
third-party dependency is required.

SQLite schema 5 transactionally extends schemas 1–4 with `patch_validations` in the
existing guarded store outside scan roots. Reports have immutable update/delete
triggers, bounded payloads, foreign keys and exact identity-column checks. Saves
and reloads bind the proposal digest, source-manifest digest, analysis, provenance,
file/candidate identities and omissions. `max_jobs` independently caps report count;
`max_job_result_bytes` caps the complete report. Failed inserts roll back and never
replace the original proposal. Migration creates no backfilled validation success.

`cascaderouter.patch-validation.v1` reports contain validator version, actual UTC
completion time, actual parser runtime version, grammar target and result metadata.
`validation_<sha256>` identifies the canonical observation; hashes prove integrity,
not authorization. No source snapshot, candidate bytes or review text is duplicated
in a report. Identical observations (including time) reuse their identity. Repeated
checks produce deterministic semantic results for identical evidence; a new real
observation time gives a separate immutable report. Proposal state never changes.

Source verification is point-in-time, not an atomic snapshot or a lock against
later edits. Historical verified fields describe the recorded observation, not
current source. Operator-owned storage and hard-link isolation retain the existing
trust limitations. A report grants no permission to execute or apply anything.

The parser retains the compiler's explicit Python 3.11 grammar target. Reports
separately identify the actual interpreter; parsing on Python 3.14 does not prove
Python 3.11 runtime compatibility. Local inspection found Python 3.14.3 and no
usable Python 3.11 installation. Python 3.11 runtime checks, clean-environment
dependency resolution/locking and hosted CI remain outstanding. No interpreter or
dependencies were downloaded. Prior hosted CI failure logs remain unavailable.

## Validation commands

Use the isolated-environment command in [api-contract.md](api-contract.md#local-test-command),
with the existing interpreter and plugin autoload disabled. Focused paths are:

```text
tests/unit/test_patch_candidate.py
tests/unit/test_patch_validator.py
tests/unit/test_patch_validation_schemas.py
tests/unit/test_patch_validation_service.py
tests/unit/test_patch_validation_storage.py
tests/security/test_patch_validation.py
tests/integration/test_patch_validation_api.py
```

Also retain the existing patch-generation/source-integrity suites. Run CascadeRouter's
full `tests/` suite with `--ignore=tests/fixtures/`; never run a scanned application's
tests. Current CI preserves exit codes, skip reasons and JUnit reporting without a
coverage gate. Tests use actual static checks with synthetic `test` evidence.
Transport/unit authority stubs never relabel evidence or enable production patch
proposals. No genuine production benchmark data or hosted validation was claimed.
