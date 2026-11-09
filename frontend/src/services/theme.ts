export type ThemeMode = 'dark' | 'light' | 'system';

const STORAGE_KEY = 'cascaderouter_theme';

export function getSavedTheme(): ThemeMode {
  if (typeof window === 'undefined' || !window.localStorage) return 'dark';
  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (saved === 'dark' || saved === 'light' || saved === 'system') {
    return saved;
  }
  return 'dark'; // Default to modern dark developer theme
}

export function applyTheme(theme: ThemeMode): void {
  if (typeof document === 'undefined') return;

  const root = document.documentElement;
  if (theme === 'system') {
    const systemDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.setAttribute('data-theme', systemDark ? 'dark' : 'light');
  } else {
    root.setAttribute('data-theme', theme);
  }

  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.setItem(STORAGE_KEY, theme);
    }
  } catch {
    // Ignore localStorage failures in private browsing
  }
}

export function toggleTheme(current: ThemeMode): ThemeMode {
  const next: ThemeMode = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  return next;
}

