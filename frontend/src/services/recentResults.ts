export interface RecentResultEntry {
  id: string;
  analysis_id?: string;
  run_id?: string;
  optimization_id?: string;
  patch_id?: string;
  repo_folder: string;
  date: string;
  calls_found: number;
  calls_can_move: number;
  saving_percentage: string;
  statuses: ('Scanned' | 'Benchmarked' | 'Patched')[];
  summary: string;
}

export const RECENT_RESULTS_STORAGE_KEY = 'cascaderouter.recent_results.v1';
export const RECENT_RESULTS_CAP = 20;

/**
 * Extracts only the terminal directory/folder name from any path.
 * Guaranteed never to return an absolute path or path with parent directories.
 */
export function sanitizeRepoFolderName(rawPath: string): string {
  if (!rawPath || typeof rawPath !== 'string') return 'repository';
  // Normalize windows backslashes
  const normalized = rawPath.replace(/\\+/g, '/').trim();
  const parts = normalized.split('/').filter(Boolean);
  if (parts.length === 0) return 'repository';
  const lastPart = parts[parts.length - 1];
  // Ensure no slashes remain
  return lastPart.replace(/[/\\:]/g, '') || 'repository';
}

/**
 * Safely reads the list of recent results from localStorage.
 * Returns empty array if storage is disabled, unavailable or contains invalid JSON.
 */
export function getRecentResults(): RecentResultEntry[] {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return [];
    const raw = window.localStorage.getItem(RECENT_RESULTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(0, RECENT_RESULTS_CAP);
  } catch {
    return [];
  }
}

/**
 * Saves a new entry or updates an existing entry by analysis_id / id.
 * Caps stored items at 20.
 * Silently catches and ignores errors if storage is unavailable or quota is exceeded.
 */
export function saveRecentResult(
  entry: Omit<RecentResultEntry, 'id'> & { id?: string }
): RecentResultEntry | null {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return null;

    const existing = getRecentResults();
    const cleanFolder = sanitizeRepoFolderName(entry.repo_folder);

    const record: RecentResultEntry = {
      id: entry.id || `res_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      analysis_id: entry.analysis_id,
      run_id: entry.run_id,
      optimization_id: entry.optimization_id,
      patch_id: entry.patch_id,
      repo_folder: cleanFolder,
      date: entry.date,
      calls_found: entry.calls_found,
      calls_can_move: entry.calls_can_move,
      saving_percentage: entry.saving_percentage,
      statuses: entry.statuses,
      summary: entry.summary,
    };

    // If an entry with the same analysis_id or id exists, merge/update it
    const index = existing.findIndex(
      e => (entry.analysis_id && e.analysis_id === entry.analysis_id) || (entry.id && e.id === entry.id)
    );

    let updated: RecentResultEntry[];
    if (index >= 0) {
      // Merge IDs & statuses
      const prev = existing[index];
      const mergedStatuses = Array.from(new Set([...prev.statuses, ...record.statuses])) as ('Scanned' | 'Benchmarked' | 'Patched')[];
      updated = [
        {
          ...prev,
          ...record,
          analysis_id: record.analysis_id || prev.analysis_id,
          run_id: record.run_id || prev.run_id,
          optimization_id: record.optimization_id || prev.optimization_id,
          patch_id: record.patch_id || prev.patch_id,
          statuses: mergedStatuses,
        },
        ...existing.filter((_, i) => i !== index),
      ];
    } else {
      updated = [record, ...existing];
    }

    const capped = updated.slice(0, RECENT_RESULTS_CAP);
    window.localStorage.setItem(RECENT_RESULTS_STORAGE_KEY, JSON.stringify(capped));
    return record;
  } catch {
    return null;
  }
}

/**
 * Removes a single entry by id from localStorage.
 */
export function removeRecentResult(id: string): void {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return;
    const existing = getRecentResults();
    const filtered = existing.filter(e => e.id !== id);
    window.localStorage.setItem(RECENT_RESULTS_STORAGE_KEY, JSON.stringify(filtered));
  } catch {
    // Ignore
  }
}

/**
 * Clears all recent results from localStorage.
 */
export function clearRecentResults(): void {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return;
    window.localStorage.removeItem(RECENT_RESULTS_STORAGE_KEY);
  } catch {
    // Ignore
  }
}
