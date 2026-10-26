import type { FC } from 'react';
import { Radio, Database, ShieldAlert } from 'lucide-react';
import type { DataSourceMode } from '../../types';

interface DataSourceBadgeProps {
  mode: DataSourceMode;
  onModeChange?: (mode: DataSourceMode) => void;
  interactive?: boolean;
}

export const DataSourceBadge: FC<DataSourceBadgeProps> = ({
  mode,
  onModeChange,
  interactive = true,
}) => {
  const getBadgeConfig = () => {
    switch (mode) {
      case 'live':
        return {
          label: 'LIVE NEBIUS API',
          icon: Radio,
          className: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20',
          dotClass: 'bg-emerald-400 animate-pulse',
        };
      case 'recorded':
        return {
          label: 'RECORDED REPLAY',
          icon: Database,
          className: 'bg-blue-500/10 text-blue-400 border-blue-500/30 hover:bg-blue-500/20',
          dotClass: 'bg-blue-400',
        };
      case 'mock':
      default:
        return {
          label: 'OFFLINE MOCK FIXTURE',
          icon: ShieldAlert,
          className: 'bg-amber-500/10 text-amber-300 border-amber-500/30 hover:bg-amber-500/20',
          dotClass: 'bg-amber-400',
        };
    }
  };

  const config = getBadgeConfig();
  const Icon = config.icon;

  if (!interactive || !onModeChange) {
    return (
      <div
        id="data-source-badge"
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${config.className}`}
        title="Active Telemetry Data Mode"
      >
        <span className={`w-2 h-2 rounded-full ${config.dotClass}`} />
        <Icon className="w-3.5 h-3.5" />
        <span>{config.label}</span>
      </div>
    );
  }

  return (
    <div className="relative inline-block text-left" id="data-source-selector">
      <div
        className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-semibold border cursor-pointer transition-colors ${config.className}`}
        onClick={() => {
          const nextMode: DataSourceMode =
            mode === 'live' ? 'mock' : mode === 'mock' ? 'recorded' : 'live';
          onModeChange(nextMode);
        }}
        title="Click to toggle data source mode (Live / Mock / Recorded)"
      >
        <span className={`w-2 h-2 rounded-full ${config.dotClass}`} />
        <Icon className="w-3.5 h-3.5" />
        <span>{config.label}</span>
        <span className="text-[10px] opacity-60 underline ml-0.5">Toggle</span>
      </div>
    </div>
  );
};
