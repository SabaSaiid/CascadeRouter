# CascadeRouter Security & Compliance Architecture

## 1. Threat Model & Security Posture

CascadeRouter inspects and optimizes source code repositories that may contain proprietary application logic, multi-turn conversation prompts, and third-party dependency graphs. To operate safely in enterprise, multi-tenant, and CI/CD contexts, CascadeRouter enforces a **Zero-Execution Static Guarantee** coupled with strict secret isolation and deterministic patch verification.

```
       Untrusted Source Repository
                   │
                   ▼
  ┌─────────────────────────────────┐
  │   Zero-Execution AST Scanner    │  <-- No import, eval, or runtime execution
  │  (ast.parse in-memory sandbox)  │
  └────────────────┬────────────────┘
                   │ Call Site AST Nodes
                   ▼
  ┌─────────────────────────────────┐
  │       DAG & Schema Validator    │  <-- Structural validation against schemas.py
  └────────────────┬────────────────┘
                   │
                   ▼
  ┌─────────────────────────────────┐
  │  Nebius & NVIDIA Benchmarking   │  <-- Ephemeral synthetic or isolated assets
  │ (Isolated Credential Vault)     │
  └────────────────┬────────────────┘
                   │ Optimal Routing Config
                   ▼
  ┌─────────────────────────────────┐
  │   Atomic Byte-Span Patcher      │  <-- Syntactic & semantic AST regression check
  │  (Automated Rollback & Backup)  │
  └─────────────────────────────────┘
```

---

## 2. Zero-Execution Static Analysis Guarantees

Many traditional code linters or dynamic profilers inadvertently execute top-level Python modules upon inspection via `importlib` or dynamic introspection. In untrusted or polyglot repositories, this presents serious remote code execution (RCE) vectors.

### Core Safeguards in `ast_scanner.py`
1. **Pure AST Traversal**: Source code is parsed strictly into Python's native `ast.AST` data structures using `ast.parse(source, filename=path, mode='exec')`. At no point is `eval()`, `exec()`, or module loading invoked.
2. **Path Sanitization & Symlink Containment**: All file operations verify canonical paths against the target repository root to prevent directory traversal attacks (`../`).
3. **Deterministic AST Visitor Scope**: The `LLMCallVisitor` class only processes designated call signatures (`openai.chat.completions.create`, `AsyncOpenAI`, LiteLLM aliases). Unrecognized AST branches are traversed without side effects.
4. **Memory-Constrained Parsing**: Input file sizes are capped before parsing to prevent denial-of-service (DoS) via deeply recursive or malformed AST structures.

---

## 3. Secret Isolation & Credential Governance

CascadeRouter interfaces with high-performance model endpoints including **Nebius Token Factory** and **NVIDIA NIM API** endpoints. Maintaining credential boundaries is critical:

| Scope | Protection Mechanism | Description |
|---|---|---|
| **Repository Scanning** | Regex & AST Masking | Scanners explicitly redact inline API keys or authentication headers discovered in AST string literals before emitting telemetry. |
| **Workbench Runtime** | Ephemeral Environment Injection | Credentials (`NEBIUS_API_KEY`, `NVIDIA_API_KEY`) are retrieved exclusively from process environment variables or secure key vaults; they are never persisted to disk or serialized into patch manifests. |
| **Benchmarking Engine** | Isolated Service Worker | Benchmarking jobs run in isolated worker threads with rate-limiting and budget ceilings to prevent runaway billing. |

---

## 4. Atomic Patch Verification & Rollback Protocols

Code modification represents an inherent operational risk. CascadeRouter's `patch_generator.py` and `patch_validator.py` implement multi-tier safety gates:

1. **Pre-Patch Checksumming**: A SHA-256 hash of the target source file is recorded prior to byte modification.
2. **Byte-Span Surgery**: Replacements are applied solely to the exact `[lineno, col_offset, end_lineno, end_col_offset]` ranges representing the model identifier string literal. Surrounding logic, comments, and formatting remain bit-for-bit identical.
3. **Post-Patch AST Re-Validation**:
   - The modified source is parsed anew with `ast.parse()`.
   - Structural AST diffing ensures that the DAG shape, control flow nodes, and variable bindings are isomorphic to the original file, except for the target model string.
4. **Automated Backup & Emergency Reversion**: A `.bak` snapshot is written prior to file write. If post-patch validation or user-configured test suites fail, the original file is restored instantaneously.

---

## 5. Compliance & Data Privacy Alignment

- **SOC2 Type II Readiness**: All compiler transformations are recorded in structured audit logs including user identity, timestamp, original model, target model, and expected cost delta.
- **Data Residency**: Synthetic benchmark payloads never contain live customer PII. Default test assets (`default_assets.py`) utilize scrubbed synthetic domain queries.
- **Non-Destructive Operations**: All operations require explicit dry-run or user approval when operating in interactive workbench mode.
