import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Card from "@/components/Card";
import Button from "@/components/Button";
import StatusBadge from "@/components/StatusBadge";
import EmptyState from "@/components/EmptyState";
import { Table } from "@/components/Table";
import {
  finalizePayRun,
  getPayRun,
  getPayRunItems,
  getPayRunPayees,
  PayRunDetail,
  PayRunItem,
  PayRunPayeeRow,
} from "@/api";
import { hasRole, useMe } from "@/hooks/useMe";

export default function PayRunDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = useState<PayRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [finalizing, setFinalizing] = useState(false);
  const [payees, setPayees] = useState<PayRunPayeeRow[]>([]);
  const [selectedPayeeId, setSelectedPayeeId] = useState<number | null>(null);
  const [items, setItems] = useState<PayRunItem[]>([]);
  const { me } = useMe();
  const isTenantAdmin = hasRole(me, "TENANT_ADMIN");

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getPayRun(Number(id))
      .then((data) => setRun(data))
      .catch((err) => setError(err.message || "Failed to load pay run"))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (!id) return;
    getPayRunPayees(Number(id))
      .then((rows) => {
        setPayees(rows);
        if (rows.length && selectedPayeeId === null) {
          setSelectedPayeeId(rows[0].payee_id);
        }
      })
      .catch(() => {});
  }, [id, selectedPayeeId]);

  useEffect(() => {
    if (!id || selectedPayeeId === null) return;
    getPayRunItems(Number(id), selectedPayeeId)
      .then((data) => setItems(data))
      .catch(() => setItems([]));
  }, [id, selectedPayeeId]);

  const selectedPayeeNet = useMemo(() => {
    if (selectedPayeeId === null) return null;
    const found = payees.find((p) => p.payee_id === selectedPayeeId);
    return found?.net_amount ?? null;
  }, [payees, selectedPayeeId]);

  const onFinalize = async () => {
    if (!run || !isTenantAdmin) return;
    if (!window.confirm("Finalize this pay run? Editing will lock.")) return;
    setFinalizing(true);
    try {
      await finalizePayRun(run.id);
      window.location.reload();
    } catch (err: any) {
      alert(err.message || "Failed to finalize pay run");
    } finally {
      setFinalizing(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <p className="text-sm text-gray-500 cursor-pointer" onClick={() => navigate("/payroll/pay-runs")}>
            ← Back to Pay Runs
          </p>
          <h1 className="text-xl font-semibold">Pay Run #{id}</h1>
          {run && (
            <div className="flex items-center space-x-2 text-sm text-gray-700">
              <StatusBadge status={run.status} />
              <StatusBadge status={run.payout_status} />
              <span>{run.pay_document_type}</span>
              <span>{run.worker_type_snapshot}</span>
              <span>Pay Date: {run.pay_date}</span>
              <span>Currency: {run.base_currency_snapshot}</span>
            </div>
          )}
        </div>
        <div className="flex items-center space-x-2">
          {isTenantAdmin && (
            <Button onClick={onFinalize} disabled={finalizing || run?.status === "FINALIZED"}>
              {finalizing ? "Finalizing..." : "Finalize"}
            </Button>
          )}
        </div>
      </div>

      <Card title="Payees">
        {loading && <p className="text-sm text-gray-500">Loading...</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
        {!loading && !run && <EmptyState title="Pay run not found" />}
        {!loading && run && payees.length === 0 && (
          <EmptyState title="No line items" description="Generate items before reviewing." />
        )}
        {!loading && run && payees.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="col-span-1 space-y-2">
              <div className="border rounded-lg divide-y">
                {payees.map((p) => (
                  <button
                    key={p.payee_id}
                    className={`w-full text-left px-4 py-3 flex items-center justify-between ${
                      selectedPayeeId === p.payee_id ? "bg-blue-50" : ""
                    }`}
                    onClick={() => setSelectedPayeeId(p.payee_id)}
                  >
                    <div>
                      <p className="text-sm font-semibold text-gray-900">{p.display_name}</p>
                      <p className="text-xs text-gray-600">Payee #{p.payee_id}</p>
                    </div>
                    <div className="text-sm font-medium text-gray-900">
                      {Number(p.net_amount).toFixed(2)} {run.base_currency_snapshot}
                    </div>
                  </button>
                ))}
              </div>
            </div>
            <div className="lg:col-span-2">
              {selectedPayeeId !== null ? (
                <Card
                  title={`Payee ${selectedPayeeId} Line Items`}
                  actions={
                    selectedPayeeNet !== null ? (
                      <div className="text-sm font-medium text-gray-900">
                        Net: {Number(selectedPayeeNet).toFixed(2)} {run.base_currency_snapshot}
                      </div>
                    ) : undefined
                  }
                >
                  <Table headers={["Source", "Description", "Qty", "Rate", "Amount", "Currency"]}>
                    {items.map((item) => (
                      <tr key={item.id}>
                        <td className="px-4 py-2 text-sm text-gray-700">{item.source_type}</td>
                        <td className="px-4 py-2 text-sm text-gray-700">{item.description}</td>
                        <td className="px-4 py-2 text-sm text-gray-700">
                          {item.quantity ?? <span className="text-gray-400">—</span>}
                        </td>
                        <td className="px-4 py-2 text-sm text-gray-700">
                          {item.unit_rate ?? <span className="text-gray-400">—</span>}
                        </td>
                        <td className="px-4 py-2 text-sm text-gray-900 font-medium">{item.amount_signed}</td>
                        <td className="px-4 py-2 text-sm text-gray-700">{item.currency}</td>
                      </tr>
                    ))}
                  </Table>
                </Card>
              ) : (
                <EmptyState title="Select a payee" />
              )}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
