/**
 * Dispatch Workspace — Layout C (table default) + Layout B (board optional)
 * Reusable operational workspace pattern: ribbon tabs, table/board views, right detail drawer.
 * 3 exact primary fields in rows/cards: Load #, Route, Status.
 * Delivered moved to ribbon tab, not a board column.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { clsx } from "clsx";
import {
  getDispatchBoard,
  addLoadNote,
  updateLoad,
  createLoad,
  listTrucks,
  listDrivers,
  listTrailers,
  type Load,
  type DispatchBoard,
  type LoadNote,
  type Truck,
  type Driver,
  type Trailer,
} from "@/api";
import { OPS, ADMIN } from "@/routes";
import { getTenantSlugFromHost } from "@/tenant";
import { useWorkspaceLayout } from "@/hooks/useWorkspaceLayout";
import { useMe } from "@/hooks/useMe";
import { useAuth } from "@/contexts/AuthContext";

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

const COLUMN_WIDTH = 220;

function formatLoc(loc: string | null | undefined): string {
  if (!loc) return "—";
  const parts = loc.split(",").map((s) => s.trim());
  return parts.length >= 2 ? `${parts[0]}, ${parts[1]}` : loc;
}

function formatRoute(load: Load): string {
  return `${formatLoc(load.pickup_location)} → ${formatLoc(load.delivery_location)}`;
}

/** Board card — 3 fields only: Load #, Route, Status */
function LoadCard({
  load,
  trucks,
  drivers,
  trailers,
  onSelect,
  onAssign,
  onStatusChange,
  onDispatch,
}: {
  load: Load;
  trucks: Truck[];
  drivers: Driver[];
  trailers: Trailer[];
  onSelect: (load: Load) => void;
  onAssign: (load: Load, field: "truck_id" | "driver_id" | "trailer_id", value: number | null) => void;
  onStatusChange: (load: Load, newStatus: string) => void;
  onDispatch: (load: Load) => void;
}) {
  const [focused, setFocused] = useState(false);
  const canDispatch = load.truck_id != null && load.driver_id != null && ["unassigned", "assigned"].includes(load.status);
  const badgeClass = STATUS_BADGE_CLASS[load.status] ?? STATUS_BADGE_CLASS.unassigned;

  return (
    <div
      className={clsx(
        "rounded border border-[#242840] bg-[#111520] transition-all w-full hover:border-[#2a3050] hover:bg-[#161b27]",
        "focus-within:ring-1 focus-within:ring-[#f5a623]/50"
      )}
      onClick={() => onSelect(load)}
      onMouseEnter={() => setFocused(true)}
      onMouseLeave={() => setFocused(false)}
    >
      <div className="p-2 cursor-pointer">
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold text-[#e8edf5] text-xs">#{load.load_number}</span>
          <span className={clsx("shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium border", badgeClass)}>
            {STATUS_LABELS[load.status] ?? load.status}
          </span>
        </div>
        <p className="mt-1 text-[11px] text-[#94a3b8] truncate">{formatRoute(load)}</p>
      </div>
      <div
        className="flex flex-wrap items-center gap-1 px-2 py-1 border-t border-[#1c2235]"
        onClick={(e) => e.stopPropagation()}
      >
        <select
          className="h-5 max-w-[52px] text-[10px] rounded border border-[#242840] bg-[#0d1017] text-[#94a3b8] px-1"
          value={load.truck_id ?? ""}
          onChange={(e) => onAssign(load, "truck_id", e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">T</option>
          {trucks.map((t) => (
            <option key={t.id} value={t.id}>{t.unit_number}</option>
          ))}
        </select>
        <select
          className="h-5 max-w-[64px] text-[10px] rounded border border-[#242840] bg-[#0d1017] text-[#94a3b8] px-1"
          value={load.driver_id ?? ""}
          onChange={(e) => onAssign(load, "driver_id", e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">D</option>
          {drivers.map((d) => (
            <option key={d.id} value={d.id}>{d.first_name}</option>
          ))}
        </select>
        <select
          className="h-5 max-w-[48px] text-[10px] rounded border border-[#242840] bg-[#0d1017] text-[#94a3b8] px-1"
          value={load.trailer_id ?? ""}
          onChange={(e) => onAssign(load, "trailer_id", e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Tr</option>
          {trailers.map((t) => (
            <option key={t.id} value={t.id}>{t.unit_number}</option>
          ))}
        </select>
        {canDispatch && (
          <button
            onClick={() => onDispatch(load)}
            className="h-5 px-2 rounded text-[10px] font-semibold bg-[#f5a623] text-[#080a0f] hover:bg-[#e69518]"
          >
            Dispatch
          </button>
        )}
        {focused && (
          <select
            className="h-5 max-w-[68px] text-[10px] rounded border border-[#242840] bg-[#0d1017] text-[#94a3b8] px-1"
            value={load.status}
            onChange={(e) => onStatusChange(load, e.target.value)}
          >
            {Object.entries(STATUS_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        )}
      </div>
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
  onAssign,
  onStatusChange,
  onDispatch,
  onEmptyAction,
}: {
  statusKey: string;
  label: string;
  loads: Load[];
  trucks: Truck[];
  drivers: Driver[];
  trailers: Trailer[];
  onSelectLoad: (load: Load) => void;
  onAssign: (load: Load, field: "truck_id" | "driver_id" | "trailer_id", value: number | null) => void;
  onStatusChange: (load: Load, newStatus: string) => void;
  onDispatch: (load: Load) => void;
  onEmptyAction?: () => void;
}) {
  return (
    <div className="flex-shrink-0 flex flex-col rounded-lg border border-[#1c2235] bg-[#111520]" style={{ width: COLUMN_WIDTH }}>
      <div className="px-2.5 py-2 border-b border-[#1c2235] font-semibold text-xs text-[#e8edf5] flex items-center justify-between">
        <span>{label}</span>
        <span className="text-[#64748b] tabular-nums">{loads.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto min-h-[60px] max-h-[calc(100vh-220px)] p-2 space-y-1.5">
        {loads.map((load) => (
          <LoadCard
            key={load.id}
            load={load}
            trucks={trucks}
            drivers={drivers}
            trailers={trailers}
            onSelect={onSelectLoad}
            onAssign={onAssign}
            onStatusChange={onStatusChange}
            onDispatch={onDispatch}
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
  const slug = getTenantSlugFromHost() ? "" : "";
  const navigate = useNavigate();
  const { logout, isLoggingOut } = useAuth();
  const { me } = useMe();
  const [layoutMode, setLayoutMode] = useWorkspaceLayout("dispatch", me?.user_id ?? null, "table");

  const [board, setBoard] = useState<DispatchBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [searchDebounced, setSearchDebounced] = useState("");
  const [ribbonTab, setRibbonTab] = useState<(typeof RIBBON_TABS)[number]["key"]>("active");
  const [selectedLoad, setSelectedLoad] = useState<Load | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);
  const [notes, setNotes] = useState<LoadNote[]>([]);
  const [newNote, setNewNote] = useState("");
  const [lastAction, setLastAction] = useState<{ load: Load; prevStatus: string } | null>(null);
  const [trucks, setTrucks] = useState<Truck[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [trailers, setTrailers] = useState<Trailer[]>([]);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

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

  useEffect(() => {
    if (selectedLoad) {
      getLoadNotes(selectedLoad.id).then(setNotes).catch(() => setNotes([]));
    } else {
      setNotes([]);
    }
  }, [selectedLoad?.id]);

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

  const handleAssign = useCallback(async (load: Load, field: "truck_id" | "driver_id" | "trailer_id", value: number | null) => {
    try {
      await updateLoad(load.id, { [field]: value });
      refreshBoard();
      if (selectedLoad?.id === load.id) setSelectedLoad({ ...selectedLoad, [field]: value } as Load);
    } catch (e) {
      console.error(e);
    }
  }, [refreshBoard, selectedLoad]);

  const handleDispatch = useCallback(async (load: Load) => {
    if (!load.truck_id || !load.driver_id) return;
    const prev = load.status;
    try {
      await updateLoad(load.id, { status: "dispatched" });
      setLastAction({ load, prevStatus: prev });
      setTimeout(() => setLastAction(null), 4000);
      refreshBoard();
      if (selectedLoad?.id === load.id) setSelectedLoad({ ...selectedLoad, status: "dispatched" });
    } catch (e) {
      console.error(e);
    }
  }, [refreshBoard, selectedLoad]);

  const handleStatusChange = useCallback(async (load: Load, newStatus: string) => {
    const prev = load.status;
    try {
      await updateLoad(load.id, { status: newStatus });
      setLastAction({ load, prevStatus: prev });
      setTimeout(() => setLastAction(null), 4000);
      refreshBoard();
      if (selectedLoad?.id === load.id) setSelectedLoad({ ...selectedLoad, status: newStatus });
    } catch (e) {
      console.error(e);
    }
  }, [refreshBoard, selectedLoad]);

  const handleAddNote = useCallback(async () => {
    if (!selectedLoad || !newNote.trim()) return;
    try {
      const note = await addLoadNote(selectedLoad.id, newNote.trim());
      setNotes((n) => [note, ...n]);
      setNewNote("");
    } catch (e) {
      console.error(e);
    }
  }, [selectedLoad, newNote]);

  const handleCreateLoad = useCallback(async () => {
    const loadNumber = `L-${Date.now().toString(36).toUpperCase()}`;
    try {
      const load = await createLoad({ load_number: loadNumber, status: "unassigned" });
      refreshBoard();
      setSelectedLoad(load);
      setDrawerOpen(true);
    } catch (e) {
      console.error(e);
    }
  }, [refreshBoard]);

  const handleUndo = useCallback(() => {
    if (!lastAction) return;
    updateLoad(lastAction.load.id, { status: lastAction.prevStatus }).then(() => {
      setLastAction(null);
      refreshBoard();
    });
  }, [lastAction, refreshBoard]);

  const handleLogout = useCallback(async () => {
    if (isLoggingOut) return;
    await logout();
    navigate("/login", { replace: true });
  }, [logout, isLoggingOut, navigate]);

  const openDrawer = (load: Load) => {
    setSelectedLoad(load);
    setDrawerOpen(true);
    setMapOpen(false);
  };

  return (
    <div className="h-screen bg-[#080a0f] text-[#e8edf5] flex flex-col overflow-hidden">
      {/* Top header — Layout C style */}
      <header className="h-12 border-b border-[#0d121d] bg-[#0a0d12] flex items-center px-4 gap-4 shrink-0">
        <NavLink to={`${slug}${OPS.DASHBOARD}`} className="font-semibold text-[#f5a623] shrink-0 text-sm hover:text-[#e69518]">
          FleetPro
        </NavLink>
        <span className="text-[#64748b] text-sm">Dispatch</span>
        <input
          type="search"
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 max-w-xs rounded border border-[#1e293b] bg-[#0d1117] px-3 py-1.5 text-sm text-[#e8edf5] placeholder-[#64748b]"
        />
        <button
          onClick={() => { setMapOpen(!mapOpen); setDrawerOpen(true); }}
          className={clsx("rounded px-3 py-1.5 text-xs", mapOpen ? "bg-[#1e293b] text-[#f5a623]" : "text-[#94a3b8] hover:text-[#e8edf5]")}
        >
          Map
        </button>
        <button
          onClick={handleCreateLoad}
          className="rounded bg-[#f5a623] text-[#080a0f] px-3 py-1.5 text-sm font-semibold hover:bg-[#e69518]"
        >
          + New Load
        </button>
        <NavLink to={`${slug}${OPS.LOADS}`} className="text-xs text-[#94a3b8] hover:text-[#e8edf5]">
          Loads
        </NavLink>

        {/* Top-right: layout switcher + user menu */}
        <div className="ml-auto flex items-center gap-2">
          <div className="flex rounded border border-[#1e293b] overflow-hidden">
            <button
              onClick={() => setLayoutMode("table")}
              className={clsx(
                "px-3 py-1.5 text-xs font-medium",
                layoutMode === "table" ? "bg-[#1e293b] text-[#f5a623]" : "text-[#94a3b8] hover:text-[#e8edf5]"
              )}
            >
              List
            </button>
            <button
              onClick={() => setLayoutMode("board")}
              className={clsx(
                "px-3 py-1.5 text-xs font-medium",
                layoutMode === "board" ? "bg-[#1e293b] text-[#f5a623]" : "text-[#94a3b8] hover:text-[#e8edf5]"
              )}
            >
              Board
            </button>
          </div>
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

      {/* Ribbon tabs — Delivered is a tab, not a board column */}
      <div className="flex gap-1 px-4 py-2 border-b border-[#0d121d] bg-[#0a0d12] shrink-0">
        {RIBBON_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setRibbonTab(tab.key)}
            className={clsx(
              "rounded px-3 py-1.5 text-xs font-medium transition",
              ribbonTab === tab.key
                ? "bg-[#1e293b] text-[#f5a623] border border-[#334155]"
                : "text-[#64748b] hover:bg-[#11151c] hover:text-[#94a3b8]"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {lastAction && (
        <div className="fixed bottom-3 right-3 z-50 flex items-center gap-2 rounded bg-[#1e293b] border border-[#334155] px-3 py-2 shadow-lg">
          <span className="text-xs text-[#94a3b8]">Updated</span>
          <button onClick={handleUndo} className="text-xs text-[#f5a623] hover:underline">Undo</button>
        </div>
      )}

      <main className="flex-1 flex overflow-hidden min-h-0">
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
                      <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">Route</th>
                      <th className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-[#64748b]">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groupedForTable.flatMap((g) =>
                      g.loads.map((load) => (
                        <tr
                          key={load.id}
                          onClick={() => openDrawer(load)}
                          className={clsx(
                            "border-b border-[#1e293b]/50 cursor-pointer transition",
                            selectedLoad?.id === load.id ? "bg-[#1e293b]/60" : "hover:bg-[#1e293b]/30"
                          )}
                        >
                          <td className="px-4 py-2.5 text-sm font-medium text-[#e8edf5]">#{load.load_number}</td>
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
                        <td colSpan={3} className="px-4 py-12 text-center text-[#64748b] text-sm">
                          {ribbonTab === "active" ? (
                            <span>No loads · <button onClick={handleCreateLoad} className="text-[#f5a623] hover:underline">New Load</button></span>
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
          <div className="flex-1 flex gap-2 overflow-x-auto overflow-y-hidden p-4 min-w-0">
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
                  onSelectLoad={openDrawer}
                  onAssign={handleAssign}
                  onStatusChange={handleStatusChange}
                  onDispatch={handleDispatch}
                  onEmptyAction={col.key === "unassigned" ? handleCreateLoad : undefined}
                />
              ))
            )}
          </div>
        )}

        {drawerOpen && (
          <aside className="w-[340px] shrink-0 border-l border-[#1e293b] bg-[#0d1117] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#1e293b] shrink-0">
              <span className="font-semibold text-sm">{mapOpen ? "Map" : "Load detail"}</span>
              <button onClick={() => setDrawerOpen(false)} className="text-[#64748b] hover:text-[#e8edf5] text-sm">✕</button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {mapOpen ? (
                <div className="h-48 rounded border border-[#1e293b] flex items-center justify-center text-[#64748b] text-sm">
                  Map (on-demand)
                </div>
              ) : selectedLoad ? (
                <div className="space-y-4">
                  <div>
                    <h3 className="font-semibold text-[#e8edf5]">#{selectedLoad.load_number}</h3>
                    <p className="text-xs text-[#94a3b8] mt-0.5">{formatRoute(selectedLoad)}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                      <span className={clsx("px-2 py-0.5 rounded border", STATUS_BADGE_CLASS[selectedLoad.status])}>
                        {STATUS_LABELS[selectedLoad.status]}
                      </span>
                      {selectedLoad.truck && <span className="text-[#94a3b8]">Truck {selectedLoad.truck.unit_number}</span>}
                      {selectedLoad.driver && <span className="text-[#94a3b8]">{selectedLoad.driver.first_name} {selectedLoad.driver.last_name}</span>}
                      {selectedLoad.trailer && <span className="text-[#94a3b8]">Trail {selectedLoad.trailer.unit_number}</span>}
                    </div>
                  </div>
                  <div>
                    <h4 className="text-xs font-medium text-[#64748b] mb-2">Notes</h4>
                    <div className="space-y-1.5 max-h-28 overflow-y-auto">
                      {notes.map((n) => (
                        <div key={n.id} className="text-xs p-2.5 rounded bg-[#0f1419] border border-[#1e293b]">
                          {n.body}
                          <div className="text-[10px] text-[#64748b] mt-0.5">{new Date(n.created_at).toLocaleString()}</div>
                        </div>
                      ))}
                      {notes.length === 0 && <p className="text-[#64748b] text-xs">No notes</p>}
                    </div>
                    <div className="flex gap-2 mt-2">
                      <input
                        value={newNote}
                        onChange={(e) => setNewNote(e.target.value)}
                        placeholder="Add note..."
                        className="flex-1 rounded border border-[#334155] bg-[#080a0f] px-2.5 py-1.5 text-xs text-[#e8edf5] placeholder-[#64748b]"
                        onKeyDown={(e) => e.key === "Enter" && handleAddNote()}
                      />
                      <button onClick={handleAddNote} className="rounded bg-[#f5a623] text-[#080a0f] px-2.5 py-1.5 text-xs font-medium">
                        Add
                      </button>
                    </div>
                  </div>
                  <NavLink to={`${slug}${OPS.LOAD_DETAIL(selectedLoad.id)}`} className="block text-xs font-medium text-[#f5a623] hover:underline">
                    Full detail →
                  </NavLink>
                </div>
              ) : (
                <p className="text-[#64748b] text-sm">Select a load</p>
              )}
            </div>
          </aside>
        )}
      </main>
    </div>
  );
}
