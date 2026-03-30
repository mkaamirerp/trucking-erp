import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PLATFORM } from "../routes";
import { platformAdminFetch, platformAdminJson, PlatformAdminUnauthorizedError } from "../lib/platformAdminFetch";
import { signalPlatformAdminUnauthorized } from "../components/PlatformShellLayout";
import type { PlatformTenantRow } from "../types/platformAdmin";

export default function PlatformTenantDetailPage() {
  const { id } = useParams<{ id: string }>();
  const tenantId = id ? parseInt(id, 10) : NaN;

  const [row, setRow] = useState<PlatformTenantRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);

  const load = useCallback(async () => {
    if (!Number.isFinite(tenantId)) {
      setRow(null);
      setError("Invalid tenant id");
      setLoading(false);
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const data = await platformAdminJson<PlatformTenantRow>(`/platform/tenants/${tenantId}`);
      setRow(data);
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        setRow(null);
        setError(null);
        return;
      }
      setRow(null);
      setError(e instanceof Error ? e.message : "Failed to load tenant");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const runProvision = async () => {
    if (!Number.isFinite(tenantId)) return;
    setActionMsg(null);
    setActionBusy(true);
    try {
      const res = await platformAdminFetch(`/platform/tenants/${tenantId}/provision`, { method: "POST" });
      const text = await res.text();
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try {
          const j = JSON.parse(text) as { detail?: string };
          if (typeof j.detail === "string") msg = j.detail;
        } catch {
          if (text) msg = text.slice(0, 300);
        }
        setActionMsg(msg);
        return;
      }
      setActionMsg("Provision request completed.");
      await load();
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        return;
      }
      setActionMsg(e instanceof Error ? e.message : "Provision failed");
    } finally {
      setActionBusy(false);
    }
  };

  const runRetryProvision = async () => {
    if (!Number.isFinite(tenantId)) return;
    setActionMsg(null);
    setActionBusy(true);
    try {
      const res = await platformAdminFetch(`/platform/tenants/${tenantId}/retry-provision`, { method: "POST" });
      const text = await res.text();
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try {
          const j = JSON.parse(text) as { detail?: string };
          if (typeof j.detail === "string") msg = j.detail;
        } catch {
          if (text) msg = text.slice(0, 300);
        }
        setActionMsg(msg);
        return;
      }
      setActionMsg("Retry provisioning completed.");
      await load();
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        return;
      }
      setActionMsg(e instanceof Error ? e.message : "Retry failed");
    } finally {
      setActionBusy(false);
    }
  };

  if (!Number.isFinite(tenantId)) {
    return <p className="text-sm text-red-400">Invalid tenant id.</p>;
  }

  return (
    <div>
      <div className="text-sm text-slate-400">
        <Link to={PLATFORM.TENANTS} className="text-sky-400 hover:underline">
          ← Tenants
        </Link>
      </div>
      <h1 className="mt-2 text-xl font-semibold text-white tracking-tight">Tenant {tenantId}</h1>

      {actionMsg ? (
        <p className="mt-4 text-sm text-amber-200/90 whitespace-pre-wrap break-words max-w-3xl">{actionMsg}</p>
      ) : null}

      {error ? <p className="mt-4 text-sm text-red-400">{error}</p> : null}
      {loading ? <p className="mt-4 text-sm text-slate-400">Loading…</p> : null}

      {!loading && row ? (
        <>
          <dl className="mt-6 grid gap-3 sm:grid-cols-2 text-sm">
            {(
              [
                ["id", String(row.id)],
                ["slug", row.slug],
                ["name", row.name],
                ["status", row.status],
                ["plan", row.plan ?? "—"],
                ["db_status", row.db_status ?? "—"],
                ["db_last_error", row.db_last_error ?? "—"],
                ["db_last_error_at", row.db_last_error_at ? String(row.db_last_error_at) : "—"],
                ["provisioned_at", row.provisioned_at ? String(row.provisioned_at) : "—"],
                ["created_at", row.created_at ? String(row.created_at) : "—"],
                ["updated_at", row.updated_at ? String(row.updated_at) : "—"],
              ] as const
            ).map(([k, v]) => (
              <div key={k} className="rounded border border-slate-800 bg-slate-900/40 px-3 py-2">
                <dt className="text-xs uppercase tracking-wide text-slate-500">{k}</dt>
                <dd className="mt-1 text-slate-200 break-all">{v}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-8 flex flex-wrap gap-3">
            {(row.db_status === "NOT_PROVISIONED" || row.db_status === "ERROR") && (
              <button
                type="button"
                disabled={actionBusy}
                onClick={() => void runProvision()}
                className="rounded bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-600 disabled:opacity-50"
              >
                Provision DB
              </button>
            )}
            {row.db_status === "ERROR" && (
              <button
                type="button"
                disabled={actionBusy}
                onClick={() => void runRetryProvision()}
                className="rounded border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
              >
                Clear error &amp; retry provision
              </button>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}
