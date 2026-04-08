import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import { PLATFORM } from "../routes";
import {
  getPlatformAdminApiKey,
  setPlatformAdminApiKey,
  verifyPlatformAdminKeyWithServer,
} from "../lib/platformAdminFetch";

export default function PlatformShellLayout() {
  const { pathname } = useLocation();
  const [apiKeyInput, setApiKeyInput] = useState(() => getPlatformAdminApiKey());
  const [authRequired, setAuthRequired] = useState(false);
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    setApiKeyInput(getPlatformAdminApiKey());
  }, []);

  const saveKey = useCallback(async () => {
    setSaveError(null);
    setSaveBusy(true);
    try {
      const v = await verifyPlatformAdminKeyWithServer(apiKeyInput);
      if (!v.ok) {
        if (v.status === 401) {
          setSaveError("Server rejected this key (401). Re-copy from SSM with no spaces or line breaks.");
        } else if (v.status === 503) {
          setSaveError("Platform admin API is disabled on the server (503). Check PLATFORM_ADMIN_API_KEY.");
        } else if (v.status === 0) {
          setSaveError(v.detail ?? "Could not reach the API.");
        } else {
          setSaveError(v.detail ?? `Request failed (${v.status}).`);
        }
        return;
      }
      try {
        setPlatformAdminApiKey(apiKeyInput);
      } catch {
        setSaveError("Browser blocked sessionStorage. Disable strict privacy mode or use a normal window.");
        return;
      }
      setAuthRequired(false);
      window.location.reload();
    } finally {
      setSaveBusy(false);
    }
  }, [apiKeyInput]);

  const clearKey = useCallback(() => {
    setSaveError(null);
    setPlatformAdminApiKey("");
    setApiKeyInput("");
    setAuthRequired(false);
    window.location.reload();
  }, []);

  useEffect(() => {
    const onUnauthorized = () => setAuthRequired(true);
    window.addEventListener("platform-admin-unauthorized", onUnauthorized);
    return () => window.removeEventListener("platform-admin-unauthorized", onUnauthorized);
  }, []);

  const hasKey = Boolean(getPlatformAdminApiKey());

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/80">
        <div className="max-w-6xl mx-auto px-4 py-3">
          <div className="flex flex-wrap items-center gap-4 justify-between">
            <Link to={PLATFORM.HOME} className="text-white font-semibold tracking-tight hover:text-slate-200 shrink-0">
              Platform
            </Link>
            <div className="flex flex-wrap items-end gap-2 text-xs max-w-xl flex-1 min-w-[12rem] justify-end">
            <label className="block text-slate-500 w-full">
              Platform admin key (same as PLATFORM_ADMIN_API_KEY; session only)
            </label>
            <input
              type="password"
              autoComplete="off"
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              placeholder="Paste key → Save"
              className="flex-1 min-w-[12rem] rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
            />
            <button
              type="button"
              onClick={() => void saveKey()}
              disabled={saveBusy}
              className="rounded bg-slate-700 px-2 py-1 text-white hover:bg-slate-600 disabled:opacity-50"
            >
              {saveBusy ? "Checking…" : "Save"}
            </button>
            <button
              type="button"
              onClick={() => void clearKey()}
              className="rounded border border-slate-600 px-2 py-1 text-slate-300 hover:bg-slate-800"
            >
              Clear
            </button>
            </div>
          </div>

          <nav
            className="mt-3 flex flex-wrap gap-x-1 gap-y-1 border-t border-slate-800/80 pt-3 text-sm"
            aria-label="Platform navigation"
          >
            <NavLink
              to={PLATFORM.HOME}
              end
              className={({ isActive }) =>
                `rounded px-2.5 py-1.5 ${isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"}`
              }
            >
              Home
            </NavLink>
            <NavLink
              to={PLATFORM.TENANTS}
              className={() =>
                `rounded px-2.5 py-1.5 ${
                  pathname === PLATFORM.TENANTS || pathname.startsWith(`${PLATFORM.TENANTS}/`)
                    ? "bg-slate-800 text-white"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                }`
              }
            >
              Tenants
            </NavLink>
            <NavLink
              to={PLATFORM.GLOBAL_BOOKING_BROKERS}
              className={({ isActive }) =>
                `rounded px-2.5 py-1.5 ${isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"}`
              }
            >
              Global booking brokers
            </NavLink>
            <NavLink
              to={PLATFORM.LOGIN_FAILURES}
              className={({ isActive }) =>
                `rounded px-2.5 py-1.5 ${isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"}`
              }
            >
              Login failures
            </NavLink>
            <NavLink
              to={PLATFORM.TESTING_UNLOCK_LOGIN}
              className={({ isActive }) =>
                `rounded px-2.5 py-1.5 ${isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"}`
              }
            >
              Unlock login
            </NavLink>
          </nav>
        </div>
        {saveError ? (
          <div className="max-w-6xl mx-auto px-4 pb-2">
            <div className="rounded border border-red-900/60 bg-red-950/50 px-3 py-2 text-sm text-red-100">{saveError}</div>
          </div>
        ) : null}
      </header>

      {(!hasKey || authRequired) && (
        <div className="max-w-6xl mx-auto px-4 pt-4">
          <div className="rounded-lg border border-amber-900/60 bg-amber-950/40 px-4 py-3 text-sm text-amber-100">
            {!hasKey ? (
              <p>
                <strong>Key required.</strong> Set <code className="text-amber-200">PLATFORM_ADMIN_API_KEY</code> on the
                API, paste the same value above, and Save.
              </p>
            ) : (
              <p>
                <strong>Unauthorized (401).</strong> Update the key above, Save, then reload the page or navigate again.
              </p>
            )}
          </div>
        </div>
      )}

      <main className="max-w-6xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}

/** Call when catching PlatformAdminUnauthorizedError so the shell shows the 401 banner. */
export function signalPlatformAdminUnauthorized(): void {
  window.dispatchEvent(new Event("platform-admin-unauthorized"));
}
