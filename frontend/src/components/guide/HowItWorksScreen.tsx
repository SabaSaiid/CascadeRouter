export function HowItWorksScreen() {
  return (
    <div className="doc-page-container">
      <div className="doc-page-content" style={{ maxWidth: 720 }}>
        <h2 className="doc-page-title">How CascadeRouter works</h2>
        <p className="doc-page-lead">
          CascadeRouter helps you route individual LLM calls in your Python application to smaller, faster, and more affordable models without sacrificing quality.
        </p>

        <section className="doc-section">
          <h3 className="doc-section-title">1. Scan</h3>
          <p className="doc-section-text">
            CascadeRouter inspects your Python code using static Abstract Syntax Tree (AST) analysis. It locates every call to OpenAI SDK or LiteLLM without executing your code or importing modules. It identifies the current model string, parameters, and variable dependencies.
          </p>
        </section>

        <section className="doc-section">
          <h3 className="doc-section-title">2. Benchmark</h3>
          <p className="doc-section-text">
            Test cases run against each candidate model through local or recorded inference. Measurements record cost, latency, time to first token, and check pass rates. Every result is tied to exact input digests for verification.
          </p>
        </section>

        <section className="doc-section">
          <h3 className="doc-section-title">3. Recommend</h3>
          <p className="doc-section-text">
            The compiler evaluates candidate models against your quality threshold. It selects the lowest-cost model that passes every check. If no cheaper alternative satisfies all assertions, the call stays on its original baseline model.
          </p>
        </section>

        <section className="doc-section">
          <h3 className="doc-section-title">4. Patch</h3>
          <p className="doc-section-text">
            When you choose to apply a recommendation, CascadeRouter writes the exact one-line model change to your source file. A timestamped <code>.bak</code> backup copy is always saved before writing to disk, ensuring a clean rollback path at all times.
          </p>
        </section>
      </div>
    </div>
  );
}
