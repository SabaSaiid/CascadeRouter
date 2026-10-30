export function Header({ demo, onModeChange }: { demo: boolean; onModeChange: () => void }) {
  return (
    <header className="workbench-header">
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <div
          style={{
            width: '36px',
            height: '36px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, rgba(77, 133, 255, 0.25) 0%, rgba(52, 211, 153, 0.15) 100%)',
            border: '1px solid rgba(77, 133, 255, 0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 0 16px rgba(77, 133, 255, 0.25)',
            flexShrink: 0,
          }}
          aria-hidden="true"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#4D85FF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="7 4 12 9 7 14" />
            <polyline points="13 10 18 15 13 20" />
            <circle cx="5" cy="19" r="1.5" fill="#34D399" stroke="#34D399" />
          </svg>
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h1>CascadeRouter IDE</h1>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 600,
                letterSpacing: '0.04em',
                padding: '2px 7px',
                borderRadius: '4px',
                background: 'rgba(77, 133, 255, 0.14)',
                border: '1px solid rgba(77, 133, 255, 0.3)',
                color: '#8cb1ff',
                fontFamily: 'var(--font-mono)',
              }}
            >
              v1.0
            </span>
          </div>
          <p>Local static analysis and evidence review</p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
        <span
          style={{
            fontSize: '11px',
            padding: '5px 11px',
            borderRadius: 'var(--cr-r-chip)',
            background: 'rgba(77, 133, 255, 0.08)',
            border: '1px solid rgba(77, 133, 255, 0.25)',
            color: '#93B4FF',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            fontFamily: 'var(--font-mono)',
          }}
          title="Benchmarking against Nebius Token Factory on NVIDIA GPUs"
        >
          <span style={{ color: '#4D85FF' }} aria-hidden="true">⚡</span>
          Nebius × NVIDIA Token Factory
        </span>

        <button
          onClick={onModeChange}
          style={{
            background: demo ? 'rgba(251, 191, 36, 0.15)' : 'var(--cr-surface-2)',
            borderColor: demo ? 'rgba(251, 191, 36, 0.4)' : 'var(--cr-line)',
            color: demo ? '#FBBF24' : 'var(--cr-text)',
          }}
        >
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: demo ? '#FBBF24' : '#34D399',
              display: 'inline-block',
              animation: 'cr-pulse-dot 2s infinite ease-in-out',
            }}
            aria-hidden="true"
          />
          {demo ? 'Leave demo' : 'Open labeled scan demo'}
        </button>

        <strong
          role="status"
          style={{
            fontSize: 'var(--cr-fs-xs)',
            fontWeight: 500,
            padding: '6px 12px',
            borderRadius: 'var(--cr-r-chip)',
            background: demo ? 'rgba(251, 191, 36, 0.1)' : 'rgba(52, 211, 153, 0.08)',
            border: demo ? '1px solid rgba(251, 191, 36, 0.25)' : '1px solid rgba(52, 211, 153, 0.2)',
            color: demo ? '#FBBF24' : '#34D399',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: demo ? '#FBBF24' : '#34D399',
            }}
            aria-hidden="true"
          />
          {demo ? 'DEMO — synthetic scan only; backend actions disabled' : 'Local backend mode — no automatic operations'}
        </strong>
      </div>
    </header>
  );
}
