import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PLATFORM } from "../routes";
import { platformAdminJson, PlatformAdminUnauthorizedError } from "../lib/platformAdminFetch";
import { signalPlatformAdminUnauthorized } from "../components/PlatformShellLayout";
import type { PlatformTenantRow } from "../types/platformAdmin";

export default function PlatformTenantsPage() {
  const [rows, setRows] = useState<PlatformTenantRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await platformAdminJson<PlatformTenantRow[]>("/platform/tenants");
      setRows(Array.isArray(data) ? data : []);
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        setRows(null);
        setError(null);
        return;
      }
      setRows(null);
      setError(e instanceof Error ? e.message : "Failed to load tenants");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div>
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold text-white tracking-tight">Platform tenants</h1>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="text-sm rounded border border-slate-600 px-3 py-1 text-slate-300 hover:bg-slate-800 disabled:opacity-50"
        >
          Refresh
        </button>
      </div>

      {error ? <p className="mt-4 text-sm text-red-400">{error}</p> : null}

      {loading ? <p className="mt-6 text-sm text-slate-400">Loading…</p> : null}

      {!loading && rows && rows.length === 0 ? (
        <p className="mt-6 text-sm text-slate-400">No tenants.</p>
      ) : null}

      {!loading && rows && rows.length > 0 ? (
        <div className="mt-6 overflow-x-auto rounded-lg border border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-slate-400">
              <tr>
                <th className="px-3 py-2 font-medium">ID</th>
                <th className="px-3 py-2 font-medium">Slug</th>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">DB</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {rows.map((t) => (
                <tr key={t.id} className="hover:bg-slate-900/40">
                  <td className="px-3 py-2 text-slate-300">{t.id}</td>
                  <td className="px-3 py-2">
                    <Link className="text-sky-400 hover:underline" to={PLATFORM.TENANT_DETAIL(t.id)}>
                      {t.slug}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-slate-300">{t.name}</td>
                  <td className="px-3 py-2 text-slate-300">{t.status}</td>
                  <td className="px-3 py-2 text-slate-300">{t.db_status ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
