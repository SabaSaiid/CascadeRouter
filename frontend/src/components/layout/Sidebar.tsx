import type { ReactNode } from 'react';

export interface SidebarProps {
  currentView: 'home' | 'workbench' | 'analytics';
  onSelectView: (view: 'home' | 'workbench' | 'analytics') => void;
  onOpenTour: () => void;
  onOpenSettings: () => void;
  onOpenTerms: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  callCount?: number;
}

export function Sidebar({
  currentView,
  onSelectView,
  onOpenTour,
  onOpenSettings,
  onOpenTerms,
  collapsed,
  onToggleCollapse,
  callCount,
}: SidebarProps) {
  return (
    <aside
      className={`app-sidebar${collapsed ? ' collapsed' : ''}`}
      aria-label="Application Navigation"
    >
      <div>
        <div className="sidebar-section">
          {!collapsed && <span className="sidebar-heading">Navigation</span>}

          <SidebarButton
            active={currentView === 'home'}
            onClick={() => onSelectView('home')}
            collapsed={collapsed}
            title="Overview & Introduction"
            icon={
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                <polyline points="9 22 9 12 15 12 15 22" />
              </svg>
            }
            label="Overview"
          />

          <SidebarButton
            active={currentView === 'workbench'}
            onClick={() => onSelectView('workbench')}
            collapsed={collapsed}
            title="Interactive Compiler Workbench"
            badge={callCount !== undefined && callCount > 0 ? String(callCount) : undefined}
            icon={
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
            }
            label="Workbench"
          />

          <SidebarButton
            active={currentView === 'analytics'}
            onClick={() => onSelectView('analytics')}
            collapsed={collapsed}
            title="FinOps Cost & Latency Analytics"
            icon={
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <line x1="18" y1="20" x2="18" y2="10" />
                <line x1="12" y1="20" x2="12" y2="4" />
                <line x1="6" y1="20" x2="6" y2="14" />
              </svg>
            }
            label="FinOps Analytics"
          />
        </div>

        <div className="sidebar-section" style={{ borderTop: '1px solid var(--rule)', marginTop: 8 }}>
          {!collapsed && <span className="sidebar-heading">Learning & Trust</span>}

          <SidebarButton
            onClick={onOpenTour}
            collapsed={collapsed}
            title="Interactive Visual Guide: How CascadeRouter Works"
            icon={
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
            }
            label="How It Works"
          />

          <SidebarButton
            onClick={onOpenTerms}
            collapsed={collapsed}
            title="Security Policy & Zero Code Execution Guarantee"
            icon={
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            }
            label="Security & Terms"
          />
        </div>
      </div>

      <div className="sidebar-footer">
        <SidebarButton
          onClick={onOpenSettings}
          collapsed={collapsed}
          title="Compiler Settings & Theme Configuration"
          icon={
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          }
          label="Settings"
        />

        <button
          type="button"
          className="sidebar-collapse-btn"
          onClick={onToggleCollapse}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? '→' : '← Collapse'}
        </button>
      </div>
    </aside>
  );
}

function SidebarButton({
  active,
  onClick,
  collapsed,
  title,
  icon,
  label,
  badge,
}: {
  active?: boolean;
  onClick: () => void;
  collapsed: boolean;
  title: string;
  icon: ReactNode;
  label: string;
  badge?: string;
}) {
  return (
    <button
      type="button"
      className={`sidebar-btn${active ? ' active' : ''}`}
      onClick={onClick}
      title={title}
      aria-current={active ? 'page' : undefined}
    >
      <span className="sidebar-btn-icon">{icon}</span>
      {!collapsed && (
        <>
          <span className="sidebar-btn-label">{label}</span>
          {badge && <span className="sidebar-btn-badge">{badge}</span>}
        </>
      )}
    </button>
  );
}

