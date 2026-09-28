const STORAGE_KEY = "truckerp.fuel.lastProviderCode";

export function readLastFuelProviderCode(): string | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v && v.trim() ? v.trim() : null;
  } catch {
    return null;
  }
}

export function writeLastFuelProviderCode(code: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, code.trim());
  } catch {
    /* ignore */
  }
}
