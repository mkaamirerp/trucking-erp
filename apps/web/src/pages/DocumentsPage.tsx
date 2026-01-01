import { useState } from "react";
import Card from "@/components/Card";
import EmptyState from "@/components/EmptyState";
import { Table } from "@/components/Table";
import StatusBadge from "@/components/StatusBadge";
import Button from "@/components/Button";
import { useFetch } from "@/hooks/useFetch";
import { PayDocument } from "@/api";

const filters = [
  { id: "period", label: "Pay Period ID" },
  { id: "payee", label: "Payee ID" },
  { id: "type", label: "Document Type" },
];

export default function DocumentsPage() {
  const { data, loading, error } = useFetch<PayDocument[]>(`/api/v1/payroll/documents`, []);
  const [filter, setFilter] = useState({ period: "", payee: "", type: "" });
  const docs = data || [];

  const filtered = docs.filter((d) => {
    if (filter.period && String(d.pay_run_id) !== filter.period) return false;
    if (filter.payee && String(d.payee_id) !== filter.payee) return false;
    if (filter.type && d.document_type !== filter.type) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Pay Documents</h1>
          <p className="text-sm text-gray-600">Download generated pay documents (PDFs).</p>
        </div>
      </div>

      <Card title="Filters">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {filters.map((f) => (
            <div key={f.id}>
              <label className="block text-sm font-medium text-gray-700">{f.label}</label>
              <input
                value={(filter as any)[f.id]}
                onChange={(e) => setFilter((prev) => ({ ...prev, [f.id]: e.target.value }))}
                className="mt-1 w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm"
                placeholder="Any"
              />
            </div>
          ))}
        </div>
      </Card>

      <Card title="Documents">
        {loading && <p className="text-sm text-gray-500">Loading...</p>}
        {error && (
          <p className="text-sm text-red-600">
            {error} (Backend endpoint may be missing. Expected GET /api/v1/payroll/documents)
          </p>
        )}
        {!loading && filtered.length === 0 && (
          <EmptyState
            title="No documents"
            description="Generate pay runs and PDFs to see documents here."
          />
        )}
        {!loading && filtered.length > 0 && (
          <Table headers={["Pay Run", "Payee", "Type", "Generated At", "Version", "Actions"]}>
            {filtered.map((doc) => (
              <tr key={doc.id}>
                <td className="px-4 py-2 text-sm font-medium text-gray-900">#{doc.pay_run_id}</td>
                <td className="px-4 py-2 text-sm text-gray-700">{doc.payee_id}</td>
                <td className="px-4 py-2 text-sm text-gray-700">
                  <StatusBadge status={doc.document_type} />
                </td>
                <td className="px-4 py-2 text-sm text-gray-700">{doc.generated_at}</td>
                <td className="px-4 py-2 text-sm text-gray-700">{doc.version}</td>
                <td className="px-4 py-2 text-sm text-gray-700">
                  <Button variant="secondary" onClick={() => (window.location.href = `/api/v1/payroll/documents/${doc.id}/download`)}>
                    Download
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
