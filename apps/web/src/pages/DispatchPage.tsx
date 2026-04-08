/**
 * Dispatch Workspace — Layout C (table default) + Layout B (board optional)
 * Summary / navigation only: ribbon + table/board; selecting a load opens the canonical load workspace (/loads/:id).
 * Primary fields in rows/cards: Load #, Trip # (read-only), Route, Status.
 * Delivered moved to ribbon tab, not a board column.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { clsx } from "clsx";
import {
  getDispatchBoard,
  listTrucks,
  listDrivers,
  listTrailers,
  type Load,
  type DispatchBoard,
  type Truck,
  type Driver,
  type Trailer,
} from "@/api";
import { OPS, ADMIN } from "@/routes";
import { getTenantSlugFromHost } from "@/tenant";
import { useWorkspaceLayout } from "@/hooks/useWorkspaceLayout";
import { useMe } from "@/hooks/useMe";
import { useAuth } from "@/contexts/AuthContext";
import { formatRouteFromStops, sortedStops, firstPickupStop, lastDropStop, formatStopCityState } from "@/utils/loadStops";

const RIBBON_TABS = [
  { key: "active", label: "Active", statuses: ["unassigned", "assigned", "dispatched"] },
  { key: "in_transit", label: "In Transit", statuses: ["arrived_pickup", "in_transit", "arrived_delivery"] },
  { key: "at_pickup", label: "At Pickup", statuses: ["arrived_pickup"] },
  { key: "at_delivery", label: "At Delivery", statuses: ["arrived_delivery"] },
  { key: "delivered", label: "Delivered", statuses: ["delivered"] },
  { key: "problem", label: "Problem / Hold", statuses: ["issue_hold"] },
] as const;

const STATUS_LABELS: Record<string, string> = {
  unassigned: "Unassigned",
  assigned: "Assigned",
  dispatched: "Dispatched",
  arrived_pickup: "At Pickup",
  in_transit: "In Transit",
  arrived_delivery: "At Delivery",
  delivered: "Delivered",
  issue_hold: "Issue/Hold",
};

const STATUS_BADGE_CLASS: Record<string, string> = {
  unassigned: "bg-slate-500/15 text-slate-300 border border-slate-500/30",
  assigned: "bg-slate-500/15 text-slate-300 border border-slate-500/30",
  dispatched: "bg-blue-500/15 text-blue-300 border border-blue-500/30",
  arrived_pickup: "bg-amber-500/15 text-amber-300 border border-amber-500/30",
  in_transit: "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30",
  arrived_delivery: "bg-amber-500/15 text-amber-300 border border-amber-500/30",
  delivered: "bg-slate-400/15 text-slate-400 border border-slate-400/30",
  issue_hold: "bg-red-500/15 text-red-300 border border-red-500/30",
};

const CARD_BADGE_CLASS: Record<string, string> = {
  unassigned: "bg-[#1c2233] text-[#9ca3af] border border-[#2b3347]",
  assigned:   "bg-[#f5a623] text-[#0a0c12] border border-[#f5a623]",
  dispatched: "bg-[#0d1f1a] text-[#34d399] border border-[#10b981]/40",
};

const CARD_ACCENT_COLOR: Record<string, string> = {
  unassigned: "#4b5563",
  assigned:   "#f5a623",
  dispatched: "#10b981",
};

const COLUMN_DOT: Record<string, { color: string; glow: string }> = {
  unassigned: { color: "#4b5563", glow: "0 0 6px #4b5563" },
  assigned:   { color: "#f5a623", glow: "0 0 6px #f5a623" },
  dispatched: { color: "#10b981", glow: "0 0 6px #10b981" },
};

const COLUMN_BG: Record<string, string> = {
  unassigned: "#0c0f16",
  assigned:   "#0c0f16",
  dispatched: "#0c0f16",
};

const COLUMN_COUNT_CLASS: Record<string, string> = {
  unassigned: "bg-[#1c2235] text-[#6b7280] border border-[#252a38]",
  assigned:   "bg-[#2a1f0a] text-[#f5a623] border border-[#3d2d0e]",
  dispatched: "bg-[#0d2420] text-[#10b981] border border-[#0f302a]",
};

const COLUMN_WIDTH = 356;

function formatRoute(load: Load): string {
  return formatRouteFromStops(load.stops);
}

function formatTripNumber(load: Load): string {
  const t = load.trip_number?.trim();
  return t || "—";
}

function uiTripStyleId(load: Load): string {
  // UI-only: do not imply a real dispatch_trips row exists.
  const n = String(load.id ?? "").padStart(4, "0");
  if (load.status === "assigned") return `TRIPAS-${n}`;
  if (load.status === "dispatched") return `TRIPSPC-${n}`;
  return `L-${(load.load_number || "").replace(/^L-/, "")}`;
}

function uiDeadMiles(load: Load): number | null {
  // UI-only placeholder; we do not have dead miles in schema yet.
  if (!load.miles || load.miles <= 0) return null;
  const seed = (load.id ?? 0) % 9; // deterministic per card
  return Math.max(0, Math.round(load.miles * (0.05 + seed * 0.01)));
}

/** Board card — v2 design: broker headline, split route, miles pills, meta, driver footer. */
function LoadCard({
  load,
  trucks,
  drivers,
  trailers,
  onSelect,
}: {
  load: Load;
  trucks: Truck[];
  drivers: Driver[];
  trailers: Trailer[];
  onSelect: (load: Load) => void;
}) {
  const [focused, setFocused] = useState(false);

  const status       = load.status;
  const statusAccent = CARD_ACCENT_COLOR[status] ?? "#4b5563";
  const statusLabel  = STATUS_LABELS[status] ?? status;
  const badgeClass   = CARD_BADGE_CLASS[status] ?? CARD_BADGE_CLASS.unassigned;

  const originFull  = formatStopCityState(firstPickupStop(load.stops));
  const destFull    = formatStopCityState(lastDropStop(load.stops));
  const [origin, originState] = originFull.includes(", ")
    ? originFull.split(", ") as [string, string]
    : [originFull, ""];
  const [dest, destState] = destFull.includes(", ")
    ? destFull.split(", ") as [string, string]
    : [destFull, ""];

  const driverInitials = load.driver
    ? `${load.driver.first_name[0] ?? ""}${load.driver.last_name[0] ?? ""}`.toUpperCase()
    : "";

  return (
    <div
      className={clsx(
        "relative rounded-xl border bg-[#141a25] border-[#242b3c] p-3 mb-3 cursor-pointer transition-all",
        "hover:bg-[#161e2c]",
        status === "dispatched" ? "shadow-[0_0_0_1px_rgba(16,185,129,0.15),0_0_22px_rgba(16,185,129,0.08)]" : ""
      )}
      style={{
        borderLeftWidth: 4,
        borderLeftStyle: "solid",
        borderLeftColor: statusAccent,
      }}
      onClick={() => onSelect(load)}
      onMouseEnter={() => setFocused(true)}
      onMouseLeave={() => setFocused(false)}
    >
      {/* HEADER */}
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="text-[14px] font-semibold text-white leading-tight">
            {load.broker_name_snapshot || "—"}
          </div>
          <div className="text-[10px] font-mono text-[#6b7280] mt-0.5">
            #{load.status === "unassigned" ? load.load_number : uiTripStyleId(load)}
          </div>
        </div>
        <span className={clsx("text-[10px] font-semibold px-2 py-0.5 rounded-md", badgeClass)}>
          {statusLabel}
        </span>
      </div>

      {/* ROUTE */}
      <div className="flex items-center justify-between bg-[#0f141f] rounded-lg px-3 py-2 mb-2 border border-[#242b3c]">
        <div>
          <div className="text-[12px] font-medium text-white">{origin}</div>
          <div className="text-[10px] text-[#6b7280]">{originState}</div>
        </div>
        <div className="text-[#6b7280] text-[10px]">→</div>
        <div className="text-right">
          <div className="text-[12px] font-medium text-white">{dest}</div>
          <div className="text-[10px] text-[#6b7280]">{destState}</div>
        </div>
      </div>

      {/* MILES */}
      <div className="flex gap-2 mb-2">
        <div className="flex-1 flex items-center justify-between bg-[#153452] border border-[#244b78] rounded-md px-2 py-1">
          <span className="text-[9px] text-[#7aa8d4] uppercase tracking-wide">Loaded</span>
          <span className="text-[11px] font-bold text-[#4d9fff]">
            {load.miles ? `${load.miles} mi` : "— mi"}
          </span>
        </div>
        <div className="flex-1 flex items-center justify-between bg-[#2a1b1f] border border-[#3b232a] rounded-md px-2 py-1">
          <span className="text-[9px] text-[#ef4444] uppercase tracking-wide">Dead</span>
          <span className="text-[11px] font-bold text-[#ef4444]">
            {uiDeadMiles(load) != null ? `${uiDeadMiles(load)} mi` : "— mi"}
          </span>
        </div>
      </div>

      {/* META */}
      <div className="flex items-center text-[10px] text-[#9ca3af] gap-3">
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-[#f5a623]/80" />
          <span>{load.equipment_type || "—"}</span>
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-[#9ca3af]/40" />
          <span>{load.estimated_weight != null ? `${load.estimated_weight.toLocaleString()} lbs` : "—"}</span>
        </span>
        <span className="ml-auto text-[12px] font-semibold text-[#10b981]">
          {load.rate ? `$${load.rate.toLocaleString()}` : "—"}
        </span>
      </div>

      {/* FOOTER — assigned */}
      {status === "assigned" && (
        <div
          className="flex items-center gap-2 pt-2 mt-2 border-t border-[#242b3c]"
          onClick={(e) => e.stopPropagation()}
        >
          {load.driver && (
            <div className="h-6 w-6 rounded-full bg-[#f5a623]/20 border border-[#f5a623]/60 flex items-center justify-center shrink-0">
              <span className="text-[9px] font-bold text-[#f5a623]">{driverInitials}</span>
            </div>
          )}
          <div className="min-w-0 flex-1 leading-tight">
            <div className="text-[11px] text-[#94a3b8] truncate">
              {load.driver ? `${load.driver.first_name} ${load.driver.last_name}` : "—"}
            </div>
            <div className="text-[10px] text-[#6b7280] truncate">
              {load.truck ? `Truck ${load.truck.unit_number}` : "—"}
            </div>
          </div>
          {load.trailer && (
            <span className="shrink-0 px-2 py-0.5 rounded-md text-[10px] bg-[#101522] border border-[#242b3c] text-[#9ca3af]">
              {load.trailer.unit_number}
            </span>
          )}
          {focused ? (
            <span className="shrink-0 px-2 py-0.5 rounded-md text-[10px] bg-[#101522] border border-[#242b3c] text-[#94a3b8]">
              View only
            </span>
          ) : null}
        </div>
      )}

      {/* FOOTER — dispatched */}
      {status === "dispatched" && (
        <div
          className="flex items-center gap-2 pt-2 mt-2 border-t border-[#242b3c]"
          onClick={(e) => e.stopPropagation()}
        >
          {load.driver && (
            <div className="h-6 w-6 rounded-full bg-[#10b981]/15 border border-[#10b981]/60 flex items-center justify-center shrink-0">
              <span className="text-[9px] font-bold text-[#10b981]">{driverInitials}</span>
            </div>
          )}
          <span className="text-[11px] text-[#94a3b8] truncate flex-1">
            {load.driver ? `${load.driver.first_name} ${load.driver.last_name}` : "—"}
            {load.truck ? ` · Truck ${load.truck.unit_number}` : ""}
          </span>
          {load.trailer && (
            <span className="shrink-0 px-2 py-0.5 rounded-md text-[10px] bg-[#101522] border border-[#242b3c] text-[#9ca3af]">
              {load.trailer.unit_number}
            </span>
          )}
          {focused ? (
            <span className="shrink-0 px-2 py-0.5 rounded-md text-[10px] bg-[#101522] border border-[#242b3c] text-[#94a3b8]">
              View only
            </span>
          ) : null}
        </div>
      )}
    </div>
  );
}

function StatusColumn({
  statusKey,
  label,
  loads,
  trucks,
  drivers,
  trailers,
  onSelectLoad,
  onEmptyAction,
}: {
  statusKey: string;
  label: string;
  loads: Load[];
  trucks: Truck[];
  drivers: Driver[];
  trailers: Trailer[];
  onSelectLoad: (load: Load) => void;
  onEmptyAction?: () => void;
}) {
  const dot = COLUMN_DOT[statusKey] ?? COLUMN_DOT.unassigned;
  const colBg = COLUMN_BG[statusKey] ?? "#0e1018";
  const countClass = COLUMN_COUNT_CLASS[statusKey] ?? COLUMN_COUNT_CLASS.unassigned;

  return (
    <div
      className="flex-shrink-0 flex flex-col rounded-xl border border-[#1c2235] shadow-[0_0_0_1px_rgba(0,0,0,0.25)]"
      style={{ width: COLUMN_WIDTH, background: colBg }}
    >
      <div
        className="px-3 py-2.5 border-b border-[#1c2235] flex items-center justify-between"
        style={{ background: colBg }}
      >
        <div className="flex items-center gap-2">
          <span
            className="h-2 w-2 rounded-full shrink-0"
            style={{ backgroundColor: dot.color, boxShadow: dot.glow }}
          />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-[#9ca3af]">{label.toUpperCase()}</span>
        </div>
        <span className={clsx("text-[10px] font-medium px-2 py-0.5 rounded-full tabular-nums", countClass)}>
          {loads.length}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto min-h-[60px] max-h-[calc(100vh-260px)] p-3 space-y-1.5">
        {loads.map((load) => (
          <LoadCard
            key={load.id}
            load={load}
            trucks={trucks}
            drivers={drivers}
            trailers={trailers}
            onSelect={onSelectLoad}
          />
        ))}
        {loads.length === 0 && (
          <div className="text-center py-6 text-[#64748b] text-xs">
            {statusKey === "unassigned" && onEmptyAction ? (
              <button onClick={onEmptyAction} className="text-[#f5a623] hover:underline">New Load</button>
            ) : (
              "—"
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function DispatchPage() {
  // React-router paths are tenant-agnostic; tenant selection is via host + cookie.
  const slug = "";
  const navigate = useNavigate();
  const { logout, isLoggingOut } = useAuth();
  const { me } = useMe();
  const [layoutMode, setLayoutMode] = useWorkspaceLayout("dispatch", me?.user_id ?? null, "board");

  const [board, setBoard] = useState<DispatchBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [searchDebounced, setSearchDebounced] = useState("");
  const [ribbonTab, setRibbonTab] = useState<(typeof RIBBON_TABS)[number]["key"]>("active");
  const [mapOpen, setMapOpen] = useState(false);
  const [trucks, setTrucks] = useState<Truck[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [trailers, setTrailers] = useState<Trailer[]>([]);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [selectedLoad, setSelectedLoad] = useState<Load | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setSearchDebounced(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const refreshBoard = useCallback(() => {
    setLoading(true);
    getDispatchBoard(searchDebounced || undefined)
      .then(setBoard)
      .catch(() => setBoard({}))
      .finally(() => setLoading(false));
  }, [searchDebounced]);

  useEffect(() => {
    refreshBoard();
  }, [refreshBoard]);

  useEffect(() => {
    Promise.all([
      listTrucks({ status: ["active"], size: 100 }).then((r) => setTrucks(r.items ?? [])),
      listDrivers({ include_inactive: false }).then(setDrivers),
      listTrailers({ status: ["active"], size: 100 }).then((r) => setTrailers(r.items ?? [])),
    ]).catch(() => {});
  }, []);

  const ribbon = RIBBON_TABS.find((t) => t.key === ribbonTab) ?? RIBBON_TABS[0];
  const statusesInRibbon = ribbon.statuses;

  const loadsForView = useMemo(() => {
    const out: Load[] = [];
    for (const s of statusesInRibbon) {
      const arr = board?.[s] ?? [];
      out.push(...arr);
    }
    return out;
  }, [board, statusesInRibbon]);

  const groupedForTable = useMemo(() => {
    const groups: { status: string; loads: Load[] }[] = [];
    for (const s of statusesInRibbon) {
      const arr = board?.[s] ?? [];
      if (arr.length > 0) {
        groups.push({ status: s, loads: arr });
      }
    }
    return groups;
  }, [board, statusesInRibbon]);

  const boardColumns = useMemo(() => {
    return statusesInRibbon.map((s) => ({ key: s, label: STATUS_LABELS[s] ?? s }));
  }, [statusesInRibbon]);

  const handleLogout = useCallback(async () => {
    if (isLoggingOut) return;
    await logout();
    navigate("/login", { replace: true });
  }, [logout, isLoggingOut, navigate]);

  const openLoadWorkspace = useCallback(
    (load: Load) => {
      setSelectedLoad(load);
    },
    [],
  );

  return (
    <div className="h-full bg-[#080a0f] text-[#e8edf5] flex flex-col overflow-hidden">
      {/* Top header — screenshot-style workspace header */}
      <header className="h-12 border-b border-[#0d121d] bg-[#0a0d12] flex items-center px-5 gap-5 shrink-0">
        <NavLink to={`${slug}${OPS.DASHBOARD}`} className="font-semibold text-[#f5a623] shrink-0 text-sm hover:text-[#e69518]">
          FleetPro
        </NavLink>
        <nav className="flex items-center gap-5 text-sm">
          <span className="text-white font-medium border-b-2 border-[#f5a623] pb-1">Dispatch</span>
          <button
            type="button"
            onClick={() => setMapOpen((m) => !m)}
            className={clsx("text-sm pb-1", mapOpen ? "text-white border-b-2 border-white/60" : "text-[#94a3b8] hover:text-white")}
          >
            Map
          </button>
          <NavLink to={`${slug}${OPS.LOADS}`} className="text-sm text-[#94a3b8] hover:text-white">
            Loads
          </NavLink>
          <span className="text-sm text-[#94a3b8] opacity-80 select-none">Reports</span>
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <input
            type="search"
            placeholder="Search loads, brokers, drivers..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-[380px] rounded-md border border-[#1e293b] bg-[#0d1117] px-3 py-1.5 text-sm text-[#e8edf5] placeholder-[#64748b]"
          />
          <button
            onClick={() => navigate(`${slug}${OPS.LOAD_NEW}`)}
            className="rounded-md bg-[#f5a623] text-[#080a0f] px-3 py-1.5 text-sm font-semibold hover:bg-[#e69518]"
          >
            + New Load
          </button>
          {/* Keep list toggle available but de-emphasized */}
          <button
            onClick={() => setLayoutMode(layoutMode === "board" ? "table" : "board")}
            className="hidden"
          >
            {layoutMode === "board" ? "List view" : "Board view"}
          </button>
          <div className="relative">
            <button
              onClick={() => setUserMenuOpen((o) => !o)}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-[#334155] bg-[#1e293b] text-[#94a3b8] hover:text-[#e8edf5] text-sm font-medium"
              aria-haspopup="true"
              aria-expanded={userMenuOpen}
            >
              {me?.user_id ? String(me.user_id).slice(-2) : "?"}
            </button>
            {userMenuOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setUserMenuOpen(false)} aria-hidden="true" />
                <div className="absolute right-0 top-full mt-1 z-50 w-48 rounded border border-[#1e293b] bg-[#0d1117] py-1 shadow-lg">
                  <NavLink
                    to={`${slug}${OPS.DASHBOARD}`}
                    className="block px-3 py-2 text-xs text-[#94a3b8] hover:bg-[#1e293b] hover:text-[#e8edf5]"
                    onClick={() => setUserMenuOpen(false)}
                  >
                    Profile
                  </NavLink>
                  <NavLink
                    to={`${slug}${ADMIN.COMPANY_PROFILE}`}
                    className="block px-3 py-2 text-xs text-[#94a3b8] hover:bg-[#1e293b] hover:text-[#e8edf5]"
                    onClick={() => setUserMenuOpen(false)}
                  >
                    Settings
                  </NavLink>
                  <button
                    onClick={() => { setUserMenuOpen(false); handleLogout(); }}
                    disabled={isLoggingOut}
                    className="block w-full text-left px-3 py-2 text-xs text-[#94a3b8] hover:bg-[#1e293b] hover:text-[#f87171] disabled:opacity-50"
                  >
                    Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Ribbon tabs — screenshot-like */}
      <div className="flex gap-2 px-5 py-2 border-b border-[#0d121d] bg-[#0a0d12] shrink-0">
        {RIBBON_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setRibbonTab(tab.key)}
            className={clsx(
              "rounded-full px-3 py-1.5 text-xs font-medium transition",
              ribbonTab === tab.key
                ? "bg-[#f5a623] text-[#0a0c12] border border-[#f5a623]"
                : "text-[#94a3b8] hover:bg-[#11151c] hover:text-white border border-transparent"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <main className="flex-1 flex overflow-hidden min-h-0 bg-[#080a0f]">
        {layoutMode === "table" ? (
          <div className="flex-1 overflow-auto p-4">
            <div className="rounded-lg border border-[#1e293b] bg-[#0d1117] overflow-hidden">
              {loading ? (
                <div className="py-12 text-center text-[#64748b] text-sm">Loading...</div>
              ) : (
                <table className="min-w-full">
                  <thead>
                    <tr className="border-b border-[#1e293b]">
                      <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">Load #</th>
                      <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">Trip #</th>
                      <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">Route</th>
                      <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groupedForTable.flatMap((g) =>
                      g.loads.map((load) => (
                        <tr
                          key={load.id}
                          onClick={() => openLoadWorkspace(load)}
                          className="border-b border-[#1e293b]/50 cursor-pointer transition hover:bg-[#1e293b]/30"
                        >
                          <td className="px-4 py-2.5 text-sm font-medium text-[#e8edf5]">#{load.load_number}</td>
                          <td className="px-4 py-2.5 text-sm text-[#94a3b8]">{formatTripNumber(load)}</td>
                          <td className="px-4 py-2.5 text-sm text-[#94a3b8]">{formatRoute(load)}</td>
                          <td className="px-4 py-2.5">
                            <span className={clsx("inline-flex px-2 py-0.5 rounded text-[11px] font-medium border", STATUS_BADGE_CLASS[load.status])}>
                              {STATUS_LABELS[load.status] ?? load.status}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                    {!loading && loadsForView.length === 0 && (
                      <tr>
                        <td colSpan={4} className="px-4 py-12 text-center text-[#64748b] text-sm">
                          {ribbonTab === "active" ? (
                            <span>
                              No loads ·{" "}
                              <button onClick={() => navigate(`${slug}${OPS.LOAD_NEW}`)} className="text-[#f5a623] hover:underline">
                                New Load
                              </button>
                            </span>
                          ) : (
                            "No loads in this queue"
                          )}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        ) : (
          <div className="flex-1 flex gap-4 overflow-x-auto overflow-y-hidden px-5 py-4 min-w-0">
            {loading ? (
              <div className="flex items-center justify-center w-full text-[#64748b] text-sm">Loading...</div>
            ) : (
              boardColumns.map((col) => (
                <StatusColumn
                  key={col.key}
                  statusKey={col.key}
                  label={col.label}
                  loads={board?.[col.key] ?? []}
                  trucks={trucks}
                  drivers={drivers}
                  trailers={trailers}
                  onSelectLoad={openLoadWorkspace}
                  onEmptyAction={col.key === "unassigned" ? () => navigate(`${slug}${OPS.LOAD_NEW}`) : undefined}
                />
              ))
            )}
          </div>
        )}
      </main>

      {/* ── LOAD DETAIL MODAL ── */}
      {selectedLoad && (
        <>
          <button
            type="button"
            aria-label="Close"
            className="fixed inset-0 z-40 bg-black/70"
            onClick={() => setSelectedLoad(null)}
          />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
            <div className="relative w-[96vw] max-w-6xl max-h-[92vh] bg-[#0d1117] rounded-2xl border border-[#1e293b] flex flex-col overflow-hidden shadow-2xl pointer-events-auto">

              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-[#1e293b] bg-[#0a0d14] shrink-0">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-lg font-bold text-white">
                      #{selectedLoad.load_number || "—"}
                    </span>
                    <span className={clsx("text-[11px] font-semibold px-2 py-0.5 rounded border", STATUS_BADGE_CLASS[selectedLoad.status])}>
                      {STATUS_LABELS[selectedLoad.status] ?? selectedLoad.status}
                    </span>
                    {selectedLoad.review_required && (
                      <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-amber-900/30 text-amber-300 border border-amber-700/40">
                        Review Required
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-[#64748b]">
                    {selectedLoad.broker_name_snapshot || "No broker"} · {formatRouteFromStops(selectedLoad.stops)}
                  </p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <button
                    type="button"
                    onClick={() => {
                      const id = selectedLoad.id;
                      setSelectedLoad(null);
                      navigate(`${slug}${OPS.LOAD_DETAIL(id)}`);
                    }}
                    className="text-xs text-[#94a3b8] hover:text-white border border-[#2b3347] rounded-md px-3 py-1.5 transition hover:border-[#475569]"
                  >
                    Edit load
                  </button>
                  <button
                    type="button"
                    aria-label="Close"
                    onClick={() => setSelectedLoad(null)}
                    className="text-[#64748b] hover:text-white text-2xl leading-none px-1"
                  >
                    ×
                  </button>
                </div>
              </div>

              {/* Body — 2 columns */}
              <div className="flex-1 overflow-hidden grid grid-cols-1 md:grid-cols-2 divide-x divide-[#1e293b]">

                {/* LEFT — who is involved, identity, financials */}
                <div className="overflow-y-auto p-5 space-y-6">

                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-[#475569] border-b border-[#1e293b] pb-2 mb-3">Who is involved</p>
                    <div className="space-y-2">
                      <ModalRow label="Broker" value={selectedLoad.broker_name_snapshot || selectedLoad.broker?.name || "—"} />
                      <ModalRow label="Contact" value={selectedLoad.broker_contact_name_snapshot || selectedLoad.broker_contact?.name || "—"} />
                      {selectedLoad.broker_contact_phone_snapshot && (
                        <ModalRow label="Phone" value={selectedLoad.broker_contact_phone_snapshot} />
                      )}
                      {selectedLoad.broker_contact_extension_snapshot && (
                        <ModalRow label="Ext" value={selectedLoad.broker_contact_extension_snapshot} />
                      )}
                      {selectedLoad.broker_contact_email_snapshot && (
                        <ModalRow label="Email" value={selectedLoad.broker_contact_email_snapshot} />
                      )}
                      <ModalRow label="Load ref" value={selectedLoad.broker_load_reference || "—"} />
                    </div>
                    {/* Driver block */}
                    <div className="mt-3 flex items-center gap-3">
                      <div
                        className="h-9 w-9 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0"
                        style={selectedLoad.driver
                          ? { background: "#1e3a5f", color: "#60a5fa" }
                          : { background: "#1c2233", color: "#4b5563" }}
                      >
                        {selectedLoad.driver
                          ? `${selectedLoad.driver.first_name[0] ?? ""}${selectedLoad.driver.last_name[0] ?? ""}`.toUpperCase()
                          : "?"}
                      </div>
                      <div>
                        <p className="text-[10px] text-[#64748b]">Driver</p>
                        <p className="text-xs text-white">
                          {selectedLoad.driver
                            ? `${selectedLoad.driver.first_name} ${selectedLoad.driver.last_name}`
                            : "Unassigned"}
                        </p>
                        {selectedLoad.driver?.phone && (
                          <p className="text-[10px] text-[#94a3b8]">{selectedLoad.driver.phone}</p>
                        )}
                      </div>
                    </div>
                    <div className="mt-2 space-y-2">
                      <ModalRow label="Truck" value={selectedLoad.truck ? selectedLoad.truck.unit_number : "—"} />
                      <ModalRow
                        label="Trailer"
                        value={selectedLoad.trailer
                          ? [selectedLoad.trailer.unit_number, selectedLoad.trailer.trailer_type].filter(Boolean).join(" · ")
                          : "—"}
                      />
                      {selectedLoad.customs_broker && (
                        <ModalRow label="Customs broker" value={selectedLoad.customs_broker.legal_name} />
                      )}
                    </div>
                  </div>

                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-[#475569] border-b border-[#1e293b] pb-2 mb-3">Load identity</p>
                    <div className="space-y-2">
                      <ModalRow label="Trip #" value={selectedLoad.trip_number?.trim() || "—"} mono />
                      <ModalRow label="Mode" value={selectedLoad.mode || "—"} />
                      {selectedLoad.broker_match_method && (
                        <ModalRow label="Match method" value={selectedLoad.broker_match_method.replace(/_/g, " ")} />
                      )}
                      {selectedLoad.broker_match_confidence_tier && (
                        <ModalRow label="Confidence" value={`Tier ${selectedLoad.broker_match_confidence_tier}`} />
                      )}
                      {selectedLoad.created_at && (
                        <ModalRow label="Created" value={new Date(selectedLoad.created_at).toLocaleString()} />
                      )}
                    </div>
                  </div>

                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-[#475569] border-b border-[#1e293b] pb-2 mb-3">Financials</p>
                    <div className="space-y-2">
                      <ModalRow
                        label="Linehaul rate"
                        value={selectedLoad.rate != null
                          ? `$${Number(selectedLoad.rate).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : "—"}
                      />
                      <ModalRow
                        label="Customer rate"
                        value={selectedLoad.customer_rate != null
                          ? `$${Number(selectedLoad.customer_rate).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : "—"}
                      />
                      <ModalRow label="Miles" value={selectedLoad.miles != null ? `${selectedLoad.miles.toLocaleString()} mi` : "—"} />
                    </div>
                  </div>
                </div>

                {/* RIGHT — freight, stops, notes */}
                <div className="overflow-y-auto p-5 space-y-6">

                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-[#475569] border-b border-[#1e293b] pb-2 mb-3">Freight & equipment</p>
                    <div className="space-y-2">
                      <ModalRow label="Equipment" value={selectedLoad.equipment_type || "—"} />
                      <ModalRow label="Trailer type" value={selectedLoad.trailer_type || "—"} />
                      <ModalRow label="Trailer size" value={selectedLoad.trailer_size || "—"} />
                      <ModalRow label="Commodity" value={selectedLoad.commodity || "—"} />
                      <ModalRow
                        label="Est. weight"
                        value={selectedLoad.estimated_weight != null ? `${selectedLoad.estimated_weight.toLocaleString()} lb` : "—"}
                      />
                      <ModalRow
                        label="Hazmat"
                        value={selectedLoad.hazmat_flag === true ? "Yes" : selectedLoad.hazmat_flag === false ? "No" : "—"}
                      />
                      <ModalRow label="Temperature" value={selectedLoad.temperature_requirement || "—"} />
                      <ModalRow label="Pallets / cases" value={selectedLoad.pallet_case_count || "—"} />
                    </div>
                  </div>

                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-[#475569] border-b border-[#1e293b] pb-2 mb-3">
                      Stops ({selectedLoad.stops?.length ?? 0})
                    </p>
                    <div className="space-y-3">
                      {(selectedLoad.stops?.length ? sortedStops(selectedLoad.stops) : []).map((s, i) => (
                        <div key={s.id || i} className="rounded-xl border border-[#1e293b] bg-[#0c101a] p-3">
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-[#64748b] mb-2">
                            {s.stop_type} · Stop {(s.sequence ?? i) + 1}
                          </p>
                          {s.facility_name && (
                            <p className="text-xs font-medium text-white">{s.facility_name}</p>
                          )}
                          {(s.street || s.city) && (
                            <p className="text-xs text-[#94a3b8]">
                              {[s.street, s.city, s.state_or_province, s.postal_code, s.country]
                                .filter(Boolean)
                                .join(", ")}
                            </p>
                          )}
                          {(s.appointment_date || s.appointment_time_text) && (
                            <p className="mt-1 text-xs text-[#64748b]">
                              Appt:{" "}
                              {[s.appointment_date, s.appointment_time_text, s.appointment_type]
                                .filter(Boolean)
                                .join(" · ")}
                            </p>
                          )}
                          {s.reference_number && (
                            <p className="text-[10px] text-[#64748b]">Ref: {s.reference_number}</p>
                          )}
                          {s.notes && (
                            <p className="mt-1 text-[10px] italic text-[#64748b]">{s.notes}</p>
                          )}
                        </div>
                      ))}
                      {!selectedLoad.stops?.length && (
                        <p className="text-xs text-[#64748b] italic">No stops on this load.</p>
                      )}
                    </div>
                  </div>

                  {selectedLoad.internal_notes?.trim() && (
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-widest text-[#475569] border-b border-[#1e293b] pb-2 mb-3">Internal notes</p>
                      <pre className="whitespace-pre-wrap text-xs text-[#94a3b8] font-mono max-h-48 overflow-y-auto rounded-lg border border-[#1e293b] bg-[#0c101a] p-3 leading-relaxed">
                        {selectedLoad.internal_notes.trim()}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ModalRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="text-[11px] text-[#64748b] shrink-0">{label}</span>
      <span className={clsx("text-right break-all", mono ? "font-mono text-[11px] text-[#94a3b8]" : "text-xs text-[#e2e8f0]")}>
        {value}
      </span>
    </div>
  );
}
