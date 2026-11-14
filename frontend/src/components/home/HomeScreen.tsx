import type { ApiFailure } from '../../services/transport.ts';
import { homeIllustrationFixture } from '../../services/homeIllustration.ts';
import { TierBoard } from '../board/TierBoard.tsx';

export interface HomeScreenProps {
  onTrySampleAgent: () => void;
  onScanOwnRepo: () => void;
  healthError?: ApiFailure;
  onRetryHealth?: () => void;
  recordedRunDate?: string | null;
}

export function HomeScreen({
  onTrySampleAgent,
  onScanOwnRepo,
  healthError,
  onRetryHealth,
  recordedRunDate,
}: HomeScreenProps) {
  const illustration = homeIllustrationFixture;
  const exampleLabel = recordedRunDate
    ? `Recorded run, ${recordedRunDate}`
    : illustration.mandatoryLabel;

  const isOriginRejection =
    healthError?.code === 'invalid_request' || healthError?.kind === 'configuration';

  return (
    <div className="home-screen-wrapper">
      <div className="home-layout">
        {/* Left Column */}
        <section className="home-col-left" aria-labelledby="home-headline">
          <h1 id="home-headline" className="home-headline" style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 600, lineHeight: 1.25 }}>
            Pay frontier-model prices only where you need them.
          </h1>

          <p className="home-paragraph">
            CascadeRouter reads your Python AI app, tests cheaper NVIDIA Nemotron models on each LLM call, and proposes a code change only where the cheaper model passes every check.
          </p>

          <div className="home-cta-row">
            <button
              type="button"
              className="btn-primary home-btn"
              onClick={onTrySampleAgent}
            >
              Try the sample agent
            </button>
            <button
              type="button"
              className="btn-outline home-btn"
              onClick={onScanOwnRepo}
            >
              Scan my own repository
            </button>
          </div>

          {/* Backend unavailable notice: only after a failed check */}
          {healthError && (
            <div className="home-notice-warn" role="status">
              <div>
                {isOriginRejection
                  ? 'The backend rejected this address. Open the app at http://localhost:5173.'
                  : "The local backend isn't responding. Start it with bash start.sh, then press Retry. You can still explore with sample data."}
              </div>
              {!isOriginRejection && onRetryHealth && (
                <button
                  type="button"
                  className="btn-outline"
                  onClick={onRetryHealth}
                  style={{ height: 28, fontSize: 'var(--fs-xs)', padding: '0 10px', flexShrink: 0 }}
                >
                  Retry
                </button>
              )}
            </div>
          )}

          {/* Reassurance line */}
          <div className="home-reassurance">
            <span>Your code is never run.</span>
            <span>Nothing changes until you apply.</span>
            <span>Every change is backed up.</span>
          </div>

          {/* How it works */}
          <div className="home-how-it-works">
            <div className="how-step-row">
              <span className="how-step-label">Scan</span>
              <span className="how-step-desc">Finds every LLM call in your code without running it.</span>
            </div>
            <div className="how-step-row">
              <span className="how-step-label">Benchmark</span>
              <span className="how-step-desc">Runs your test cases on each candidate model and records cost, speed and pass or fail.</span>
            </div>
            <div className="how-step-row">
              <span className="how-step-label">Recommend</span>
              <span className="how-step-desc">Picks the cheapest model that passes every check.</span>
            </div>
            <div className="how-step-row">
              <span className="how-step-label">Patch</span>
              <span className="how-step-desc">Shows the one-line change. A .bak backup is saved before anything is written.</span>
            </div>
          </div>
        </section>

        {/* Right Column: Signature TierBoard Route Board */}
        <section className="home-col-right" aria-labelledby="tier-board-heading">
          <div className="home-board-wrapper" style={{ background: 'var(--sheet)', border: '1px solid var(--rule)', borderRadius: 'var(--r-sheet)', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
            <TierBoard
              isIllustration={true}
              illustrationCalls={illustration.boardCalls}
              mandatoryLabel={exampleLabel}
            />

            {/* Explanatory summary footer line */}
            <div style={{ padding: '12px 16px', background: 'var(--paper)', borderTop: '1px solid var(--rule)', fontSize: 'var(--fs-xs)', color: 'var(--muted)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>{illustration.summarySentence}</span>
              <span style={{ fontSize: '11px' }}>{illustration.footerNote}</span>
            </div>
          </div>
        </section>
      </div>

      {/* Small centred footer line */}
      <footer className="home-footer" style={{ textAlign: 'center', padding: '24px 0', fontSize: 'var(--fs-xs)', color: 'var(--muted)' }}>
        CascadeRouter — local, verifiable LLM routing
      </footer>
    </div>
  );
}
