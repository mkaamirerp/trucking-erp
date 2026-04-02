import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Card from "@/components/Card";
import Button from "@/components/Button";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { Table } from "@/components/Table";
import { listLoads, Load } from "@/api";

export default function LoadsListPage() {
  const navigate = useNavigate();
  const [loads, setLoads] = useState<Load[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listLoads({ page: 1, size: 50 })
      .then((res) => setLoads(res.items || []))
      .catch((e) => setError(e?.message || "Failed to load loads"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Loads</h1>
          <p className="text-sm text-gray-600">Manage loads and dispatch.</p>
        </div>
      </div>

      <Card title="Loads">
        {loading && <p className="text-sm text-gray-500">Loading...</p>}
        {error && (
          <p className="text-sm text-red-600">
            {error} (Backend list endpoint may be missing. Expected GET /api/v1/loads)
          </p>
        )}
        {!loading && loads.length === 0 && (
          <EmptyState
            title="No loads yet"
            description="Loads will appear here when added."
          />
        )}
        {!loading && loads.length > 0 && (
          <Table
            headers={[
              "Load #",
              "Pickup",
              "Delivery",
              "Pickup Date",
              "Status",
              "Driver",
              "Rate",
              "Actions",
            ]}
          >
            {loads.map((load) => (
              <tr key={load.id}>
                <td className="px-4 py-2 text-sm font-medium text-gray-900">
                  {load.load_number}
                </td>
                <td className="px-4 py-2 text-sm text-gray-700">
                  {load.pickup_location || "—"}
                </td>
                <td className="px-4 py-2 text-sm text-gray-700">
                  {load.delivery_location || "—"}
                </td>
                <td className="px-4 py-2 text-sm text-gray-700">
                  {load.pickup_date || "—"}
                </td>
                <td className="px-4 py-2 text-sm">
                  <StatusBadge status={load.status} />
                </td>
                <td className="px-4 py-2 text-sm text-gray-700">
                  {load.driver
                    ? `${load.driver.first_name} ${load.driver.last_name}`
                    : "—"}
                </td>
                <td className="px-4 py-2 text-sm text-gray-700">
                  {load.rate != null ? `$${load.rate}` : "—"}
                </td>
                <td className="px-4 py-2 text-sm">
                  <Button
                    variant="secondary"
                    onClick={() => navigate(`/loads/${load.id}`)}
                  >
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
