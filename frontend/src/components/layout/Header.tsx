export function Header({ demo, onModeChange }: { demo: boolean; onModeChange: () => void }) {
  return <header className="workbench-header"><div><h1>CascadeRouter IDE</h1><p>Local static analysis and evidence review</p></div>
    <button onClick={onModeChange}>{demo ? 'Leave demo' : 'Open labeled scan demo'}</button>
    <strong role="status">{demo ? 'DEMO — synthetic scan only; backend actions disabled' : 'Local backend mode — no automatic operations'}</strong>
  </header>;
}
