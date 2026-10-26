import type { FC } from 'react';
import { Check, Database, Radio, TriangleAlert } from 'lucide-react';
import type { DataSourceMode } from '../../types';

interface DataSourceBadgeProps {
  mode: DataSourceMode;
  onModeChange?: (mode: DataSourceMode) => void;
  interactive?: boolean;
}

const MODES: DataSourceMode[] = ['live', 'recorded', 'mock'];

const CONFIG = {
  live: {
    label: 'Live — Nebius',
    icon: Radio,
    dot: 'bg-[var(--cr-pass)] animate-pulse',
    className: 'text-[var(--cr-pass)]',
  },
  recorded: {
    label: 'Recorded run',
    icon: Database,
    dot: 'bg-[var(--cr-accent)]',
    className: 'text-[var(--cr-accent)]',
  },
  mock: {
    label: 'Mock data',
    icon: TriangleAlert,
    dot: 'bg-[var(--cr-warn)]',
    className: 'text-[var(--cr-warn)]',
  },
} satisfies Record<DataSourceMode, { label: string; icon: typeof Check; dot: string; className: string }>;

export const DataSourceBadge: FC<DataSourceBadgeProps> = ({
  mode,
  onModeChange,
  interactive = true,
}) => {
  const cfg = CONFIG[mode];
  const Icon = cfg.icon;

  const cycle = () => {
    if (!onModeChange) return;
    const next = MODES[(MODES.indexOf(mode) + 1) % MODES.length];
    onModeChange(next);
  };

  return (
    <button
      id="data-source-badge"
      type="button"
      onClick={interactive ? cycle : undefined}
      disabled={!interactive || !onModeChange}
      title="Toggle data source (Live / Mock / Recorded)"
      className="btn-ghost flex items-center gap-2 text-[var(--cr-muted)] cr-transition"
    >
      <span className={`inline-block w-2 h-2 rounded-full ${cfg.dot}`} aria-hidden="true" />
      <Icon className={`w-3.5 h-3.5 ${cfg.className}`} aria-hidden="true" />
      <span className={`text-xs ${cfg.className}`}>{cfg.label}</span>
    </button>
  );
};
