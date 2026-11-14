export interface AppSettings {
  // Recommendation rules
  strictAllChecks: boolean;
  passRateRequired: number; // 50 to 100

  // Benchmark defaults
  baselineModelId: string;
  candidateModelIds: string; // comma-separated, max 8
  caseSetId: string;
  evaluationProfileId: string;

  // Data source
  dataSource: 'live' | 'recorded' | 'sample';

  // Appearance
  appearance: 'light' | 'dark' | 'system';
}

export const SETTINGS_STORAGE_KEY = 'cascaderouter.settings.v1';

export const DEFAULT_SETTINGS: AppSettings = {
  strictAllChecks: true,
  passRateRequired: 100,
  baselineModelId: 'meta-llama/Meta-Llama-3.1-70B-Instruct',
  candidateModelIds: 'nvidia/Llama-3.1-Nemotron-70B-Instruct, meta-llama/Meta-Llama-3.1-8B-Instruct',
  caseSetId: 'nebius_standard_cases',
  evaluationProfileId: 'json_eval_profile',
  dataSource: 'live',
  appearance: 'light',
};

/**
 * Validates model, case set and profile identifiers according to backend contract rules:
 * Non-empty string matching /^[A-Za-z0-9_./-]+$/
 */
export function isValidIdentifier(id: string): boolean {
  if (!id || typeof id !== 'string') return false;
  const trimmed = id.trim();
  return trimmed.length > 0 && /^[A-Za-z0-9_./-]+$/.test(trimmed);
}

/**
 * Parses and validates comma-separated candidate model IDs.
 * Enforces cap of 8 candidate models and valid identifier syntax.
 */
export function parseCandidateModelIds(raw: string): { valid: string[]; error?: string } {
  const parts = raw.split(',').map(s => s.trim()).filter(Boolean);
  if (parts.length === 0) {
    return { valid: [], error: 'At least one candidate model is required.' };
  }
  if (parts.length > 8) {
    return { valid: parts.slice(0, 8), error: 'Candidate models are limited to at most 8.' };
  }
  for (const p of parts) {
    if (!isValidIdentifier(p)) {
      return { valid: [], error: `Invalid model identifier: "${p}". Only letters, numbers, _, ., /, - allowed.` };
    }
  }
  return { valid: parts };
}

/**
 * Maps the recommendation settings into the contract's quality threshold string:
 * e.g. "1.000000" if strict, or "0.800000" if 80%.
 */
export function deriveQualityThreshold(strictAllChecks: boolean, passRateRequired: number): string {
  if (strictAllChecks) {
    return '1.000000';
  }
  const rate = Math.max(50, Math.min(100, isFinite(passRateRequired) ? passRateRequired : 100));
  return (rate / 100).toFixed(6);
}

/**
 * Safely loads settings from localStorage. Falls back to defaults.
 */
export function loadSettings(): AppSettings {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return { ...DEFAULT_SETTINGS };
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    const parsed = JSON.parse(raw);
    return {
      strictAllChecks: typeof parsed.strictAllChecks === 'boolean' ? parsed.strictAllChecks : DEFAULT_SETTINGS.strictAllChecks,
      passRateRequired: typeof parsed.passRateRequired === 'number' && parsed.passRateRequired >= 50 && parsed.passRateRequired <= 100
        ? parsed.passRateRequired
        : DEFAULT_SETTINGS.passRateRequired,
      baselineModelId: typeof parsed.baselineModelId === 'string' && isValidIdentifier(parsed.baselineModelId)
        ? parsed.baselineModelId
        : DEFAULT_SETTINGS.baselineModelId,
      candidateModelIds: typeof parsed.candidateModelIds === 'string'
        ? parsed.candidateModelIds
        : DEFAULT_SETTINGS.candidateModelIds,
      caseSetId: typeof parsed.caseSetId === 'string' && isValidIdentifier(parsed.caseSetId)
        ? parsed.caseSetId
        : DEFAULT_SETTINGS.caseSetId,
      evaluationProfileId: typeof parsed.evaluationProfileId === 'string' && isValidIdentifier(parsed.evaluationProfileId)
        ? parsed.evaluationProfileId
        : DEFAULT_SETTINGS.evaluationProfileId,
      dataSource: ['live', 'recorded', 'sample'].includes(parsed.dataSource)
        ? parsed.dataSource
        : DEFAULT_SETTINGS.dataSource,
      appearance: ['light', 'dark', 'system'].includes(parsed.appearance)
        ? parsed.appearance
        : DEFAULT_SETTINGS.appearance,
    };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

/**
 * Saves settings to localStorage under cascaderouter.settings.v1.
 * Ignores failures if storage is unavailable.
 */
export function saveSettings(settings: AppSettings): boolean {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return false;
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
    return true;
  } catch {
    return false;
  }
}
