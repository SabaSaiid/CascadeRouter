# Static AST Scanner Technical Specification

CascadeRouter's static scanner discovers, catalogs, and instruments LLM call sites across Python repositories without executing code.

## Scanner Safety Model

Dynamic analysis (such as inspecting objects at runtime or using import hooks) risks executing untrusted initialization code, establishing network sockets, or mutating local state. CascadeRouter enforces a **Strict Zero-Execution Guarantee**:

- Files are read strictly as UTF-8 text.
- Abstract Syntax Trees are parsed exclusively via `ast.parse(source, filename=path)`.
- No `eval()`, `exec()`, or `importlib.import_module()` is permitted during repository indexing.

## Call Site Signatures Detected

The scanner recognizes standard client invocation forms across popular LLM client libraries:

### 1. OpenAI SDK (v1.x)
```python
# Synchronous Chat Completion
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.7
)

# Asynchronous Chat Completion
response = await async_client.chat.completions.create(
    model="gpt-4o",
    messages=history
)
```

### 2. LiteLLM Proxy / SDK
```python
# Synchronous LiteLLM
response = litellm.completion(
    model="azure/gpt-4o",
    messages=messages
)

# Async LiteLLM
response = await litellm.acompletion(
    model="bedrock/claude-3-5-sonnet",
    messages=messages
)
```

## Pattern Matching Architecture

The AST traversal is implemented via a subclass of `ast.NodeVisitor`:

```python
class LLMCallVisitor(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.call_sites = []

    def visit_Call(self, node: ast.Call):
        # Detect client.chat.completions.create
        if self._is_openai_chat_completion(node.func):
            model_info = self._extract_keyword_arg(node, "model")
            self.call_sites.append({
                "type": "openai",
                "lineno": node.lineno,
                "col_offset": node.col_offset,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
                "end_col_offset": getattr(node, "end_col_offset", node.col_offset),
                "model_arg": model_info,
            })
            
        # Detect litellm.completion / acompletion
        elif self._is_litellm_completion(node.func):
            model_info = self._extract_keyword_arg(node, "model")
            self.call_sites.append({
                "type": "litellm",
                "lineno": node.lineno,
                "col_offset": node.col_offset,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
                "end_col_offset": getattr(node, "end_col_offset", node.col_offset),
                "model_arg": model_info,
            })
            
        self.generic_visit(node)
```

## Variable Binding and Value Resolution

When the `model` argument is not an inline string literal (e.g., `model=MODEL_NAME` or `model=config["model"]`), the scanner uses lexical scope resolution:

1. **Local Scope**: Checks previous `ast.Assign` statements within the same function definition.
2. **Module Scope**: Checks top-level variable definitions in the module file.
3. **Fallback Marker**: If the variable originates from an external import or dynamic config file, the scanner tags the call site as `DYNAMIC_VARIABLE`, prompting the user for confirmation prior to generating patches.
