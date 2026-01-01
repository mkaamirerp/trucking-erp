import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Card from "@/components/Card";
import Button from "@/components/Button";
import { createPayRun, generatePayRun, getPayPeriods, PayPeriod } from "@/api";
import { hasRole, useMe } from "@/hooks/useMe";

const DOCUMENT_TYPES = [
  "PAYSTUB",
  "SETTLEMENT_STATEMENT",
  "CONTRACTOR_PAY_STATEMENT",
  "CARRIER_PAYOUT_STATEMENT",
];
const WORKER_TYPES = [
  "EMPLOYEE_DRIVER",
  "CONTRACTOR_COMPANY_DRIVER",
  "OWNER_OPERATOR_LEASED_ON",
  "THIRD_PARTY_CARRIER",
];

export default function PayRunNewPage() {
  const navigate = useNavigate();
  const [periods, setPeriods] = useState<PayPeriod[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    pay_period_id: "",
    pay_document_type: DOCUMENT_TYPES[0],
    worker_type_snapshot: WORKER_TYPES[0],
    pay_date: "",
    base_currency_snapshot: "USD",
  });
  const { me } = useMe();
  const isTenantAdmin = hasRole(me, "TENANT_ADMIN");

  useEffect(() => {
    getPayPeriods()
      .then((data) => setPeriods(data))
      .catch((err) => setError(err.message || "Failed to load pay periods"))
      .finally(() => setLoading(false));
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!isTenantAdmin) return;
    setSubmitting(true);
    try {
      const run = await createPayRun({
        pay_period_id: Number(form.pay_period_id),
        pay_document_type: form.pay_document_type,
        worker_type_snapshot: form.worker_type_snapshot,
        pay_date: form.pay_date,
        base_currency_snapshot: form.base_currency_snapshot,
      });
      await generatePayRun(run.id);
      navigate(`/payroll/pay-runs/${run.id}`);
    } catch (err: any) {
      setError(err.message || "Failed to generate pay run");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Generate Pay Run</h1>
          <p className="text-sm text-gray-600">Create a new pay run and generate line items.</p>
        </div>
      </div>

      <Card title="Details">
        {loading && <p className="text-sm text-gray-500">Loading pay periods...</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
        {!loading && (
          <form onSubmit={onSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700">Pay Period</label>
              <select
                required
                value={form.pay_period_id}
                onChange={(e) => setForm((f) => ({ ...f, pay_period_id: e.target.value }))}
                className="mt-1 w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm"
              >
                <option value="">Select period</option>
                {periods.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.start_date} → {p.end_date})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Document Type</label>
              <select
                required
                value={form.pay_document_type}
                onChange={(e) => setForm((f) => ({ ...f, pay_document_type: e.target.value }))}
                className="mt-1 w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm"
              >
                {DOCUMENT_TYPES.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Worker Type</label>
              <select
                required
                value={form.worker_type_snapshot}
                onChange={(e) => setForm((f) => ({ ...f, worker_type_snapshot: e.target.value }))}
                className="mt-1 w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm"
              >
                {WORKER_TYPES.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Pay Date</label>
              <input
                required
                type="date"
                value={form.pay_date}
                onChange={(e) => setForm((f) => ({ ...f, pay_date: e.target.value }))}
                className="mt-1 w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Currency</label>
              <input
                required
                value={form.base_currency_snapshot}
                onChange={(e) => setForm((f) => ({ ...f, base_currency_snapshot: e.target.value.toUpperCase() }))}
                className="mt-1 w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm"
              />
            </div>
            <div className="sm:col-span-2">
              <Button type="submit" disabled={submitting || !isTenantAdmin}>
                {submitting ? "Generating..." : "Generate & Review"}
              </Button>
              {!isTenantAdmin && (
                <p className="mt-2 text-xs text-gray-500">Only TenantAdmin can generate pay runs.</p>
              )}
            </div>
          </form>
        )}
      </Card>
    </div>
  );
}
