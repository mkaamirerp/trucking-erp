/** Calendar month length (month 1–12). Uses real Date math (leap years). */
export function daysInCalendarMonth(year: number, month1to12: number): number {
  return new Date(year, month1to12, 0).getDate();
}

export type MonthRelativeWeek = {
  week: 1 | 2 | 3 | 4 | 5;
  year: number;
  month: number;
  fromDay: number;
  toDay: number;
  label: string;
};

export function monthRelativeWeekBounds(
  year: number,
  month1to12: number,
  week: 1 | 2 | 3 | 4 | 5,
): { fromDay: number; toDay: number } {
  const dim = daysInCalendarMonth(year, month1to12);
  const fromDay = (week - 1) * 7 + 1;
  const toDay = week === 5 ? dim : Math.min(week * 7, dim);
  return { fromDay, toDay };
}

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function formatMonthDay(year: number, month: number, day: number): string {
  const short = MONTH_NAMES[month - 1]?.slice(0, 3) ?? "???";
  return `${short} ${day}`;
}

export function buildMonthRelativeWeeks(year: number, month1to12: number): MonthRelativeWeek[] {
  const dim = daysInCalendarMonth(year, month1to12);
  const weeks: MonthRelativeWeek[] = [];
  for (let w = 1; w <= 5; w++) {
    const week = w as 1 | 2 | 3 | 4 | 5;
    const { fromDay, toDay } = monthRelativeWeekBounds(year, month1to12, week);
    if (fromDay > dim) break;
    weeks.push({
      week,
      year,
      month: month1to12,
      fromDay,
      toDay,
      label: `Week ${week} — ${formatMonthDay(year, month1to12, fromDay)}–${formatMonthDay(year, month1to12, toDay)}`,
    });
    if (toDay >= dim) break;
  }
  return weeks;
}

export type StatementMonthGroup = {
  year: number;
  month: number;
  label: string;
  weeks: MonthRelativeWeek[];
};

export function buildStatementMonthGroups(dates: Date[]): StatementMonthGroup[] {
  const keys = new Map<string, { year: number; month: number }>();
  for (const d of dates) {
    if (Number.isNaN(d.getTime())) continue;
    const year = d.getFullYear();
    const month = d.getMonth() + 1;
    keys.set(`${year}-${month}`, { year, month });
  }
  const sorted = [...keys.values()].sort((a, b) => a.year - b.year || a.month - b.month);
  return sorted.map(({ year, month }) => ({
    year,
    month,
    label: `${MONTH_NAMES[month - 1] ?? "Month"} ${year}`,
    weeks: buildMonthRelativeWeeks(year, month),
  }));
}

export type DatePeriodSelection =
  | { kind: "all" }
  | { kind: "week"; year: number; month: number; week: 1 | 2 | 3 | 4 | 5 }
  | { kind: "custom"; from: string; to: string };

export function parseStatementLocalDate(isoDate: string): Date | null {
  const t = isoDate.trim();
  if (!t) return null;
  const m = t.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const dt = new Date(y, mo - 1, d);
  if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
  return dt;
}

/** Accepted BVD transaction_date → local calendar date (date portion only). */
export function parseBvdStatementTransactionDate(raw: string): Date | null {
  const t = raw.trim();
  if (!t) return null;
  const head = t.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (head) return parseStatementLocalDate(head[0]);
  const iso = t.includes("T") ? t : t.replace(" ", "T");
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function toIsoDateString(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function transactionDateInPeriod(txnDate: Date | null, period: DatePeriodSelection): boolean {
  if (!txnDate || Number.isNaN(txnDate.getTime())) return period.kind === "all";
  if (period.kind === "all") return true;
  if (period.kind === "custom") {
    const from = parseStatementLocalDate(period.from);
    const to = parseStatementLocalDate(period.to);
    if (!from || !to) return true;
    const t = txnDate.getTime();
    return t >= from.getTime() && t <= to.getTime();
  }
  const y = txnDate.getFullYear();
  const m = txnDate.getMonth() + 1;
  const day = txnDate.getDate();
  if (y !== period.year || m !== period.month) return false;
  const { fromDay, toDay } = monthRelativeWeekBounds(period.year, period.month, period.week);
  return day >= fromDay && day <= toDay;
}
