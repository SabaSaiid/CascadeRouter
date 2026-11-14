import { useEffect, useRef } from 'react';
import type { AppRoute } from '../../services/router.ts';
import type { PipelineStep } from '../../services/pipeline.ts';
import { APP_VERSION } from '../../version.ts';

export interface SidebarProps {
  currentRoute: AppRoute;
  onNavigate: (route: AppRoute) => void;
  pipelineSteps: PipelineStep[];
  onSelectPipelineStep: (stepKey: 'scan' | 'benchmark' | 'recommend' | 'patch') => void;
  recentResultsCount: number;
  isOpenOnMobile: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({
  currentRoute,
  onNavigate,
  pipelineSteps,
  onSelectPipelineStep,
  recentResultsCount,
  isOpenOnMobile,
  onCloseMobile,
}: SidebarProps) {
  const drawerRef = useRef<HTMLDivElement>(null);

  // Focus trap and Esc key handler when mobile drawer is open
  useEffect(() => {
    if (!isOpenOnMobile || !drawerRef.current) return;
    const container = drawerRef.current;
    const focusable = container.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length > 0) {
      focusable[0].focus();
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCloseMobile();
        return;
      }
      if (e.key === 'Tab') {
        const elements = Array.from(container.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        ));
        if (elements.length === 0) return;
        const first = elements[0];
        const last = elements[elements.length - 1];
        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpenOnMobile, onCloseMobile]);

  const navItemClass = (route: AppRoute) =>
    `sidebar-nav-item${currentRoute === route ? ' active' : ''}`;

  return (
    <>
      {/* Drawer backdrop for viewports < 1280px */}
      {isOpenOnMobile && (
        <div
          className="sidebar-backdrop"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        ref={drawerRef}
        className={`app-sidebar${isOpenOnMobile ? ' drawer-open' : ''}`}
        aria-label="Application Navigation"
        role={isOpenOnMobile ? 'dialog' : 'complementary'}
        aria-modal={isOpenOnMobile ? 'true' : undefined}
      >
        {/* Top: Wordmark */}
        <div className="sidebar-header">
          <button
            type="button"
            className="sidebar-wordmark-btn"
            onClick={() => {
              onNavigate('home');
              if (isOpenOnMobile) onCloseMobile();
            }}
            aria-label="CascadeRouter Home"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--navy)"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polyline points="7 4 12 9 7 14" />
              <polyline points="13 10 18 15 13 20" />
              <circle cx="5" cy="19" r="1.5" fill="var(--gain)" stroke="var(--gain)" />
            </svg>
            <span className="sidebar-wordmark-text">CascadeRouter</span>
          </button>

          {isOpenOnMobile && (
            <button
              type="button"
              className="sidebar-close-btn"
              onClick={onCloseMobile}
              aria-label="Close navigation menu"
            >
              Close
            </button>
          )}
        </div>

        {/* Pipeline block */}
        <div className="sidebar-pipeline-block" aria-label="Pipeline workflow progress">
          <div className="sidebar-pipeline-title">Pipeline</div>
          <div className="sidebar-pipeline-steps">
            {pipelineSteps.map(step => (
              <button
                key={step.key}
                type="button"
                className={`pipeline-step-btn ${step.dot}`}
                aria-current={step.dot === 'current' ? 'step' : undefined}
                onClick={() => {
                  onSelectPipelineStep(step.key);
                  if (isOpenOnMobile) onCloseMobile();
                }}
                title={`Open workbench: ${step.name}`}
              >
                <div className="pipeline-step-head">
                  <span className={`pipeline-step-dot ${step.dot}`} aria-hidden="true" />
                  <span className="pipeline-step-name">{step.name}</span>
                </div>
                <div className="pipeline-step-summary">{step.summary}</div>
                {step.progressPercent !== undefined && (
                  <div
                    className="pipeline-progress-bar"
                    role="progressbar"
                    aria-valuenow={step.progressPercent}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`Benchmarking progress: ${step.progressPercent}%`}
                  >
                    <div
                      className="pipeline-progress-fill"
                      style={{ width: `${step.progressPercent}%` }}
                    />
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Divider */}
        <hr className="sidebar-divider" />

        {/* Navigation list */}
        <nav className="sidebar-nav" aria-label="Main views">
          <button
            type="button"
            className={navItemClass('home')}
            onClick={() => {
              onNavigate('home');
              if (isOpenOnMobile) onCloseMobile();
            }}
            aria-current={currentRoute === 'home' ? 'page' : undefined}
          >
            Home
          </button>

          <button
            type="button"
            className={navItemClass('workbench')}
            onClick={() => {
              onNavigate('workbench');
              if (isOpenOnMobile) onCloseMobile();
            }}
            aria-current={currentRoute === 'workbench' ? 'page' : undefined}
          >
            Workbench
          </button>

          <button
            type="button"
            className={navItemClass('history')}
            onClick={() => {
              onNavigate('history');
              if (isOpenOnMobile) onCloseMobile();
            }}
            aria-current={currentRoute === 'history' ? 'page' : undefined}
          >
            <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
              <span>Recent results</span>
              <span className="sidebar-nav-count">({recentResultsCount})</span>
            </span>
          </button>
        </nav>

        {/* Bottom pinned items */}
        <div className="sidebar-footer">
          <nav className="sidebar-footer-nav" aria-label="Secondary navigation">
            <button
              type="button"
              className={navItemClass('settings')}
              onClick={() => {
                onNavigate('settings');
                if (isOpenOnMobile) onCloseMobile();
              }}
              aria-current={currentRoute === 'settings' ? 'page' : undefined}
            >
              Settings
            </button>

            <button
              type="button"
              className={navItemClass('guide')}
              onClick={() => {
                onNavigate('guide');
                if (isOpenOnMobile) onCloseMobile();
              }}
              aria-current={currentRoute === 'guide' ? 'page' : undefined}
            >
              How it works
            </button>

            <button
              type="button"
              className={navItemClass('security')}
              onClick={() => {
                onNavigate('security');
                if (isOpenOnMobile) onCloseMobile();
              }}
              aria-current={currentRoute === 'security' ? 'page' : undefined}
            >
              Security and terms
            </button>
          </nav>

          <div className="sidebar-version-note">
            Version {APP_VERSION}, local backend
          </div>
        </div>
      </aside>
    </>
  );
}
