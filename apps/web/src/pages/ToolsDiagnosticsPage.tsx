import { useEffect, useState } from "react";
import { fetchWithTenant } from "../api";

const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

type ColumnRow = { name: string; type: string; nullable: boolean; default: string | null };

export default function ToolsDiagnosticsPage() {
  const [unlocked, setUnlocked] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [wrong, setWrong] = useState(false);
  const [driversCount, setDriversCount] = useState<number | null>(null);
  const [driversColumns, setDriversColumns] = useState<ColumnRow[] | null>(null);
  const [loadingCount, setLoadingCount] = useState(false);
  const [loadingDescribe, setLoadingDescribe] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tables, setTables] = useState<string[] | null>(null);
  const [selectedTable, setSelectedTable] = useState<string>("drivers");
  const [sampleRows, setSampleRows] = useState<Record<string, unknown>[] | null>(null);
  const [loadingTables, setLoadingTables] = useState(false);
  const [loadingSample, setLoadingSample] = useState(false);
  const [unlockError, setUnlockError] = useState<string | null>(null);

  const checkLocked = async (res: Response): Promise<boolean> => {
    if (res.status !== 401) return false;
    const body = await res.clone().json().catch(() => ({}));
    const detail = body?.detail ?? "";
    if (String(detail).includes("TOOLS_LOCKED")) {
      setUnlocked(false);
      return true;
    }
    return false;
  };

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/tools/ping`, { credentials: "include" })
      .then((res) => {
        if (cancelled) return;
        setUnlocked(res.ok);
      })
      .catch(() => {
        if (!cancelled) setUnlocked(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setWrong(false);
    setUnlockError(null);
    fetch(`${API_BASE}/tools/unlock`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    })
      .then(async (res) => {
        const data = await res.json().catch(() => ({}));
        if (res.status === 503) {
          setUnlockError("Server returned 503 — API is running old code. Deploy latest code and restart the API, then use password: devtools123");
          setWrong(false);
          return;
        }
        if (data.ok) {
          window.location.reload();
        } else {
          setUnlockError(null);
          setWrong(true);
        }
      })
      .catch(() => {
        setWrong(true);
        setUnlockError("Network error. Try again.");
      });
  };

  const handleDescribeDrivers = async () => {
    setError(null);
    setLoadingDescribe(true);
    const res = await fetchWithTenant(`${API_BASE}/tools/db/describe?table=drivers`);
    if (await checkLocked(res)) {
      setLoadingDescribe(false);
      return;
    }
    setLoadingDescribe(false);
    if (!res.ok) {
      const t = await res.text();
      setError(t || "Describe failed");
      setDriversColumns(null);
      return;
    }
    const data = await res.json();
    setDriversColumns(data.columns ?? []);
    setError(null);
  };

  const handleCountDrivers = async () => {
    setError(null);
    setLoadingCount(true);
    const res = await fetchWithTenant(`${API_BASE}/tools/db/count?table=drivers`);
    if (await checkLocked(res)) {
      setLoadingCount(false);
      return;
    }
    setLoadingCount(false);
    if (!res.ok) {
      const t = await res.text();
      setError(t || "Count failed");
      setDriversCount(null);
      return;
    }
    const data = await res.json();
    setDriversCount(data.count ?? 0);
    setError(null);
  };

  const handleLoadTables = async () => {
    setError(null);
    setLoadingTables(true);
    const res = await fetchWithTenant(`${API_BASE}/tools/db/tables`);
    if (await checkLocked(res)) {
      setLoadingTables(false);
      return;
    }
    setLoadingTables(false);
    if (!res.ok) {
      const t = await res.text();
      setError(t || "Load tables failed");
      setTables(null);
      return;
    }
    const data = await res.json();
    setTables(data.tables ?? []);
    setError(null);
  };

  const handleSampleTable = async () => {
    setError(null);
    setLoadingSample(true);
    setSampleRows(null);
    const res = await fetchWithTenant(
      `${API_BASE}/tools/db/sample?table=${encodeURIComponent(selectedTable)}&limit=10`
    );
    if (await checkLocked(res)) {
      setLoadingSample(false);
      return;
    }
    setLoadingSample(false);
    if (!res.ok) {
      const t = await res.text();
      setError(t || "Sample failed");
      setSampleRows(null);
      return;
    }
    const data = await res.json();
    setSampleRows(data.rows ?? []);
    setError(null);
  };

  if (unlocked === null) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-700">
        Loading…
      </div>
    );
  }

  if (!unlocked) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <form onSubmit={handleSubmit} className="space-y-3 w-full max-w-xs">
          <h1 className="text-lg font-medium">DB Inspector</h1>
          <p className="text-sm text-gray-600">Your tool to see the database in the browser (no terminal). Enter password to unlock.</p>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
            autoComplete="current-password"
          />
          {wrong && (
            <p className="text-sm text-red-600">Wrong password.</p>
          )}
          {unlockError && (
            <p className="text-sm text-amber-600">{unlockError}</p>
          )}
          <button
            type="submit"
            className="w-full px-3 py-2 rounded bg-gray-800 text-white text-sm font-medium hover:bg-gray-700"
          >
            Unlock
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="min-h-screen p-6 text-gray-800">
      <h1 className="text-lg font-medium mb-2">DB Inspector (unlocked)</h1>
      <p className="text-sm text-gray-600 mb-6">View tables, schema, and sample rows in the browser. Cookie expires automatically.</p>

      <section className="mb-8">
        <h2 className="text-base font-medium mb-3">Tables</h2>
        <div className="flex gap-2 mb-3">
          <button
            type="button"
            onClick={handleLoadTables}
            disabled={loadingTables}
            className="px-3 py-2 rounded bg-gray-800 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-50"
          >
            {loadingTables ? "Loading…" : "Load tables"}
          </button>
        </div>
        {tables !== null && (
          <ul className="flex flex-wrap gap-2 mb-4">
            {tables.map((t) => (
              <li key={t}>
                <button
                  type="button"
                  onClick={() => setSelectedTable(t)}
                  className={`px-2 py-1 rounded text-sm font-mono ${
                    selectedTable === t
                      ? "bg-gray-800 text-white"
                      : "bg-gray-100 text-gray-800 hover:bg-gray-200"
                  }`}
                >
                  {t}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mb-8">
        <h2 className="text-base font-medium mb-3">Sample rows</h2>
        <div className="flex gap-2 mb-3">
          <button
            type="button"
            onClick={handleSampleTable}
            disabled={loadingSample}
            className="px-3 py-2 rounded bg-gray-800 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-50"
          >
            {loadingSample ? "Loading…" : "Sample selected table"}
          </button>
          <span className="text-sm text-gray-600 self-center">Table: {selectedTable}</span>
        </div>
        {sampleRows !== null && sampleRows.length > 0 && (
          <div className="overflow-x-auto border border-gray-300 rounded">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-100">
                  {Object.keys(sampleRows[0]).map((col) => (
                    <th key={col} className="border border-gray-300 px-2 py-1.5 text-left font-medium whitespace-nowrap">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sampleRows.map((row, i) => (
                  <tr key={i}>
                    {Object.keys(sampleRows[0]).map((col) => (
                      <td key={col} className="border border-gray-300 px-2 py-1.5 whitespace-nowrap">
                        {row[col] != null ? String(row[col]) : "—"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {sampleRows !== null && sampleRows.length === 0 && (
          <p className="text-sm text-gray-600">No rows.</p>
        )}
      </section>

      <section className="mb-8">
        <h2 className="text-base font-medium mb-3">Drivers Inspector</h2>
        <div className="flex gap-2 mb-4">
          <button
            type="button"
            onClick={handleDescribeDrivers}
            disabled={loadingDescribe}
            className="px-3 py-2 rounded bg-gray-800 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-50"
          >
            {loadingDescribe ? "Loading…" : "Describe drivers"}
          </button>
          <button
            type="button"
            onClick={handleCountDrivers}
            disabled={loadingCount}
            className="px-3 py-2 rounded bg-gray-800 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-50"
          >
            {loadingCount ? "Loading…" : "Count drivers"}
          </button>
        </div>
        {error && <p className="text-sm text-red-600 mb-2">{error}</p>}
        {driversCount !== null && (
          <div className="mb-4">
            <p className="text-sm text-gray-600 mb-1">Row count</p>
            <p className="text-3xl font-semibold tabular-nums">{driversCount}</p>
          </div>
        )}
        {driversColumns !== null && driversColumns.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full border border-gray-300 text-sm">
              <thead>
                <tr className="bg-gray-100">
                  <th className="border border-gray-300 px-3 py-2 text-left font-medium">Column</th>
                  <th className="border border-gray-300 px-3 py-2 text-left font-medium">Type</th>
                  <th className="border border-gray-300 px-3 py-2 text-left font-medium">Nullable</th>
                  <th className="border border-gray-300 px-3 py-2 text-left font-medium">Default</th>
                </tr>
              </thead>
              <tbody>
                {driversColumns.map((col) => (
                  <tr key={col.name}>
                    <td className="border border-gray-300 px-3 py-2 font-mono">{col.name}</td>
                    <td className="border border-gray-300 px-3 py-2">{col.type}</td>
                    <td className="border border-gray-300 px-3 py-2">{col.nullable ? "Yes" : "No"}</td>
                    <td className="border border-gray-300 px-3 py-2 font-mono text-gray-600">
                      {col.default ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
