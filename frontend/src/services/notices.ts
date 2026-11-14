export interface NoticeItem {
  id: string;
  text: string;
  createdAt: number;
}

export const MAX_NOTICES = 2;
export const NOTICE_DISMISS_MS = 6000;

export class NoticeQueue {
  private notices: NoticeItem[] = [];
  private listeners: Set<(notices: NoticeItem[]) => void> = new Set();
  private timers: Map<string, ReturnType<typeof setTimeout>> = new Map();

  subscribe(listener: (notices: NoticeItem[]) => void): () => void {
    this.listeners.add(listener);
    listener(this.notices);
    return () => {
      this.listeners.delete(listener);
    };
  }

  getNotices(): NoticeItem[] {
    return [...this.notices];
  }

  addNotice(text: string): string {
    const id = `notice_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    const item: NoticeItem = {
      id,
      text,
      createdAt: Date.now(),
    };

    // If already at cap, drop the oldest notice and clear its timer
    if (this.notices.length >= MAX_NOTICES) {
      const dropped = this.notices.shift();
      if (dropped) {
        const t = this.timers.get(dropped.id);
        if (t) {
          clearTimeout(t);
          this.timers.delete(dropped.id);
        }
      }
    }

    this.notices.push(item);

    // Auto-dismiss after 6s
    const timer = setTimeout(() => {
      this.dismiss(id);
    }, NOTICE_DISMISS_MS);
    this.timers.set(id, timer);

    this.notify();
    return id;
  }

  dismiss(id: string): void {
    const idx = this.notices.findIndex(n => n.id === id);
    if (idx >= 0) {
      this.notices.splice(idx, 1);
      const timer = this.timers.get(id);
      if (timer) {
        clearTimeout(timer);
        this.timers.delete(id);
      }
      this.notify();
    }
  }

  clear(): void {
    for (const timer of this.timers.values()) {
      clearTimeout(timer);
    }
    this.timers.clear();
    this.notices = [];
    this.notify();
  }

  private notify(): void {
    const snapshot = [...this.notices];
    for (const listener of this.listeners) {
      listener(snapshot);
    }
  }
}

export const globalNoticeQueue = new NoticeQueue();
