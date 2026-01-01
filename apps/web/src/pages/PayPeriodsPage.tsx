import { FormEvent, useMemo, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { Table } from "@/components/Table";
import { createPayPeriod, closePayPeriod, getPayPeriods, PayPeriod } from "@/api";
import { useFetch } from "@/hooks/useFetch";
import { hasRole, useMe } from "@/hooks/useMe";

export default function PayPeriodsPage() {
  const { data, loading, error } = useFetch<PayPeriod[]>(`/api/v1/payroll/pay-periods`, []);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", start_date: "", end_date: "" });
  const periods = useMemo(() => data || [], [data]);
  const { me } = useMe();
  const isTenantAdmin = hasRole(me, "TENANT_ADMIN");

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!isTenantAdmin) return;
    setCreating(true);
    try {
      await createPayPeriod(form);
      window.location.reload();
    } catch (err: any) {
      alert(err.message || "Failed to create pay period");
    } finally {
      setCreating(false);
    }
  };

  const onClose = async (id: number) => {
    if (!window.confirm("Close this pay period? This locks edits.")) return;
    try {
      await closePayPeriod(id);
      window.location.reload();
    } catch (err: any) {
      alert(err.message || "Failed to close pay period");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Pay Periods</h1>
          <p className="text-sm text-gray-600">Create, view, and close pay periods.</p>
        </div>
      </div>

      {isTenantAdmin && (
        <Card title="Create Pay Period">
          <form onSubmit={onCreate} className="grid grid-cols-1 gap-4 sm:grid-cols-4 items-end">
            <div className="sm:col-span-1">
              <label className="block text-sm font-medium text-gray-700">Name</label>
              <input
                required
                className="mt-1 w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div className="sm:col-span-1">
              <label className="block text-sm font-medium text-gray-700">Start Date</label>
              <input
                required
                type="date"
                className="mt-1 w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm"
                value={form.start_date}
                onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))}
              />
            </div>
            <div className="sm:col-span-1">
              <label className="block text-sm font-medium text-gray-700">End Date</label>
              <input
                required
                type="date"
                className="mt-1 w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm"
                value={form.end_date}
                onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))}
              />
            </div>
            <div>
              <Button type="submit" disabled={creating || !isTenantAdmin}>
                {creating ? "Creating..." : "Create"}
              </Button>
              {!isTenantAdmin && (
                <p className="mt-1 text-xs text-gray-500">Only TenantAdmin can create periods.</p>
              )}
            </div>
          </form>
        </Card>
      )}

      <Card title="Pay Periods">
        {loading && <p className="text-sm text-gray-500">Loading...</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
        {!loading && periods.length === 0 && (
          <EmptyState title="No pay periods" description="Create your first pay period to begin." />
        )}
        {!loading && periods.length > 0 && (
          <Table headers={["Name", "Start", "End", "Status", "Updated", "Actions"]}>
            {periods.map((p) => (
              <tr key={p.id}>
                <td className="px-4 py-2 text-sm font-medium text-gray-900">{p.name}</td>
                <td className="px-4 py-2 text-sm text-gray-700">{p.start_date}</td>
                <td className="px-4 py-2 text-sm text-gray-700">{p.end_date}</td>
                <td className="px-4 py-2 text-sm">
                  <StatusBadge status={p.status} />
                </td>
                <td className="px-4 py-2 text-sm text-gray-700">{p.updated_at?.slice(0, 10)}</td>
                <td className="px-4 py-2 text-sm text-gray-700">
                  {isTenantAdmin && p.status === "OPEN" ? (
                    <Button variant="secondary" onClick={() => onClose(p.id)}>
                      Close
                    </Button>
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
