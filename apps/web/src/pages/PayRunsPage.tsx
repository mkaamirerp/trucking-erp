import { useNavigate } from "react-router-dom";
import Card from "@/components/Card";
import Button from "@/components/Button";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { Table } from "@/components/Table";
import { listPayRuns, PayRunSummary } from "@/api";
import { useFetch } from "@/hooks/useFetch";
import { hasRole, useMe } from "@/hooks/useMe";

export default function PayRunsPage() {
  const navigate = useNavigate();
  const { me } = useMe();
  const { data, loading, error } = useFetch<PayRunSummary[]>(`/api/v1/payroll/pay-runs`, []);
  const runs = data || [];
  const isTenantAdmin = hasRole(me, "TENANT_ADMIN");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Pay Runs</h1>
          <p className="text-sm text-gray-600">Generate and review payroll/settlement runs.</p>
        </div>
        {isTenantAdmin && <Button onClick={() => navigate("/payroll/pay-runs/new")}>Generate Pay Run</Button>}
      </div>

      <Card title="Pay Runs">
        {loading && <p className="text-sm text-gray-500">Loading...</p>}
        {error && (
          <p className="text-sm text-red-600">
            {error} (Backend list endpoint may be missing. Expected GET /api/v1/payroll/pay-runs)
          </p>
        )}
        {!loading && runs.length === 0 && (
          <EmptyState
            title="No pay runs yet"
            description="Generate a pay run to see it here."
            action={
              isTenantAdmin ? (
                <Button onClick={() => navigate("/payroll/pay-runs/new")}>Generate Pay Run</Button>
              ) : undefined
            }
          />
        )}
        {!loading && runs.length > 0 && (
          <Table headers={["ID", "Period", "Doc Type", "Worker Type", "Pay Date", "Status", "Payout", "Actions"]}>
            {runs.map((run) => (
              <tr key={run.id}>
                <td className="px-4 py-2 text-sm font-medium text-gray-900">#{run.id}</td>
                <td className="px-4 py-2 text-sm text-gray-700">{run.pay_period_id}</td>
                <td className="px-4 py-2 text-sm text-gray-700">{run.pay_document_type}</td>
                <td className="px-4 py-2 text-sm text-gray-700">{run.worker_type_snapshot}</td>
                <td className="px-4 py-2 text-sm text-gray-700">{run.pay_date}</td>
                <td className="px-4 py-2 text-sm">
                  <StatusBadge status={run.status} />
                </td>
                <td className="px-4 py-2 text-sm">
                  <StatusBadge status={run.payout_status} />
                </td>
                <td className="px-4 py-2 text-sm">
                  <Button variant="secondary" onClick={() => navigate(`/payroll/pay-runs/${run.id}`)}>
                    View
                  </Button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
