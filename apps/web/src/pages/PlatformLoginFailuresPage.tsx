/**
 * Operator-only: recent login failures from platform DB (X-Platform-Admin-Key).
 * Key UX lives in PlatformShellLayout; API calls use platformAdminJson.
 */
import { useCallback, useState } from "react";
import {
  getPlatformAdminApiKey,
  platformAdminJson,
  PlatformAdminHttpError,
  PlatformAdminUnauthorizedError,
} from "../lib/platformAdminFetch";
import { signalPlatformAdminUnauthorized } from "../components/PlatformShellLayout";

type Row = {
  id: number;
  created_at: string;
  tenant_id: number;
  tenant_slug: string;
  tenant_auth_mode: string;
  reason_code: string;
  email_fingerprint: string;
  request_id: string | null;
  request_host: string | null;
};

const REASON_HINTS = [
  "login_fail_no_tenant_user",
  "login_fail_no_workspace_member",
  "login_fail_verify_tenant_password",
  "login_fail_tenant_auth_incomplete",
  "login_fail_no_platform_user",
  "login_fail_no_platform_membership",
  "login_fail_verify_platform_password",
];

export default function PlatformLoginFailuresPage() {
  const [tenantId, setTenantId] = useState("");
  const [reason, setReason] = useState("");
  const [fingerprint, setFingerprint] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchRows = useCallback(async () => {
    setError(null);
    setLoading(true);
    if (!getPlatformAdminApiKey().trim()) {
      setRows(null);
      setLoading(false);
      signalPlatformAdminUnauthorized();
      return;
    }
    const params = new URLSearchParams();
    if (tenantId.trim()) params.set("tenant_id", tenantId.trim());
    if (reason.trim()) params.set("reason", reason.trim());
    if (fingerprint.trim()) params.set("email_fingerprint", fingerprint.trim().toLowerCase());
    params.set("limit", "200");
    const qs = params.toString();
    const path = `/platform/login-failures${qs ? `?${qs}` : ""}`;
    try {
      const data = await platformAdminJson<Row[]>(path);
      setRows(data);
    } catch (e) {
      setRows(null);
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        return;
      }
      if (e instanceof PlatformAdminHttpError) {
        setError(e.message);
        return;
      }
      setError("Network error");
    } finally {
      setLoading(false);
    }
  }, [tenantId, reason, fingerprint]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-white">Login failures</h1>
        <p className="mt-1 text-sm text-slate-400">
          Correlates with API logs <code className="text-slate-300">event=login_failed</code>. Requires{" "}
          <code className="text-slate-300">PLATFORM_ADMIN_API_KEY</code> on the API.
        </p>
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4 space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="block text-xs font-medium text-slate-400">
            Tenant ID
            <input
              type="text"
              inputMode="numeric"
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              placeholder="e.g. 53"
            />
          </label>
          <label className="block text-xs font-medium text-slate-400">
            Reason contains
            <input
              list="reason-hints"
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="substring of reason_code"
            />
            <datalist id="reason-hints">
              {REASON_HINTS.map((r) => (
                <option key={r} value={r} />
              ))}
            </datalist>
          </label>
          <label className="block text-xs font-medium text-slate-400">
            Email fingerprint
            <input
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
              value={fingerprint}
              onChange={(e) => setFingerprint(e.target.value)}
              placeholder="16-char sha256 prefix from logs"
            />
          </label>
        </div>
        <button
          type="button"
          onClick={() => void fetchRows()}
          disabled={loading}
          className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {loading ? "Loading…" : "Load"}
        </button>
      </div>

      {error && (
        <div className="rounded border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-200">{error}</div>
      )}

      {rows && (
        <div className="overflow-x-auto rounded border border-slate-800">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-slate-900 text-slate-400">
              <tr>
                <th className="px-2 py-2 font-medium">Time</th>
                <th className="px-2 py-2 font-medium">Tenant</th>
                <th className="px-2 py-2 font-medium">Mode</th>
                <th className="px-2 py-2 font-medium">Reason</th>
                <th className="px-2 py-2 font-medium">Email fp</th>
                <th className="px-2 py-2 font-medium">Host</th>
                <th className="px-2 py-2 font-medium">Req ID</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-2 py-6 text-center text-slate-500">
                    No rows
                  </td>
                </tr>
              ) : (
                rows.map((r) => (
                  <tr key={r.id} className="bg-slate-950/80">
                    <td className="whitespace-nowrap px-2 py-1.5 text-slate-300">{r.created_at}</td>
                    <td className="whitespace-nowrap px-2 py-1.5 text-slate-300">
                      {r.tenant_slug} <span className="text-slate-500">({r.tenant_id})</span>
                    </td>
                    <td className="px-2 py-1.5 text-slate-300">{r.tenant_auth_mode}</td>
                    <td className="max-w-[14rem] truncate px-2 py-1.5 font-mono text-amber-200/90" title={r.reason_code}>
                      {r.reason_code}
                    </td>
                    <td className="whitespace-nowrap px-2 py-1.5 font-mono text-slate-400">{r.email_fingerprint}</td>
                    <td className="px-2 py-1.5 text-slate-400">{r.request_host ?? "—"}</td>
                    <td className="max-w-[8rem] truncate px-2 py-1.5 text-slate-500" title={r.request_id ?? ""}>
                      {r.request_id ?? "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
