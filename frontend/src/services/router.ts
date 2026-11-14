export type AppRoute =
  | 'home'
  | 'workbench'
  | 'history'
  | 'settings'
  | 'guide'
  | 'security';

export const ROUTE_HASHES: Record<AppRoute, string> = {
  home: '#/',
  workbench: '#/workbench',
  history: '#/history',
  settings: '#/settings',
  guide: '#/guide',
  security: '#/security',
};

export const ROUTE_TITLES: Record<AppRoute, string> = {
  home: 'CascadeRouter - Home',
  workbench: 'CascadeRouter - Workbench',
  history: 'CascadeRouter - Recent results',
  settings: 'CascadeRouter - Settings',
  guide: 'CascadeRouter - How it works',
  security: 'CascadeRouter - Security and terms',
};

export const VIEW_HEADINGS: Record<AppRoute, string> = {
  home: 'Home',
  workbench: 'Workbench',
  history: 'Recent results',
  settings: 'Settings',
  guide: 'How it works',
  security: 'Security and terms',
};

export function parseRoute(hash: string): AppRoute {
  const clean = hash.trim().toLowerCase();
  if (clean === '#/workbench' || clean === '#workbench') return 'workbench';
  if (clean === '#/history' || clean === '#history') return 'history';
  if (clean === '#/settings' || clean === '#settings') return 'settings';
  if (clean === '#/guide' || clean === '#guide') return 'guide';
  if (clean === '#/security' || clean === '#security') return 'security';
  return 'home';
}

export function navigateTo(route: AppRoute): void {
  const targetHash = ROUTE_HASHES[route];
  if (typeof window !== 'undefined') {
    if (window.location.hash !== targetHash) {
      window.location.hash = targetHash;
    }
    updateDocumentTitle(route);
  }
}

export function updateDocumentTitle(route: AppRoute): void {
  if (typeof document !== 'undefined') {
    document.title = ROUTE_TITLES[route] ?? 'CascadeRouter';
  }
}
