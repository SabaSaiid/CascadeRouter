import type { NoticeItem } from '../../services/notices.ts';

export interface CompletionNoticesProps {
  notices: NoticeItem[];
  onDismiss: (id: string) => void;
}

export function CompletionNotices({ notices, onDismiss }: CompletionNoticesProps) {
  if (notices.length === 0) return null;

  return (
    <div
      className="completion-notices-container"
      role="region"
      aria-label="Call completion notices"
    >
      {notices.slice(-2).map(item => (
        <div
          key={item.id}
          className="completion-notice-card"
          role="status"
          aria-live="polite"
        >
          <div className="completion-notice-text">
            {item.text}
          </div>
          <button
            type="button"
            className="completion-notice-dismiss"
            onClick={() => onDismiss(item.id)}
            aria-label="Dismiss completion notice"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
