import type { TollPdfReviewRow } from "../../api";

export type TollReviewSortColumn =
  | "order"
  | "page"
  | "agency"
  | "post_date"
  | "entry"
  | "exit"
  | "entry_loc"
  | "exit_loc"
  | "transponder"
  | "plate"
  | "charge";

export type TollReviewSortDirection = "asc" | "desc";

export type TollReviewSortState = {
  column: TollReviewSortColumn;
  direction: TollReviewSortDirection;
};

function effectiveText(row: TollPdfReviewRow, key: keyof TollPdfReviewRow): string {
  const overlay = row.effective?.[key as string];
  if (typeof overlay === "string" && overlay.trim()) return overlay.trim();
  const raw = row[key];
  if (raw == null) return "";
  return String(raw).trim();
}

function compareText(a: string, b: string): number {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  return a.localeCompare(b, "en", { sensitivity: "base" });
}

function compareIdentifier(a: string, b: string): number {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  return a.localeCompare(b, "en", { sensitivity: "base", numeric: false });
}

function compareNumber(a: number, b: number): number {
  if (Number.isNaN(a) && Number.isNaN(b)) return 0;
  if (Number.isNaN(a)) return 1;
  if (Number.isNaN(b)) return -1;
  if (a === b) return 0;
  return a < b ? -1 : 1;
}

function dateKey(date: string, time: string): number {
  const text = `${date} ${time}`.trim();
  if (!text) return Number.NEGATIVE_INFINITY;
  const isoLike = text.includes("T") ? text : text.replace(" ", "T");
  const parsed = Date.parse(isoLike);
  if (!Number.isNaN(parsed)) return parsed;
  return Number.NEGATIVE_INFINITY;
}

function moneyKey(value: string): number {
  const cleaned = value.replace(/[$,()]/g, "").trim();
  if (!cleaned) return Number.NaN;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : Number.NaN;
}

export function compareTollReviewRows(
  a: TollPdfReviewRow,
  b: TollPdfReviewRow,
  column: TollReviewSortColumn,
): number {
  switch (column) {
    case "order":
      return compareNumber(a.source_row_order, b.source_row_order);
    case "page":
      return compareNumber(a.source_page_number ?? Number.NaN, b.source_page_number ?? Number.NaN);
    case "agency":
      return compareText(effectiveText(a, "agency_raw"), effectiveText(b, "agency_raw"));
    case "post_date":
      return compareNumber(dateKey(effectiveText(a, "post_date"), ""), dateKey(effectiveText(b, "post_date"), ""));
    case "entry":
      return compareNumber(
        dateKey(effectiveText(a, "entry_date"), effectiveText(a, "entry_time")),
        dateKey(effectiveText(b, "entry_date"), effectiveText(b, "entry_time")),
      );
    case "exit":
      return compareNumber(
        dateKey(effectiveText(a, "exit_date"), effectiveText(a, "exit_time")),
        dateKey(effectiveText(b, "exit_date"), effectiveText(b, "exit_time")),
      );
    case "entry_loc":
      return compareText(
        `${effectiveText(a, "entry_location")} ${effectiveText(a, "entry_lane")}`,
        `${effectiveText(b, "entry_location")} ${effectiveText(b, "entry_lane")}`,
      );
    case "exit_loc":
      return compareText(
        `${effectiveText(a, "exit_location")} ${effectiveText(a, "exit_lane")}`,
        `${effectiveText(b, "exit_location")} ${effectiveText(b, "exit_lane")}`,
      );
    case "transponder":
      return compareIdentifier(effectiveText(a, "transponder_number"), effectiveText(b, "transponder_number"));
    case "plate":
      return compareIdentifier(effectiveText(a, "plate_number"), effectiveText(b, "plate_number"));
    case "charge":
      return compareNumber(moneyKey(effectiveText(a, "trip_charge")), moneyKey(effectiveText(b, "trip_charge")));
    default:
      return 0;
  }
}

export function sortTollReviewRows(
  rows: TollPdfReviewRow[],
  sort: TollReviewSortState | null,
): TollPdfReviewRow[] {
  if (!sort) return rows;
  const indexed = rows.map((row, sourceIndex) => ({ row, sourceIndex }));
  indexed.sort((left, right) => {
    const cmp = compareTollReviewRows(left.row, right.row, sort.column);
    if (cmp !== 0) return sort.direction === "asc" ? cmp : -cmp;
    return left.sourceIndex - right.sourceIndex;
  });
  return indexed.map((entry) => entry.row);
}

export function nextTollReviewSort(
  prev: TollReviewSortState | null,
  column: TollReviewSortColumn,
): TollReviewSortState {
  if (prev?.column === column) {
    return { column, direction: prev.direction === "asc" ? "desc" : "asc" };
  }
  return { column, direction: "asc" };
}
