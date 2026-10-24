/** Month-first display for load workspace stop dates (e.g. 10/28/2026). */
export function formatDateMonthFirst(iso: string | null | undefined): string {
  if (!iso) return "";
  const part = iso.length >= 10 ? iso.slice(0, 10) : iso;
  const [y, m, d] = part.split("-");
  if (!y || !m || !d) return iso;
  const mi = parseInt(m, 10);
  const di = parseInt(d, 10);
  if (!Number.isFinite(mi) || !Number.isFinite(di)) return iso;
  return `${mi}/${di}/${y}`;
}

/** Parse month-first text to ISO date (YYYY-MM-DD) or null if invalid. */
export function parseDateMonthFirst(text: string): string | null {
  const t = text.trim();
  if (!t) return null;
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(t);
  if (!m) return null;
  const mm = m[1].padStart(2, "0");
  const dd = m[2].padStart(2, "0");
  const y = m[3];
  const month = parseInt(mm, 10);
  const day = parseInt(dd, 10);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return `${y}-${mm}-${dd}`;
}
