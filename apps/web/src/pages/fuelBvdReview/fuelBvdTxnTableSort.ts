import type { FuelBvdRow } from "../../api";
import { operationalCell } from "./bvdParsedDisplay";
import { parseBvdMoneyString } from "./bvdParsedValidation";
import { bvdProductDisplayLabel } from "./bvdProductDisplay";
import { formatBvdTxnLocationShort } from "./bvdTransactionRowPresentation";

export type FuelBvdTxnSortColumn =
  | "date"
  | "unit"
  | "driver"
  | "location"
  | "product"
  | "qty"
  | "discount"
  | "hst"
  | "gst"
  | "pst"
  | "qst"
  | "final"
  | "currency";

export type FuelBvdTxnSortDirection = "asc" | "desc";

export type FuelBvdTxnSortState = {
  column: FuelBvdTxnSortColumn;
  direction: FuelBvdTxnSortDirection;
};

/** Parse BVD transaction datetime for chronological sort (not display text). */
export function parseFuelBvdTxnDateSortKey(raw: string): number {
  const t = raw.trim();
  if (!t) return Number.NEGATIVE_INFINITY;
  const isoLike = t.includes("T") ? t : t.replace(" ", "T");
  const d = new Date(isoLike);
  if (!Number.isNaN(d.getTime())) return d.getTime();
  const m = t.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
  if (m) {
    const parsed = Date.parse(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:00`);
    if (!Number.isNaN(parsed)) return parsed;
  }
  return Number.NEGATIVE_INFINITY;
}

/** Identifier/text sort — preserves leading zeros (no numeric coercion). */
export function compareFuelBvdIdentifier(a: string, b: string): number {
  const ta = a.trim();
  const tb = b.trim();
  if (!ta && !tb) return 0;
  if (!ta) return 1;
  if (!tb) return -1;
  return ta.localeCompare(tb, "en", { sensitivity: "base", numeric: false });
}

function compareFuelBvdMoneyField(a: string, b: string): number {
  const na = parseBvdMoneyString(a);
  const nb = parseBvdMoneyString(b);
  if (na === null && nb === null) return 0;
  if (na === null) return 1;
  if (nb === null) return -1;
  if (na === nb) return 0;
  return na < nb ? -1 : 1;
}

function compareFuelBvdText(a: string, b: string): number {
  const ta = a.trim();
  const tb = b.trim();
  if (!ta && !tb) return 0;
  if (!ta) return 1;
  if (!tb) return -1;
  return ta.localeCompare(tb, "en", { sensitivity: "base" });
}

export function compareFuelBvdTxnRows(
  a: FuelBvdRow,
  b: FuelBvdRow,
  column: FuelBvdTxnSortColumn,
): number {
  switch (column) {
    case "date": {
      const ka = parseFuelBvdTxnDateSortKey(operationalCell(a, "transaction_date"));
      const kb = parseFuelBvdTxnDateSortKey(operationalCell(b, "transaction_date"));
      if (ka === kb) return 0;
      return ka < kb ? -1 : 1;
    }
    case "unit":
      return compareFuelBvdIdentifier(
        operationalCell(a, "unit_number"),
        operationalCell(b, "unit_number"),
      );
    case "driver":
      return compareFuelBvdText(
        operationalCell(a, "driver_name"),
        operationalCell(b, "driver_name"),
      );
    case "location":
      return compareFuelBvdText(formatBvdTxnLocationShort(a), formatBvdTxnLocationShort(b));
    case "product":
      return compareFuelBvdText(
        bvdProductDisplayLabel(operationalCell(a, "prod")),
        bvdProductDisplayLabel(operationalCell(b, "prod")),
      );
    case "qty":
      return compareFuelBvdMoneyField(operationalCell(a, "qty"), operationalCell(b, "qty"));
    case "discount":
      return compareFuelBvdMoneyField(operationalCell(a, "disc_amt"), operationalCell(b, "disc_amt"));
    case "hst":
      return compareFuelBvdMoneyField(operationalCell(a, "hst"), operationalCell(b, "hst"));
    case "gst":
      return compareFuelBvdMoneyField(operationalCell(a, "gst"), operationalCell(b, "gst"));
    case "pst":
      return compareFuelBvdMoneyField(operationalCell(a, "pst"), operationalCell(b, "pst"));
    case "qst":
      return compareFuelBvdMoneyField(operationalCell(a, "qst"), operationalCell(b, "qst"));
    case "final":
      return compareFuelBvdMoneyField(
        operationalCell(a, "final_amt"),
        operationalCell(b, "final_amt"),
      );
    case "currency":
      return compareFuelBvdText(operationalCell(a, "cur"), operationalCell(b, "cur"));
    default:
      return 0;
  }
}

/** UI-only view sort; stable tie-break preserves source order within equal keys. */
export function sortFuelBvdTransactions(
  transactions: FuelBvdRow[],
  sort: FuelBvdTxnSortState,
): FuelBvdRow[] {
  const indexed = transactions.map((row, sourceIndex) => ({ row, sourceIndex }));
  indexed.sort((left, right) => {
    const cmp = compareFuelBvdTxnRows(left.row, right.row, sort.column);
    if (cmp !== 0) {
      return sort.direction === "asc" ? cmp : -cmp;
    }
    return left.sourceIndex - right.sourceIndex;
  });
  return indexed.map((entry) => entry.row);
}
