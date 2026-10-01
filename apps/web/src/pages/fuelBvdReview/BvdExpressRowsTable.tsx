import type { ReactNode } from "react";
import type { FuelBvdRow, FuelCanonicalTransaction } from "../../api";
import { operationalCell } from "./bvdParsedDisplay";
import { formatBvdTxnCompactMoney } from "./fuelBvdTxnMoneyColumns";
import { formatBvdTransactionDateTime } from "./bvdTransactionRowPresentation";

type Props = {
  rows: FuelBvdRow[];
  canonicalByRowId?: Map<number, FuelCanonicalTransaction>;
  processedStickyHeader?: boolean;
};

const EXPRESS_TWO_LINE: Record<string, [string, string]> = {
  "Date / Time": ["Date /", "Time"],
  "Source driver": ["Source", "driver"],
  "Provider ref": ["Provider", "ref"],
  "Provider reason": ["Provider", "reason"],
};

function expressHeaderText(label: string, processed: boolean): ReactNode {
  if (!processed) return label;
  const lines = EXPRESS_TWO_LINE[label];
  if (!lines) return label;
  return (
    <>
      {lines[0]}
      <br />
      {lines[1]}
    </>
  );
}

function categoryLabel(row: FuelBvdRow, canonicalByRowId?: Map<number, FuelCanonicalTransaction>): string {
  const canon = canonicalByRowId?.get(row.id);
  if (canon?.classification?.trim()) return canon.classification.trim();
  return "—";
}

function expressThClass(label: string, base: string, processed: boolean): string {
  if (!processed) return `${base} bvd-express-rows__header-cell`;
  const two = EXPRESS_TWO_LINE[label];
  return [
    base,
    "bvd-express-rows__header-cell",
    "bvd-express-rows__header-sticky",
    two ? "bvd-express-rows__header-twoline" : "bvd-express-rows__header-oneline",
  ].join(" ");
}

function ExpressHeaderRow({ processedStickyHeader = false }: { processedStickyHeader?: boolean }) {
  const cell = (label: string, className: string) => (
    <th className={expressThClass(label, className, processedStickyHeader)} scope="col">
      {expressHeaderText(label, processedStickyHeader)}
    </th>
  );

  return (
    <thead className="bvd-express-rows__thead">
      <tr className="bvd-express-rows__header-row">
        {cell("Date / Time", "bvd-express-rows__col-compact")}
        {cell("Unit", "bvd-express-rows__col-compact")}
        {cell("Source driver", "bvd-express-rows__col-flex bvd-express-rows__col-driver")}
        {cell("Provider ref", "bvd-express-rows__col-compact")}
        {cell("Auth", "bvd-express-rows__col-compact")}
        {cell("Provider reason", "bvd-express-rows__col-flex")}
        {cell("Principal", "bvd-express-rows__col-compact bvd-express-rows__col-numeric")}
        {cell("Fee", "bvd-express-rows__col-compact bvd-express-rows__col-numeric")}
        {cell("Total", "bvd-express-rows__col-compact bvd-express-rows__col-amount")}
        {cell("Currency", "bvd-express-rows__col-compact")}
        {cell("Category", "bvd-express-rows__col-compact")}
      </tr>
    </thead>
  );
}

export default function BvdExpressRowsTable({
  rows,
  canonicalByRowId,
  processedStickyHeader = false,
}: Props) {
  const tableClass =
    "bvd-statement__table bvd-statement__table--txn bvd-txn-rows__table bvd-express-rows__table";

  const wrapClass = processedStickyHeader
    ? "bvd-statement__table-wrap bvd-express-rows bvd-express-rows--processed-native-sticky"
    : "bvd-statement__table-wrap bvd-express-rows";

  return (
    <div
      className={wrapClass}
      data-testid="bvd-express-rows-table"
      data-processed-native-sticky={processedStickyHeader ? "true" : undefined}
    >
      <table className={tableClass}>
        <ExpressHeaderRow processedStickyHeader={processedStickyHeader} />
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className="bvd-purchase-row bvd-express-rows__main"
              data-testid={`bvd-express-row-${row.id}`}
            >
              <td className="bvd-express-rows__col-compact" data-testid="bvd-express-col-date">
                {formatBvdTransactionDateTime(operationalCell(row, "transaction_date"))}
              </td>
              <td className="bvd-express-rows__col-compact" data-testid="bvd-express-col-unit">
                {operationalCell(row, "express_tractor") || operationalCell(row, "unit_number") || "—"}
              </td>
              <td
                className="bvd-express-rows__col-flex bvd-express-rows__col-driver"
                data-testid="bvd-express-col-driver"
              >
                {operationalCell(row, "driver_name") || "—"}
              </td>
              <td className="bvd-express-rows__col-compact" data-testid="bvd-express-col-provider-ref">
                {operationalCell(row, "express_code") || "—"}
              </td>
              <td className="bvd-express-rows__col-compact" data-testid="bvd-express-col-auth">
                {operationalCell(row, "auth_code") || "—"}
              </td>
              <td className="bvd-express-rows__col-flex" data-testid="bvd-express-col-reason">
                {operationalCell(row, "payee_raw") || "—"}
              </td>
              <td
                className="bvd-express-rows__col-compact bvd-express-rows__col-numeric"
                data-testid="bvd-express-col-principal"
              >
                {formatBvdTxnCompactMoney(operationalCell(row, "amount_cashed"))}
              </td>
              <td
                className="bvd-express-rows__col-compact bvd-express-rows__col-numeric"
                data-testid="bvd-express-col-fee"
              >
                {formatBvdTxnCompactMoney(operationalCell(row, "express_fee"))}
              </td>
              <td
                className="bvd-express-rows__col-compact bvd-express-rows__col-amount"
                data-testid="bvd-express-col-final"
              >
                {formatBvdTxnCompactMoney(operationalCell(row, "final_amt"))}
              </td>
              <td className="bvd-express-rows__col-compact" data-testid="bvd-express-col-cur">
                {operationalCell(row, "cur") || "—"}
              </td>
              <td className="bvd-express-rows__col-compact" data-testid="bvd-express-col-category">
                {categoryLabel(row, canonicalByRowId)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
