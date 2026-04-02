import { useNavigate } from "react-router-dom";
import { useDashboard } from "../hooks/useDashboard";
import { useMe } from "../hooks/useMe";
import { seedDemoData } from "../api";
import { useAuth } from "../contexts/AuthContext";
import { useState } from "react";

export default function DashboardPage() {
  const navigate = useNavigate();
  const { logout, isLoggingOut } = useAuth();
  const { me } = useMe();
  const { loading, error, summary, drivers = [], driversError, refetch } = useDashboard();
  const [seeding, setSeeding] = useState(false);
  const [seedError, setSeedError] = useState<string | null>(null);

  const handleLogout = async () => {
    if (isLoggingOut) return;
    await logout();
    navigate("/login", { replace: true });
  };

  const handleSeedDemo = async () => {
    setSeeding(true);
    setSeedError(null);
    try {
      await seedDemoData();
      await refetch();
    } catch (e) {
      setSeedError(e instanceof Error ? e.message : "Seed failed");
    } finally {
      setSeeding(false);
    }
  };

  const s = summary;
  const activeLoads = s?.active_loads ?? 0;
  const driversOnDuty = s?.drivers_active ?? 0;
  const inTransit = s?.in_transit ?? 0;
  const delayed = s?.delayed ?? 0;
  const revenue = s?.revenue_this_week ?? 0;
  const revenueFormatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(revenue);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <div className="mx-auto max-w-6xl">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold">Dashboard</h1>
            <p className="mt-2 text-slate-400">
              {loading ? "Loading..." : "Dispatch overview"}
            </p>
          </div>
          <div className="flex items-center gap-4 flex-wrap">
            <div className="text-right">
              <div className="text-xs text-slate-500">Signed in as</div>
              <div className="text-sm font-semibold">{me?.email ?? "—"}</div>
            </div>
            <button
              type="button"
              onClick={handleSeedDemo}
              disabled={loading || seeding}
              className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-sm font-medium disabled:opacity-50"
            >
              {seeding ? "Seeding…" : "Seed demo data"}
            </button>
            <button
              type="button"
              onClick={handleLogout}
              disabled={isLoggingOut}
              className="px-4 py-2 rounded-lg bg-red-900/60 hover:bg-red-800/60 text-red-200 text-sm font-medium disabled:opacity-50 border border-red-700/50"
            >
              {isLoggingOut ? "Logging out…" : "Log out"}
            </button>
          </div>
        </div>

        {error ? (
          <div className="mt-4 rounded-xl border border-amber-700/50 bg-amber-950/30 p-4 text-amber-200">
            <div className="font-semibold">Some data failed to load</div>
            <div className="mt-1 text-xs break-words">{error}</div>
          </div>
        ) : null}
        {seedError ? (
          <div className="mt-4 rounded-xl border border-red-700/50 bg-red-950/30 p-4 text-red-200">
            <div className="font-semibold">Seed failed</div>
            <div className="mt-1 text-xs break-words">{seedError}</div>
          </div>
        ) : null}

        <section className="mt-6 grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
          <KpiCard
            icon="🚛"
            iconBg="green"
            value={loading ? "…" : String(activeLoads)}
            label="Active Loads"
          />
          <KpiCard
            icon="🚐"
            iconBg="blue"
            value={loading ? "…" : String(driversOnDuty)}
            label="Drivers On Duty"
          />
          <KpiCard
            icon="🚚"
            iconBg="yellow"
            value={loading ? "…" : String(inTransit)}
            label="In Transit"
          />
          <KpiCard
            icon="🚛"
            iconBg="red"
            value={loading ? "…" : String(delayed)}
            label="Delayed"
          />
          <KpiCard
            value={loading ? "…" : revenueFormatted}
            label="Revenue This Week"
            revenue
          />
        </section>

        <section className="mt-6 rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <div className="font-semibold mb-3">
            Drivers ({(drivers ?? []).length || (s?.drivers_active ?? 0)} on duty)
          </div>
          {(drivers?.length ?? 0) > 0 ? (
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {(drivers ?? []).map((d) => (
                <li
                  key={d.id}
                  className="flex items-center gap-3 rounded-lg border border-slate-700/50 bg-slate-800/40 px-4 py-3"
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-600 text-sm font-semibold">
                    {(d.first_name?.[0] ?? "") + (d.last_name?.[0] ?? "")}
                  </span>
                  <div className="min-w-0">
                    <div className="font-medium text-slate-100">
                      {d.first_name} {d.last_name}
                    </div>
                    {d.email ? (
                      <div className="truncate text-xs text-slate-400">{d.email}</div>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : (s?.drivers_active ?? 0) > 0 ? (
            <div className="space-y-2">
              <p className="text-sm text-slate-400">
                {s.drivers_active} drivers on duty. List could not be loaded.
                {driversError ? ` (${driversError})` : ""}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => refetch()}
                  className="px-3 py-1.5 rounded-md text-sm font-medium bg-slate-700 text-slate-200 hover:bg-slate-600"
                >
                  Retry loading drivers
                </button>
                <a href="/loads" className="px-3 py-1.5 rounded-md text-sm font-medium text-sky-400 hover:underline">
                  Open Loads
                </a>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-400">
              No drivers yet. Use &quot;Seed demo data&quot; above to add demo drivers and loads.
            </p>
          )}
        </section>

        <div className="mt-8 rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <div className="font-semibold mb-2">Quick links</div>
          <ul className="text-sm text-slate-400 space-y-1">
            <li>• <a href="/loads" className="text-sky-400 hover:underline">Loads</a> — view and manage loads (drivers on assignments)</li>
            <li>• <a href="/payroll/pay-runs" className="text-sky-400 hover:underline">Pay runs</a> — payroll</li>
            <li>• <a href="/operations/driver-onboarding-review" className="text-sky-400 hover:underline">Driver onboarding</a> — admin</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

function KpiCard({
  icon,
  iconBg,
  value,
  label,
  revenue,
}: {
  icon?: string;
  iconBg?: "green" | "blue" | "yellow" | "red";
  value: string;
  label: string;
  revenue?: boolean;
}) {
  const iconBgClass =
    iconBg === "green"
      ? "bg-emerald-500/20 text-emerald-400"
      : iconBg === "blue"
        ? "bg-blue-500/20 text-blue-400"
        : iconBg === "yellow"
          ? "bg-amber-500/20 text-amber-400"
          : iconBg === "red"
            ? "bg-red-500/20 text-red-400"
            : "";

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 flex flex-col gap-2">
      {icon ? (
        <span className={`inline-flex w-9 h-9 items-center justify-center rounded-lg text-lg ${iconBgClass}`}>
          {icon}
        </span>
      ) : null}
      <div className={`text-2xl font-semibold ${revenue ? "text-emerald-400" : ""}`}>{value}</div>
      <div className="text-sm text-slate-400">{label}</div>
    </div>
  );
}
