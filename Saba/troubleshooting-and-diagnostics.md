# Operational Troubleshooting & AST Conflict Runbook

## 1. Quick Diagnostic Decision Tree

When encountering unexpected behavior during scanning, benchmarking, or patch application, follow this operational triage workflow:

```
  Symptom Detected
         │
         ├──► Scanner fails to detect call site?
         │    └─► Check Section 2: AST Detection Issues
         │
         ├──► Benchmarks timing out or returning 401/403?
         │    └─► Check Section 3: Provider API Authentication & Endpoints
         │
         ├──► Patch fails validation or syntax error generated?
         │    └─► Check Section 4: AST Byte-Span Conflict Resolution
         │
         └──► Out-of-memory or high latency on Nebius / NVIDIA?
              └─► Check Section 5: Memory & Concurrency Tuning
```

---

## 2. AST Detection Issues

### Issue: Call site in custom function is ignored by scanner
- **Root Cause**: The caller uses a dynamic wrapper or factory function rather than directly importing `OpenAI`, `AsyncOpenAI`, or `litellm`.
- **Diagnostic Command**:
  ```bash
  python -m backend.main --mode scan --target path/to/file.py --verbose
  ```
- **Remedy**: Annotate the wrapper method or update `backend/compiler/ast_scanner.py` to add your custom wrapper identifier to `SUPPORTED_CLIENT_WRAPPERS`.

---

## 3. Provider API Authentication & Endpoints

### Issue: HTTP 401 Unauthorized against Nebius Token Factory
- **Root Cause**: Missing or malformed `NEBIUS_API_KEY` environment variable.
- **Verification**:
  ```bash
  curl -s -o /dev/null -w "%{http_code}" https://api.tokenfactory.nebius.com/v1/models \
    -H "Authorization: Bearer $NEBIUS_API_KEY"
  ```
- **Remedy**: Verify your API key has active credit in the Nebius console and verify that `.env` is loaded before starting the backend daemon.

### Issue: HTTP 429 Too Many Requests against NVIDIA NIM
- **Root Cause**: Exceeding concurrency rate limits on free-tier or shared NIM API keys.
- **Remedy**: Lower the benchmark concurrency parameter in `backend/config.py`:
  ```python
  BENCHMARK_CONCURRENCY = 2  # Reduce from default 5
  ```

---

## 4. AST Byte-Span Conflict Resolution & Rollback

### Issue: Patch causes `SyntaxError` after applying modifications
- **Root Cause**: The target file was modified concurrently between the AST scan phase and the patch application phase, shifting byte offsets.
- **Automated Rollback**:
  ```bash
  # Restore automatically generated backup file
  cp target_file.py.bak target_file.py
  ```
- **Remedy**: Re-run the AST scan to refresh character offsets before applying patches. `patch_validator.py` will catch any syntax regression prior to finalization.

---

## 5. Memory & Concurrency Tuning

For high-throughput multi-agent test suites:
- Ensure `uvloop` is installed for maximum asynchronous I/O event loop efficiency.
- Configure connection pool limits in `backend/services/repository_access.py` to prevent local file descriptor exhaustion during extensive repository crawls.
