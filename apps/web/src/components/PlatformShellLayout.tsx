import { Link, NavLink, Outlet } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import { PLATFORM } from "../routes";
import { getPlatformAdminApiKey, setPlatformAdminApiKey } from "../lib/platformAdminFetch";

export default function PlatformShellLayout() {
  const [apiKeyInput, setApiKeyInput] = useState(() => getPlatformAdminApiKey());
  const [authRequired, setAuthRequired] = useState(false);

  useEffect(() => {
    setApiKeyInput(getPlatformAdminApiKey());
  }, []);

  const saveKey = useCallback(() => {
    setPlatformAdminApiKey(apiKeyInput);
    setAuthRequired(false);
    window.location.reload();
  }, [apiKeyInput]);

  const clearKey = useCallback(() => {
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
        <div className="max-w-6xl mx-auto px-4 py-3 flex flex-wrap items-center gap-4 justify-between">
          <div className="flex items-center gap-6">
            <Link to={PLATFORM.HOME} className="text-white font-semibold tracking-tight hover:text-slate-200">
              Platform
            </Link>
            <nav className="flex gap-4 text-sm">
              <NavLink
                to={PLATFORM.HOME}
                end
                className={({ isActive }) =>
                  isActive ? "text-white" : "text-slate-400 hover:text-slate-200"
                }
              >
                Home
              </NavLink>
              <NavLink
                to={PLATFORM.TENANTS}
                className={({ isActive }) =>
                  isActive ? "text-white" : "text-slate-400 hover:text-slate-200"
                }
              >
                Tenants
              </NavLink>
              <NavLink
                to={PLATFORM.LOGIN_FAILURES}
                className={({ isActive }) =>
                  isActive ? "text-white" : "text-slate-400 hover:text-slate-200"
                }
              >
                Login failures
              </NavLink>
            </nav>
          </div>
          <div className="flex flex-wrap items-end gap-2 text-xs max-w-xl">
            <label className="block text-slate-500 w-full">X-Platform-Admin-Key (session only)</label>
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
              className="rounded bg-slate-700 px-2 py-1 text-white hover:bg-slate-600"
            >
              Save
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
