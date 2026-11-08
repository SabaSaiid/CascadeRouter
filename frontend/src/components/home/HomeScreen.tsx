import type { ApiFailure } from '../../services/transport.ts';
import { homeIllustrationFixture } from '../../services/homeIllustration.ts';

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
          <h1 id="home-headline" className="home-headline">
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

        {/* Right Column: Example Card */}
        <section className="home-col-right" aria-labelledby="example-card-heading">
          <div className="example-card">
            {/* Card Header */}
            <div className="example-card-header">
              <h2 id="example-card-heading" className="example-card-title">
                {illustration.title}
              </h2>
              <span className="example-card-badge" data-testid="example-mandatory-label">
                {exampleLabel}
              </span>
            </div>

            {/* Three call rows separated by hairlines */}
            <div className="example-calls">
              {illustration.calls.map(call => (
                <div key={call.name} className="example-call-row">
                  <div className="example-call-title-row">
                    <span className="example-call-name">{call.name}</span>
                    <span className={`chip ${call.chip.kind === 'gain' ? 'chip-gain' : 'chip-neutral'}`}>
                      {call.chip.text}
                    </span>
                  </div>

                  {call.now && call.recommended ? (
                    <div className="example-cost-lines">
                      <div className="example-cost-line">
                        <span className="example-cost-label">{call.now.label}</span>
                        <div
                          className="example-cost-bar bar-now"
                          style={{ width: `${call.now.barWidthPx}px` }}
                          aria-hidden="true"
                        />
                        <span className="example-cost-val num">{call.now.cost}</span>
                      </div>
                      <div className="example-cost-line">
                        <span className="example-cost-label">{call.recommended.label}</span>
                        <div
                          className="example-cost-bar bar-rec"
                          style={{ width: `${call.recommended.barWidthPx}px` }}
                          aria-hidden="true"
                        />
                        <span className="example-cost-val num">{call.recommended.cost}</span>
                      </div>
                    </div>
                  ) : (
                    <p className="example-call-note">
                      {call.note}
                    </p>
                  )}
                </div>
              ))}
            </div>

            {/* Closing sentence */}
            <div className="example-card-summary">
              {illustration.summarySentence}
            </div>

            {/* Footer line */}
            <div className="example-card-footer">
              {illustration.footerNote}
            </div>
          </div>
        </section>
      </div>

      {/* Small centred footer line */}
      <footer className="home-footer">
        CascadeRouter — local, verifiable LLM routing
      </footer>
    </div>
  );
}
