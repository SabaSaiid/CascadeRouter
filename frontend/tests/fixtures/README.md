These fixtures are schema-validated outputs from CascadeRouter's own deterministic
test pipeline. All job, optimization, patch and validation evidence is `test`;
the scan's public repository label is sanitized and its source is `mock`.
They are never an API fallback, approved production data, or permission to patch
or execute a target. No captured application output or private source manifest is
included. Legacy illustrative fixtures are retained separately when the old UI is
retired. Tests may deliberately corrupt copies to exercise rejection paths.

`invalid-job-patches.json` describes negative mutations of the test job, including
forged provenance, contradictory outcomes and impossible coverage. Those copies
must be rejected by both Pydantic and the client; they are never displayed or used
as recorded evidence.
