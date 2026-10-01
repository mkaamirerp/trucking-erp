import type { FuelBvdRow, FuelCanonicalTransaction } from "../../api";
import { operationalCell } from "./bvdParsedDisplay";
import { formatBvdTxnCompactMoney } from "./fuelBvdTxnMoneyColumns";
import { formatBvdTransactionDateTime } from "./bvdTransactionRowPresentation";

type Props = {
  rows: FuelBvdRow[];
  canonicalByRowId?: Map<number, FuelCanonicalTransaction>;
};

function categoryLabel(row: FuelBvdRow, canonicalByRowId?: Map<number, FuelCanonicalTransaction>): string {
  const canon = canonicalByRowId?.get(row.id);
  if (canon?.classification?.trim()) return canon.classification.trim();
  return "—";
}

export default function BvdExpressRowsTable({ rows, canonicalByRowId }: Props) {
  return (
    <div
      className="bvd-statement__table-wrap bvd-express-rows"
      data-testid="bvd-express-rows-table"
    >
      <table className="bvd-statement__table bvd-statement__table--txn bvd-txn-rows__table bvd-express-rows__table">
        <thead className="bvd-express-rows__thead">
          <tr className="bvd-express-rows__header-row">
            <th className="bvd-express-rows__col-compact bvd-express-rows__header-cell" scope="col">
              Date / Time
            </th>
            <th className="bvd-express-rows__col-compact bvd-express-rows__header-cell" scope="col">Unit</th>
            <th
              className="bvd-express-rows__col-flex bvd-express-rows__col-driver bvd-express-rows__header-cell"
              scope="col"
            >
              Source driver
            </th>
            <th className="bvd-express-rows__col-compact bvd-express-rows__header-cell" scope="col">
              Provider ref
            </th>
            <th className="bvd-express-rows__col-compact bvd-express-rows__header-cell" scope="col">Auth</th>
            <th className="bvd-express-rows__col-flex bvd-express-rows__header-cell" scope="col">
              Provider reason
            </th>
            <th
              className="bvd-express-rows__col-compact bvd-express-rows__col-numeric bvd-express-rows__header-cell"
              scope="col"
            >
              Principal
            </th>
            <th
              className="bvd-express-rows__col-compact bvd-express-rows__col-numeric bvd-express-rows__header-cell"
              scope="col"
            >
              Fee
            </th>
            <th
              className="bvd-express-rows__col-compact bvd-express-rows__col-amount bvd-express-rows__header-cell"
              scope="col"
            >
              Total
            </th>
            <th className="bvd-express-rows__col-compact bvd-express-rows__header-cell" scope="col">Currency</th>
            <th className="bvd-express-rows__col-compact bvd-express-rows__header-cell" scope="col">Category</th>
          </tr>
        </thead>
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
