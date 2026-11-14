export function SecurityTermsScreen() {
  return (
    <div className="doc-page-container">
      <div className="doc-page-content" style={{ maxWidth: 720 }}>
        <h2 className="doc-page-title">Security and terms</h2>
        <p className="doc-page-lead">
          CascadeRouter is designed for safe local execution and transparency. All security properties described here reflect the verified guarantees documented in the repository.
        </p>

        <section className="doc-section">
          <h3 className="doc-section-title">Zero code execution</h3>
          <p className="doc-section-text">
            Your repository code is never executed, imported, or run during scanning, benchmarking, optimization, or patch validation. Analysis is performed strictly through static Python AST parsing.
          </p>
        </section>

        <section className="doc-section">
          <h3 className="doc-section-title">Loopback-only communication</h3>
          <p className="doc-section-text">
            The local backend binds strictly to the numeric loopback interface (<code>127.0.0.1</code>). It disables proxy-header trust and enforces explicit host checks. No external network server is exposed.
          </p>
        </section>

        <section className="doc-section">
          <h3 className="doc-section-title">Automatic backup before patching</h3>
          <p className="doc-section-text">
            Before applying any patch to disk, CascadeRouter automatically generates an exact <code>.bak</code> rollback copy of the target file. Patches perform precise byte-span replacement of model identifier literals only.
          </p>
        </section>

        <section className="doc-section">
          <h3 className="doc-section-title">Confirmation before apply</h3>
          <p className="doc-section-text">
            No source file is modified automatically. You review the unified diff and explicitly choose to apply the proposed patch. You can review all changed lines before confirming.
          </p>
        </section>

        <section className="doc-section">
          <h3 className="doc-section-title">Controlled error privacy</h3>
          <p className="doc-section-text">
            API diagnostics and error messages omit private input values, source snippets, and absolute filesystem paths. All state is maintained locally in private operator-owned SQLite storage.
          </p>
        </section>
      </div>
    </div>
  );
}
