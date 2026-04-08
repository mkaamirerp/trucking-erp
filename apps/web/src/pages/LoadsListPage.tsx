import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Card from "@/components/Card";
import Button from "@/components/Button";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";
import { Table } from "@/components/Table";
import { listLoads, Load } from "@/api";
import { formatRouteFromStops, firstPickupAppointmentDate } from "@/utils/loadStops";

export default function LoadsListPage() {
  const navigate = useNavigate();
  const [loads, setLoads] = useState<Load[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [searchApplied, setSearchApplied] = useState("");

  const runQuery = useCallback((q: string) => {
    setLoading(true);
    setError(null);
    listLoads({ page: 1, size: 50, search: q || undefined })
      .then((res) => setLoads(res.items || []))
      .catch((e) => setError(e?.message || "Failed to load loads"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    runQuery("");
  }, [runQuery]);

  const applySearch = () => {
    const q = searchInput.trim();
    setSearchApplied(q);
    runQuery(q);
  };

  const exportCsv = () => {
    const headers = ["load_number", "trip_number", "route", "first_pickup_date", "status", "driver", "rate"];
    const esc = (v: string) => `"${v.replace(/"/g, '""')}"`;
    const lines = [
      headers.join(","),
      ...loads.map((load) => {
        const driver = load.driver ? `${load.driver.first_name} ${load.driver.last_name}`.trim() : "";
        return [
          esc(load.load_number),
          esc(load.trip_number?.trim() || ""),
          esc(formatRouteFromStops(load.stops)),
          esc(firstPickupAppointmentDate(load.stops) || ""),
          esc(load.status),
          esc(driver),
          load.rate != null ? String(load.rate) : "",
        ].join(",");
      }),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `loads-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold">Loads</h1>
          <p className="text-sm text-gray-600">Manage loads and dispatch.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applySearch()}
            placeholder="Search load #, trip #, broker ref…"
            className="min-w-[200px] rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
          />
          <Button type="button" variant="secondary" onClick={applySearch} disabled={loading}>
            Search
          </Button>
          {searchApplied ? (
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setSearchInput("");
                setSearchApplied("");
                runQuery("");
              }}
              disabled={loading}
            >
              Clear
            </Button>
          ) : null}
          {!loading && loads.length > 0 ? (
            <Button type="button" variant="secondary" onClick={exportCsv}>
              Export CSV
            </Button>
          ) : null}
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
              "Trip #",
              "Route (stops)",
              "First pickup date",
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
                <td className="px-4 py-2 text-sm text-gray-700">{load.trip_number?.trim() || "—"}</td>
                <td className="px-4 py-2 text-sm text-gray-700">
                  {formatRouteFromStops(load.stops)}
                </td>
                <td className="px-4 py-2 text-sm text-gray-700">
                  {firstPickupAppointmentDate(load.stops) || "—"}
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
