/**
 * Fleet — trucks and trailers asset management.
 * List all assets, add new ones, view assignment history (loads each asset was assigned to).
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { clsx } from "clsx";
import {
  listTrucks,
  listTrailers,
  createTruck,
  createTrailer,
  updateTruck,
  updateTrailer,
  listLoads,
  type Truck,
  type Trailer,
  type Load,
} from "@/api";
import { firstPickupAppointmentDate, formatRouteFromStops } from "@/utils/loadStops";
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

const TRAILER_TYPES = ["dry_van", "reefer", "flatbed", "step_deck", "lowboy", "tanker", "dump", "chassis", "other"] as const;
const TRAILER_TYPE_OPTIONS = TRAILER_TYPES.map((t) => ({ value: t, label: t.replace(/_/g, " ") }));
const DOOR_OPTIONS = [
  { value: "swing", label: "Swing" },
  { value: "roll", label: "Roll" },
  { value: "curtain", label: "Curtain" },
] as const;
const TRAILER_STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "retired", label: "Retired" },
] as const;

const FORM_INPUT_CLS =
  "w-full rounded border border-[var(--trk-border-strong)] bg-[var(--trk-bg)] px-2.5 py-1.5 text-sm text-[var(--trk-text)] focus:border-[var(--trk-heading)] focus:ring-0 focus:outline-none";
const FORM_LABEL_CLS = "block text-xs font-medium text-[var(--trk-text-muted)] mb-1";

function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset>
      <legend className="text-sm font-semibold text-[var(--trk-text)] mb-3">{title}</legend>
      <div className="grid grid-cols-2 gap-3">{children}</div>
    </fieldset>
  );
}

function FormField({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="col-span-2 sm:col-span-1">
      <label className={FORM_LABEL_CLS}>
        {label} {required && <span className="text-[var(--trk-heading)]">*</span>}
      </label>
      {children}
    </div>
  );
}

type Tab = "trucks" | "trailers";

function formatDate(d: string | null | undefined): string {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return String(d);
  }
}

function formatDateTime(d: string | null | undefined): string {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return String(d);
  }
}

/** Load history row for an asset */
function LoadHistoryRow({ load, onNavigate }: { load: Load; onNavigate: (id: number) => void }) {
  return (
    <tr
      className="border-t border-[var(--trk-border)] hover:bg-[var(--trk-bg)]/50 cursor-pointer"
      onClick={() => onNavigate(load.id)}
    >
      <td className="px-4 py-2 text-xs font-medium text-[var(--trk-heading)]">
        #{load.load_number}
      </td>
      <td className="px-4 py-2 text-xs text-[var(--trk-text-muted)]">{load.trip_number?.trim() || "—"}</td>
      <td className="px-4 py-2 text-xs text-[var(--trk-text-muted)]">
        {formatRouteFromStops(load.stops)}
      </td>
      <td className="px-4 py-2 text-xs text-[var(--trk-text-muted)]">
        {formatDate(firstPickupAppointmentDate(load.stops))}
      </td>
      <td className="px-4 py-2 text-xs">
        <span className="px-2 py-0.5 rounded bg-[var(--trk-surface-2)] text-[var(--trk-text-muted)] text-[10px]">
          {STATUS_LABELS[load.status ?? ""] ?? load.status ?? "—"}
        </span>
      </td>
      <td className="px-4 py-2 text-xs text-[var(--trk-text-muted)]">
        {load.truck ? `Truck ${load.truck.unit_number}` : "—"}
      </td>
      <td className="px-4 py-2 text-xs text-[var(--trk-text-muted)]">
        {load.trailer ? `Trailer ${load.trailer.unit_number}` : "—"}
      </td>
      <td className="px-4 py-2 text-xs text-[var(--trk-text-muted)]">
        {formatDateTime(load.updated_at)}
      </td>
    </tr>
  );
}

/** Asset row with expandable load history */
function AssetRow({
  asset,
  isTruck,
  loadHistory,
  loadHistoryLoading,
  expanded,
  onToggle,
  onEdit,
  onLoadHistory,
}: {
  asset: Truck | Trailer;
  isTruck: boolean;
  loadHistory: Load[];
  loadHistoryLoading: boolean;
  expanded: boolean;
  onToggle: () => void;
  onEdit: () => void;
}) {
  const nav = useNavigate();

  return (
    <>
      <tr
        className={clsx(
          "border-t border-[var(--trk-border)] transition-colors",
          expanded && "bg-[var(--trk-bg)]/30"
        )}
      >
        <td className="px-4 py-2">
          <button
            type="button"
            onClick={onToggle}
            className="text-[var(--trk-text-muted)] hover:text-[var(--trk-text)] text-sm font-mono"
            aria-expanded={expanded}
          >
            {expanded ? "▼" : "▶"}
          </button>
        </td>
        <td className="px-4 py-2 text-sm font-semibold text-[var(--trk-text)]">
          {asset.unit_number}
        </td>
        <td className="px-4 py-2 text-sm text-[var(--trk-text-muted)]">
          {"vin" in asset ? (asset.vin ?? "—") : "—"}
        </td>
        <td className="px-4 py-2 text-sm text-[var(--trk-text-muted)]">
          {asset.make && asset.model ? `${asset.make} ${asset.model}` : asset.make ?? asset.model ?? "—"}
        </td>
        <td className="px-4 py-2 text-sm text-[var(--trk-text-muted)]">
          {"trailer_type" in asset ? (asset.trailer_type ?? "—") : "—"}
        </td>
        <td className="px-4 py-2 text-sm text-[var(--trk-text-muted)]">
          {asset.plate_number ?? "—"}
        </td>
        <td className="px-4 py-2 text-sm">
          <span
            className={clsx(
              "px-2 py-0.5 rounded text-xs",
              asset.status === "active"
                ? "bg-emerald-500/20 text-emerald-300"
                : asset.status === "inactive"
                  ? "bg-[var(--trk-surface-2)] text-[var(--trk-text-muted)]"
                  : "bg-amber-500/20 text-amber-300"
            )}
          >
            {asset.status ?? "active"}
          </span>
        </td>
        <td className="px-4 py-2 text-sm">
          <button
            type="button"
            onClick={onEdit}
            className="text-[var(--trk-heading)] hover:underline text-xs font-medium"
          >
            Edit
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="border-t border-[var(--trk-border)] bg-[var(--trk-bg)]">
          <td colSpan={8} className="px-4 py-3">
            <div className="rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] overflow-hidden">
              <div className="px-4 py-2 border-b border-[var(--trk-border)] text-xs font-semibold text-[var(--trk-text-muted)]">
                Assignment history — loads this {isTruck ? "truck" : "trailer"} was assigned to
              </div>
              {loadHistoryLoading ? (
                <div className="px-4 py-6 text-center text-[var(--trk-text-muted)] text-sm">
                  Loading…
                </div>
              ) : loadHistory.length === 0 ? (
                <div className="px-4 py-6 text-center text-[var(--trk-text-muted)] text-sm">
                  No loads assigned yet. Assign from Dispatch.
                </div>
              ) : (
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--trk-border)]">
                      <th className="px-4 py-2 text-left text-[var(--trk-text-muted)] font-medium">Load #</th>
                      <th className="px-4 py-2 text-left text-[var(--trk-text-muted)] font-medium">Trip #</th>
                      <th className="px-4 py-2 text-left text-[var(--trk-text-muted)] font-medium">Route (stops)</th>
                      <th className="px-4 py-2 text-left text-[var(--trk-text-muted)] font-medium">1st pickup date</th>
                      <th className="px-4 py-2 text-left text-[var(--trk-text-muted)] font-medium">Status</th>
                      <th className="px-4 py-2 text-left text-[var(--trk-text-muted)] font-medium">Truck</th>
                      <th className="px-4 py-2 text-left text-[var(--trk-text-muted)] font-medium">Trailer</th>
                      <th className="px-4 py-2 text-left text-[var(--trk-text-muted)] font-medium">Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loadHistory.map((load) => (
                      <LoadHistoryRow
                        key={load.id}
                        load={load}
                        onNavigate={(id) => nav(`/loads/${id}`)}
                      />
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function FleetPage() {
  const [tab, setTab] = useState<Tab>("trucks");
  const [trucks, setTrucks] = useState<Truck[]>([]);
  const [trailers, setTrailers] = useState<Trailer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showAddTruck, setShowAddTruck] = useState(false);
  const [showAddTrailer, setShowAddTrailer] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [editTruck, setEditTruck] = useState<Truck | null>(null);
  const [editTrailer, setEditTrailer] = useState<Trailer | null>(null);

  const [loadHistory, setLoadHistory] = useState<Load[]>([]);
  const [loadHistoryLoading, setLoadHistoryLoading] = useState(false);

  const [addError, setAddError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadFleet = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      listTrucks({ page: 1, size: 200 }).then((r) => r.items ?? []),
      listTrailers({ page: 1, size: 200 }).then((r) => r.items ?? []),
    ])
      .then(([t, tr]) => {
        setTrucks(t);
        setTrailers(tr);
      })
      .catch((e) => setError(e?.message ?? "Failed to load fleet"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadFleet();
  }, [loadFleet]);

  useEffect(() => {
    if (expandedId == null) {
      setLoadHistory([]);
      return;
    }
    setLoadHistoryLoading(true);
    const param = tab === "trucks" ? { truck_id: expandedId } : { trailer_id: expandedId };
    listLoads({ ...param, page: 1, size: 100 })
      .then((r) => setLoadHistory(r.items ?? []))
      .catch(() => setLoadHistory([]))
      .finally(() => setLoadHistoryLoading(false));
  }, [expandedId, tab]);

  const handleToggleExpand = (id: number) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--trk-text)]">Fleet</h1>
          <p className="text-sm text-[var(--trk-text-muted)]">
            Trucks and trailers — add assets, view assignment history.
          </p>
        </div>
      </div>

      <div className="flex gap-2 border-b border-[var(--trk-border)]">
        <button
          type="button"
          onClick={() => setTab("trucks")}
          className={clsx(
            "px-4 py-2 text-sm font-medium rounded-t border-b-2 -mb-px transition-colors",
            tab === "trucks"
              ? "border-[var(--trk-heading)] text-[var(--trk-heading)]"
              : "border-transparent text-[var(--trk-text-muted)] hover:text-[var(--trk-text-muted)]"
          )}
        >
          Trucks ({trucks.length})
        </button>
        <button
          type="button"
          onClick={() => setTab("trailers")}
          className={clsx(
            "px-4 py-2 text-sm font-medium rounded-t border-b-2 -mb-px transition-colors",
            tab === "trailers"
              ? "border-[var(--trk-heading)] text-[var(--trk-heading)]"
              : "border-transparent text-[var(--trk-text-muted)] hover:text-[var(--trk-text-muted)]"
          )}
        >
          Trailers ({trailers.length})
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-950/20 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {tab === "trucks" && (
        <div className="rounded-lg border border-[var(--trk-border)] bg-[var(--trk-bg)] overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--trk-border)]">
            <span className="text-sm font-semibold text-[var(--trk-text)]">Trucks</span>
            <button
              type="button"
              onClick={() => {
                setShowAddTruck(true);
                setShowAddTrailer(false);
                setEditTruck(null);
                setEditTrailer(null);
                setAddError(null);
              }}
              className="px-3 py-1.5 rounded bg-[var(--trk-heading)] text-[var(--trk-bg)] text-sm font-medium hover:bg-[var(--trk-heading)]"
            >
              + Add Truck
            </button>
          </div>

          <div className="overflow-x-auto">
            {loading ? (
              <div className="px-4 py-12 text-center text-[var(--trk-text-muted)] text-sm">
                Loading trucks…
              </div>
            ) : trucks.length === 0 && !showAddTruck ? (
              <div className="px-4 py-12 text-center text-[var(--trk-text-muted)] text-sm">
                No trucks yet. Click &quot;+ Add Truck&quot; to add one.
              </div>
            ) : trucks.length === 0 ? (
              /* Form open, no trucks — show minimal placeholder so table area isn't empty during overlay */
              <div className="px-4 py-8 text-center text-[var(--trk-text-muted)] text-sm" aria-hidden="true">
                &nbsp;
              </div>
            ) : (
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-[var(--trk-border)]">
                    <th className="w-8 px-4 py-2" />
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">Unit #</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">VIN</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">Make / Model</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">Type</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">Plate</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">Status</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {trucks.map((t) => (
                    <AssetRow
                      key={t.id}
                      asset={t}
                      isTruck
                      loadHistory={expandedId === t.id ? loadHistory : []}
                      loadHistoryLoading={expandedId === t.id && loadHistoryLoading}
                      expanded={expandedId === t.id}
                      onToggle={() => handleToggleExpand(t.id)}
                      onEdit={() => {
                        setEditTruck(t);
                        setEditTrailer(null);
                        setAddError(null);
                        setExpandedId(null);
                      }}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {tab === "trailers" && (
        <div className="rounded-lg border border-[var(--trk-border)] bg-[var(--trk-bg)] overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--trk-border)]">
            <span className="text-sm font-semibold text-[var(--trk-text)]">Trailers</span>
            <button
              type="button"
              onClick={() => {
                setShowAddTrailer(true);
                setShowAddTruck(false);
                setEditTruck(null);
                setEditTrailer(null);
                setAddError(null);
              }}
              className="px-3 py-1.5 rounded bg-[var(--trk-heading)] text-[var(--trk-bg)] text-sm font-medium hover:bg-[var(--trk-heading)]"
            >
              + Add Trailer
            </button>
          </div>

          <div className="overflow-x-auto">
            {loading ? (
              <div className="px-4 py-12 text-center text-[var(--trk-text-muted)] text-sm">
                Loading trailers…
              </div>
            ) : trailers.length === 0 && !showAddTrailer ? (
              <div className="px-4 py-12 text-center text-[var(--trk-text-muted)] text-sm">
                No trailers yet. Click &quot;+ Add Trailer&quot; to add one.
              </div>
            ) : trailers.length === 0 ? (
              <div className="px-4 py-8 text-center text-[var(--trk-text-muted)] text-sm" aria-hidden="true">
                &nbsp;
              </div>
            ) : (
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-[var(--trk-border)]">
                    <th className="w-8 px-4 py-2" />
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">Unit #</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">VIN</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">Make / Model</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">Type</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">Plate</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">Status</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-[var(--trk-text-muted)]">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {trailers.map((tr) => (
                    <AssetRow
                      key={tr.id}
                      asset={tr}
                      isTruck={false}
                      loadHistory={expandedId === tr.id ? loadHistory : []}
                      loadHistoryLoading={expandedId === tr.id && loadHistoryLoading}
                      expanded={expandedId === tr.id}
                      onToggle={() => handleToggleExpand(tr.id)}
                      onEdit={() => {
                        setEditTrailer(tr);
                        setEditTruck(null);
                        setAddError(null);
                        setExpandedId(null);
                      }}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {showAddTruck && (
        <AddTruckForm
          onSuccess={() => {
            setShowAddTruck(false);
            setAddError(null);
            loadFleet();
          }}
          onCancel={() => {
            setShowAddTruck(false);
            setAddError(null);
          }}
          onError={setAddError}
          error={addError}
          saving={saving}
          setSaving={setSaving}
        />
      )}
      {editTruck && (
        <EditTruckForm
          truck={editTruck}
          onSuccess={() => {
            setEditTruck(null);
            loadFleet();
          }}
          onCancel={() => setEditTruck(null)}
          onError={setAddError}
          error={addError}
          saving={saving}
          setSaving={setSaving}
        />
      )}
      {showAddTrailer && (
        <AddTrailerForm
          onSuccess={() => {
            setShowAddTrailer(false);
            setAddError(null);
            loadFleet();
          }}
          onCancel={() => {
            setShowAddTrailer(false);
            setAddError(null);
          }}
          onError={setAddError}
          error={addError}
          saving={saving}
          setSaving={setSaving}
        />
      )}
      {editTrailer && (
        <EditTrailerForm
          trailer={editTrailer}
          onSuccess={() => {
            setEditTrailer(null);
            loadFleet();
          }}
          onCancel={() => setEditTrailer(null)}
          onError={setAddError}
          error={addError}
          saving={saving}
          setSaving={setSaving}
        />
      )}
    </div>
  );
}

const OWNERSHIP_OPTIONS = [
  { value: "company", label: "Company" },
  { value: "owner_operator", label: "Owner Operator" },
  { value: "leased", label: "Leased" },
] as const;

const FUEL_OPTIONS = [
  { value: "diesel", label: "Diesel" },
  { value: "gas", label: "Gas" },
  { value: "cng", label: "CNG" },
  { value: "electric", label: "Electric" },
] as const;

const TRANSMISSION_OPTIONS = [
  { value: "manual", label: "Manual" },
  { value: "automatic", label: "Automatic" },
  { value: "automated_manual", label: "Automated Manual" },
] as const;

const TRUCK_STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "in_shop", label: "In Shop" },
  { value: "retired", label: "Retired" },
] as const;

/** Add truck form — full asset creation per fleet inventory spec */
function AddTruckForm({
  onSuccess,
  onCancel,
  onError,
  error,
  saving,
  setSaving,
}: {
  onSuccess: () => void;
  onCancel: () => void;
  onError: (s: string | null) => void;
  error: string | null;
  saving: boolean;
  setSaving: (v: boolean) => void;
}) {
  const [unitNumber, setUnitNumber] = useState("");
  const [vin, setVin] = useState("");
  const [year, setYear] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [color, setColor] = useState("");

  const [plateNumber, setPlateNumber] = useState("");
  const [plateRegion, setPlateRegion] = useState("");
  const [ownershipType, setOwnershipType] = useState("company");
  const [purchaseDate, setPurchaseDate] = useState("");
  const [purchasePrice, setPurchasePrice] = useState("");

  const [engineMake, setEngineMake] = useState("");
  const [engineModel, setEngineModel] = useState("");
  const [engineSerial, setEngineSerial] = useState("");
  const [horsepower, setHorsepower] = useState("");
  const [fuelType, setFuelType] = useState("");
  const [transmission, setTransmission] = useState("");
  const [numAxles, setNumAxles] = useState("");
  const [gvwrLbs, setGvwrLbs] = useState("");

  const [odometerAtPurchase, setOdometerAtPurchase] = useState("");
  const [currentOdometer, setCurrentOdometer] = useState("");
  const [odometerLastUpdated, setOdometerLastUpdated] = useState("");

  const [insuranceCarrier, setInsuranceCarrier] = useState("");
  const [insurancePolicyNumber, setInsurancePolicyNumber] = useState("");
  const [insuranceExpiry, setInsuranceExpiry] = useState("");

  const [status, setStatus] = useState("active");
  const [notes, setNotes] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    onError(null);
    if (!unitNumber.trim() || !vin.trim()) {
      onError("Unit number and VIN are required");
      return;
    }
    setSaving(true);
    try {
      const payload: Parameters<typeof createTruck>[0] = {
        unit_number: unitNumber.trim(),
        vin: vin.trim().toUpperCase(),
        year: year ? parseInt(year, 10) : undefined,
        make: make.trim() || undefined,
        model: model.trim() || undefined,
        color: color.trim() || undefined,
        plate_number: plateNumber.trim() || undefined,
        plate_region: plateRegion.trim() || undefined,
        ownership_type: ownershipType,
        purchase_date: purchaseDate || undefined,
        purchase_price: purchasePrice ? parseFloat(purchasePrice) : undefined,
        engine_make: engineMake.trim() || undefined,
        engine_model: engineModel.trim() || undefined,
        engine_serial: engineSerial.trim() || undefined,
        horsepower: horsepower ? parseInt(horsepower, 10) : undefined,
        fuel_type: fuelType || undefined,
        transmission: transmission || undefined,
        num_axles: numAxles ? parseInt(numAxles, 10) : undefined,
        gvwr_lbs: gvwrLbs ? parseInt(gvwrLbs, 10) : undefined,
        odometer_at_purchase: odometerAtPurchase ? parseInt(odometerAtPurchase, 10) : undefined,
        current_odometer: currentOdometer ? parseInt(currentOdometer, 10) : undefined,
        odometer_last_updated: odometerLastUpdated
          ? (odometerLastUpdated.length === 16 ? `${odometerLastUpdated}:00` : odometerLastUpdated)
          : undefined,
        insurance_carrier: insuranceCarrier.trim() || undefined,
        insurance_policy_number: insurancePolicyNumber.trim() || undefined,
        insurance_expiry: insuranceExpiry || undefined,
        status,
        notes: notes.trim() || undefined,
      };
      await createTruck(payload);
      onSuccess();
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "Failed to add truck");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      <div
        className="absolute inset-0 z-0 bg-black/50"
        role="button"
        tabIndex={0}
        onClick={onCancel}
        onKeyDown={(e) => e.key === "Escape" && onCancel()}
        aria-label="Close"
      />
      <div
        className="relative z-10 ml-auto w-full max-w-xl bg-[var(--trk-bg)] border-l border-[var(--trk-border)] shadow-xl flex flex-col h-full overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--trk-border)] shrink-0">
          <h2 className="text-lg font-semibold text-[var(--trk-text)]">Add Truck Asset</h2>
          <button
            type="button"
            onClick={onCancel}
            className="p-2 text-[var(--trk-text-muted)] hover:text-[var(--trk-text)] rounded hover:bg-[var(--trk-border)]"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <form
          onSubmit={handleSubmit}
          className="flex flex-col min-h-0 overflow-y-auto"
        >
          <div className="flex-1 px-6 py-5 space-y-6">
            <FormSection title="Basic Info">
              <FormField label="Unit #" required>
                <input
                  value={unitNumber}
                  onChange={(e) => setUnitNumber(e.target.value)}
                  className={FORM_INPUT_CLS}
                  placeholder="101"
                  required
                />
              </FormField>
              <FormField label="VIN" required>
                <input
                  value={vin}
                  onChange={(e) => setVin(e.target.value.toUpperCase())}
                  className={FORM_INPUT_CLS}
                  placeholder="1HGBH41JXMN109186"
                  required
                />
              </FormField>
              <FormField label="Year">
                <input
                  type="number"
                  min={1900}
                  max={2100}
                  value={year}
                  onChange={(e) => setYear(e.target.value)}
                  className={FORM_INPUT_CLS}
                  placeholder="2024"
                />
              </FormField>
              <FormField label="Make">
                <input value={make} onChange={(e) => setMake(e.target.value)} className={FORM_INPUT_CLS} placeholder="Freightliner" />
              </FormField>
              <FormField label="Model">
                <input value={model} onChange={(e) => setModel(e.target.value)} className={FORM_INPUT_CLS} placeholder="Cascadia" />
              </FormField>
              <FormField label="Color">
                <input value={color} onChange={(e) => setColor(e.target.value)} className={FORM_INPUT_CLS} placeholder="White" />
              </FormField>
            </FormSection>

            <FormSection title="Registration & Ownership">
              <FormField label="Plate #">
                <input value={plateNumber} onChange={(e) => setPlateNumber(e.target.value)} className={FORM_INPUT_CLS} placeholder="ABC 1234" />
              </FormField>
              <FormField label="Plate Region">
                <input value={plateRegion} onChange={(e) => setPlateRegion(e.target.value)} className={FORM_INPUT_CLS} placeholder="CA" />
              </FormField>
              <FormField label="Ownership">
                <select value={ownershipType} onChange={(e) => setOwnershipType(e.target.value)} className={FORM_INPUT_CLS}>
                  {OWNERSHIP_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="Purchase Date">
                <input
                  type="date"
                  value={purchaseDate}
                  onChange={(e) => setPurchaseDate(e.target.value)}
                  className={FORM_INPUT_CLS}
                />
              </FormField>
              <FormField label="Purchase Price ($)">
                <input
                  type="number"
                  min={0}
                  step={0.01}
                  value={purchasePrice}
                  onChange={(e) => setPurchasePrice(e.target.value)}
                  className={FORM_INPUT_CLS}
                  placeholder="85000"
                />
              </FormField>
            </FormSection>

            <FormSection title="Powertrain & Specs">
              <FormField label="Engine Make">
                <input value={engineMake} onChange={(e) => setEngineMake(e.target.value)} className={FORM_INPUT_CLS} placeholder="Detroit" />
              </FormField>
              <FormField label="Engine Model">
                <input value={engineModel} onChange={(e) => setEngineModel(e.target.value)} className={FORM_INPUT_CLS} placeholder="DD15" />
              </FormField>
              <FormField label="Engine Serial">
                <input value={engineSerial} onChange={(e) => setEngineSerial(e.target.value)} className={FORM_INPUT_CLS} placeholder="ABC123" />
              </FormField>
              <FormField label="Horsepower">
                <input
                  type="number"
                  min={1}
                  value={horsepower}
                  onChange={(e) => setHorsepower(e.target.value)}
                  className={FORM_INPUT_CLS}
                  placeholder="450"
                />
              </FormField>
              <FormField label="Fuel Type">
                <select value={fuelType} onChange={(e) => setFuelType(e.target.value)} className={FORM_INPUT_CLS}>
                  <option value="">—</option>
                  {FUEL_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="Transmission">
                <select value={transmission} onChange={(e) => setTransmission(e.target.value)} className={FORM_INPUT_CLS}>
                  <option value="">—</option>
                  {TRANSMISSION_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="Num Axles">
                <input
                  type="number"
                  min={1}
                  value={numAxles}
                  onChange={(e) => setNumAxles(e.target.value)}
                  className={FORM_INPUT_CLS}
                  placeholder="3"
                />
              </FormField>
              <FormField label="GVWR (lbs)">
                <input
                  type="number"
                  min={1}
                  value={gvwrLbs}
                  onChange={(e) => setGvwrLbs(e.target.value)}
                  className={FORM_INPUT_CLS}
                  placeholder="80000"
                />
              </FormField>
            </FormSection>

            <FormSection title="Odometer">
              <FormField label="Odometer at Purchase">
                <input
                  type="number"
                  min={0}
                  value={odometerAtPurchase}
                  onChange={(e) => setOdometerAtPurchase(e.target.value)}
                  className={FORM_INPUT_CLS}
                  placeholder="0"
                />
              </FormField>
              <FormField label="Current Odometer">
                <input
                  type="number"
                  min={0}
                  value={currentOdometer}
                  onChange={(e) => setCurrentOdometer(e.target.value)}
                  className={FORM_INPUT_CLS}
                  placeholder="125000"
                />
              </FormField>
              <FormField label="Odometer Last Updated">
                <input
                  type="datetime-local"
                  value={odometerLastUpdated}
                  onChange={(e) => setOdometerLastUpdated(e.target.value)}
                  className={FORM_INPUT_CLS}
                />
              </FormField>
            </FormSection>

            <FormSection title="Insurance">
              <FormField label="Insurance Carrier">
                <input value={insuranceCarrier} onChange={(e) => setInsuranceCarrier(e.target.value)} className={FORM_INPUT_CLS} placeholder="Progressive" />
              </FormField>
              <FormField label="Policy #">
                <input value={insurancePolicyNumber} onChange={(e) => setInsurancePolicyNumber(e.target.value)} className={FORM_INPUT_CLS} placeholder="POL-12345" />
              </FormField>
              <FormField label="Expiry">
                <input
                  type="date"
                  value={insuranceExpiry}
                  onChange={(e) => setInsuranceExpiry(e.target.value)}
                  className={FORM_INPUT_CLS}
                />
              </FormField>
            </FormSection>

            <FormSection title="Status & Notes">
              <FormField label="Status">
                <select value={status} onChange={(e) => setStatus(e.target.value)} className={FORM_INPUT_CLS}>
                  {TRUCK_STATUS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FormField>
              <div className="col-span-2">
                <label className={FORM_LABEL_CLS}>Notes</label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className={`${FORM_INPUT_CLS} min-h-[80px] resize-y`}
                  placeholder="Additional notes…"
                  rows={3}
                />
              </div>
            </FormSection>
          </div>

          {error && <div className="px-6 py-2 text-sm text-red-400">{error}</div>}
          <div className="flex gap-3 px-6 py-4 border-t border-[var(--trk-border)] shrink-0 bg-[var(--trk-bg)]">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded bg-[var(--trk-heading)] text-[var(--trk-bg)] text-sm font-medium hover:bg-[var(--trk-heading)] disabled:opacity-50"
            >
              {saving ? "Adding…" : "Add Truck"}
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 rounded border border-[var(--trk-border-strong)] text-[var(--trk-text-muted)] text-sm hover:bg-[var(--trk-border)]"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** Add trailer form — full asset creation per fleet inventory spec */
function AddTrailerForm({
  onSuccess,
  onCancel,
  onError,
  error,
  saving,
  setSaving,
}: {
  onSuccess: () => void;
  onCancel: () => void;
  onError: (s: string | null) => void;
  error: string | null;
  saving: boolean;
  setSaving: (v: boolean) => void;
}) {
  const [unitNumber, setUnitNumber] = useState("");
  const [vin, setVin] = useState("");
  const [year, setYear] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");

  const [plateNumber, setPlateNumber] = useState("");
  const [plateRegion, setPlateRegion] = useState("");
  const [ownershipType, setOwnershipType] = useState("company");
  const [purchaseDate, setPurchaseDate] = useState("");
  const [purchasePrice, setPurchasePrice] = useState("");

  const [trailerType, setTrailerType] = useState("dry_van");
  const [lengthFt, setLengthFt] = useState("");
  const [numAxles, setNumAxles] = useState("");
  const [gvwrLbs, setGvwrLbs] = useState("");
  const [doorType, setDoorType] = useState("");

  const [reeferMake, setReeferMake] = useState("");
  const [reeferModel, setReeferModel] = useState("");
  const [reeferSerial, setReeferSerial] = useState("");

  const [insuranceCarrier, setInsuranceCarrier] = useState("");
  const [insurancePolicyNumber, setInsurancePolicyNumber] = useState("");
  const [insuranceExpiry, setInsuranceExpiry] = useState("");

  const [status, setStatus] = useState("active");
  const [notes, setNotes] = useState("");

  const isReefer = trailerType === "reefer";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    onError(null);
    if (!unitNumber.trim()) {
      onError("Unit number is required");
      return;
    }
    setSaving(true);
    try {
      const payload: Parameters<typeof createTrailer>[0] = {
        unit_number: unitNumber.trim(),
        vin: vin.trim() || undefined,
        year: year ? parseInt(year, 10) : undefined,
        make: make.trim() || undefined,
        model: model.trim() || undefined,
        plate_number: plateNumber.trim() || undefined,
        plate_region: plateRegion.trim() || undefined,
        ownership_type: ownershipType,
        purchase_date: purchaseDate || undefined,
        purchase_price: purchasePrice ? parseFloat(purchasePrice) : undefined,
        trailer_type: trailerType,
        length_ft: lengthFt ? parseInt(lengthFt, 10) : undefined,
        num_axles: numAxles ? parseInt(numAxles, 10) : undefined,
        gvwr_lbs: gvwrLbs ? parseInt(gvwrLbs, 10) : undefined,
        door_type: doorType || undefined,
        insurance_carrier: insuranceCarrier.trim() || undefined,
        insurance_policy_number: insurancePolicyNumber.trim() || undefined,
        insurance_expiry: insuranceExpiry || undefined,
        status,
        notes: notes.trim() || undefined,
      };
      if (isReefer) {
        payload.reefer_make = reeferMake.trim() || undefined;
        payload.reefer_model = reeferModel.trim() || undefined;
        payload.reefer_serial = reeferSerial.trim() || undefined;
      }
      await createTrailer(payload);
      onSuccess();
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "Failed to add trailer");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      <div
        className="absolute inset-0 z-0 bg-black/50"
        role="button"
        tabIndex={0}
        onClick={onCancel}
        onKeyDown={(e) => e.key === "Escape" && onCancel()}
        aria-label="Close"
      />
      <div
        className="relative z-10 ml-auto w-full max-w-xl bg-[var(--trk-bg)] border-l border-[var(--trk-border)] shadow-xl flex flex-col h-full overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--trk-border)] shrink-0">
          <h2 className="text-lg font-semibold text-[var(--trk-text)]">Add Trailer Asset</h2>
          <button
            type="button"
            onClick={onCancel}
            className="p-2 text-[var(--trk-text-muted)] hover:text-[var(--trk-text)] rounded hover:bg-[var(--trk-border)]"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col min-h-0 overflow-y-auto">
          <div className="flex-1 px-6 py-5 space-y-6">
            <FormSection title="Basic Info">
              <FormField label="Unit #" required>
                <input value={unitNumber} onChange={(e) => setUnitNumber(e.target.value)} className={FORM_INPUT_CLS} placeholder="T-101" required />
              </FormField>
              <FormField label="VIN">
                <input value={vin} onChange={(e) => setVin(e.target.value.toUpperCase())} className={FORM_INPUT_CLS} placeholder="1HGBH41JXMN109186" />
              </FormField>
              <FormField label="Year">
                <input type="number" min={1900} max={2100} value={year} onChange={(e) => setYear(e.target.value)} className={FORM_INPUT_CLS} placeholder="2024" />
              </FormField>
              <FormField label="Make">
                <input value={make} onChange={(e) => setMake(e.target.value)} className={FORM_INPUT_CLS} placeholder="Wabash" />
              </FormField>
              <FormField label="Model">
                <input value={model} onChange={(e) => setModel(e.target.value)} className={FORM_INPUT_CLS} placeholder="53 ft Reefer" />
              </FormField>
            </FormSection>

            <FormSection title="Registration & Ownership">
              <FormField label="Plate #">
                <input value={plateNumber} onChange={(e) => setPlateNumber(e.target.value)} className={FORM_INPUT_CLS} placeholder="ABC 1234" />
              </FormField>
              <FormField label="Plate Region">
                <input value={plateRegion} onChange={(e) => setPlateRegion(e.target.value)} className={FORM_INPUT_CLS} placeholder="CA" />
              </FormField>
              <FormField label="Ownership">
                <select value={ownershipType} onChange={(e) => setOwnershipType(e.target.value)} className={FORM_INPUT_CLS}>
                  {OWNERSHIP_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="Purchase Date">
                <input type="date" value={purchaseDate} onChange={(e) => setPurchaseDate(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
              <FormField label="Purchase Price ($)">
                <input type="number" min={0} step={0.01} value={purchasePrice} onChange={(e) => setPurchasePrice(e.target.value)} className={FORM_INPUT_CLS} placeholder="45000" />
              </FormField>
            </FormSection>

            <FormSection title="Trailer Specs">
              <FormField label="Trailer Type">
                <select value={trailerType} onChange={(e) => setTrailerType(e.target.value)} className={FORM_INPUT_CLS}>
                  {TRAILER_TYPE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="Length (ft)">
                <input type="number" min={1} value={lengthFt} onChange={(e) => setLengthFt(e.target.value)} className={FORM_INPUT_CLS} placeholder="53" />
              </FormField>
              <FormField label="Num Axles">
                <input type="number" min={1} value={numAxles} onChange={(e) => setNumAxles(e.target.value)} className={FORM_INPUT_CLS} placeholder="3" />
              </FormField>
              <FormField label="GVWR (lbs)">
                <input type="number" min={1} value={gvwrLbs} onChange={(e) => setGvwrLbs(e.target.value)} className={FORM_INPUT_CLS} placeholder="80000" />
              </FormField>
              <FormField label="Door Type">
                <select value={doorType} onChange={(e) => setDoorType(e.target.value)} className={FORM_INPUT_CLS}>
                  <option value="">—</option>
                  {DOOR_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FormField>
            </FormSection>

            {isReefer && (
              <FormSection title="Reefer Info">
                <FormField label="Reefer Make">
                  <input value={reeferMake} onChange={(e) => setReeferMake(e.target.value)} className={FORM_INPUT_CLS} placeholder="Carrier" />
                </FormField>
                <FormField label="Reefer Model">
                  <input value={reeferModel} onChange={(e) => setReeferModel(e.target.value)} className={FORM_INPUT_CLS} placeholder="X4 7500" />
                </FormField>
                <FormField label="Reefer Serial">
                  <input value={reeferSerial} onChange={(e) => setReeferSerial(e.target.value)} className={FORM_INPUT_CLS} placeholder="ABC123" />
                </FormField>
              </FormSection>
            )}

            <FormSection title="Insurance">
              <FormField label="Insurance Carrier">
                <input value={insuranceCarrier} onChange={(e) => setInsuranceCarrier(e.target.value)} className={FORM_INPUT_CLS} placeholder="Progressive" />
              </FormField>
              <FormField label="Policy #">
                <input value={insurancePolicyNumber} onChange={(e) => setInsurancePolicyNumber(e.target.value)} className={FORM_INPUT_CLS} placeholder="POL-12345" />
              </FormField>
              <FormField label="Expiry">
                <input type="date" value={insuranceExpiry} onChange={(e) => setInsuranceExpiry(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
            </FormSection>

            <FormSection title="Status & Notes">
              <FormField label="Status">
                <select value={status} onChange={(e) => setStatus(e.target.value)} className={FORM_INPUT_CLS}>
                  {TRAILER_STATUS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FormField>
              <div className="col-span-2">
                <label className={FORM_LABEL_CLS}>Notes</label>
                <textarea value={notes} onChange={(e) => setNotes(e.target.value)} className={`${FORM_INPUT_CLS} min-h-[80px] resize-y`} placeholder="Additional notes…" rows={3} />
              </div>
            </FormSection>
          </div>

          {error && <div className="px-6 py-2 text-sm text-red-400">{error}</div>}
          <div className="flex gap-3 px-6 py-4 border-t border-[var(--trk-border)] shrink-0 bg-[var(--trk-bg)]">
            <button type="submit" disabled={saving} className="px-4 py-2 rounded bg-[var(--trk-heading)] text-[var(--trk-bg)] text-sm font-medium hover:bg-[var(--trk-heading)] disabled:opacity-50">
              {saving ? "Adding…" : "Add Trailer"}
            </button>
            <button type="button" onClick={onCancel} className="px-4 py-2 rounded border border-[var(--trk-border-strong)] text-[var(--trk-text-muted)] text-sm hover:bg-[var(--trk-border)]">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function toDateInputValue(d: string | null | undefined): string {
  if (!d) return "";
  try {
    return new Date(d).toISOString().slice(0, 10);
  } catch {
    return "";
  }
}

function toDateTimeLocalValue(d: string | null | undefined): string {
  if (!d) return "";
  try {
    const date = new Date(d);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  } catch {
    return "";
  }
}

/** Edit truck form — full asset edit per fleet inventory spec */
function EditTruckForm({
  truck,
  onSuccess,
  onCancel,
  onError,
  error,
  saving,
  setSaving,
}: {
  truck: Truck;
  onSuccess: () => void;
  onCancel: () => void;
  onError: (s: string | null) => void;
  error: string | null;
  saving: boolean;
  setSaving: (v: boolean) => void;
}) {
  const t = truck as Record<string, unknown>;
  const [unitNumber, setUnitNumber] = useState(String(truck.unit_number ?? ""));
  const [vin, setVin] = useState(String(truck.vin ?? ""));
  const [year, setYear] = useState((truck.year ?? t.year) != null ? String(truck.year ?? t.year) : "");
  const [make, setMake] = useState(String(truck.make ?? t.make ?? ""));
  const [model, setModel] = useState(String(truck.model ?? t.model ?? ""));
  const [color, setColor] = useState(String(truck.color ?? t.color ?? ""));

  const [plateNumber, setPlateNumber] = useState(String(truck.plate_number ?? t.plate_number ?? ""));
  const [plateRegion, setPlateRegion] = useState(String(t.plate_region ?? ""));
  const [ownershipType, setOwnershipType] = useState(String(truck.ownership_type ?? t.ownership_type ?? "company"));
  const [purchaseDate, setPurchaseDate] = useState(toDateInputValue(String(t.purchase_date ?? "")));
  const [purchasePrice, setPurchasePrice] = useState((t.purchase_price ?? 0) ? String(t.purchase_price) : "");

  const [engineMake, setEngineMake] = useState(String(t.engine_make ?? ""));
  const [engineModel, setEngineModel] = useState(String(t.engine_model ?? ""));
  const [engineSerial, setEngineSerial] = useState(String(t.engine_serial ?? ""));
  const [horsepower, setHorsepower] = useState((t.horsepower ?? 0) ? String(t.horsepower) : "");
  const [fuelType, setFuelType] = useState(String(t.fuel_type ?? ""));
  const [transmission, setTransmission] = useState(String(t.transmission ?? ""));
  const [numAxles, setNumAxles] = useState((t.num_axles ?? 0) ? String(t.num_axles) : "");
  const [gvwrLbs, setGvwrLbs] = useState((t.gvwr_lbs ?? 0) ? String(t.gvwr_lbs) : "");

  const [odometerAtPurchase, setOdometerAtPurchase] = useState((t.odometer_at_purchase ?? 0) ? String(t.odometer_at_purchase) : "");
  const [currentOdometer, setCurrentOdometer] = useState((t.current_odometer ?? 0) ? String(t.current_odometer) : "");
  const [odometerLastUpdated, setOdometerLastUpdated] = useState(toDateTimeLocalValue(String(t.odometer_last_updated ?? "")));

  const [insuranceCarrier, setInsuranceCarrier] = useState(String(t.insurance_carrier ?? ""));
  const [insurancePolicyNumber, setInsurancePolicyNumber] = useState(String(t.insurance_policy_number ?? ""));
  const [insuranceExpiry, setInsuranceExpiry] = useState(toDateInputValue(String(t.insurance_expiry ?? "")));

  const [status, setStatus] = useState(String(truck.status ?? t.status ?? "active"));
  const [notes, setNotes] = useState(String(t.notes ?? ""));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    onError(null);
    if (!unitNumber.trim() || !vin.trim()) {
      onError("Unit number and VIN are required");
      return;
    }
    setSaving(true);
    try {
      await updateTruck(truck.id, {
        unit_number: unitNumber.trim(),
        vin: vin.trim().toUpperCase(),
        year: year ? parseInt(year, 10) : undefined,
        make: make.trim() || undefined,
        model: model.trim() || undefined,
        color: color.trim() || undefined,
        plate_number: plateNumber.trim() || undefined,
        plate_region: plateRegion.trim() || undefined,
        ownership_type: ownershipType,
        purchase_date: purchaseDate || undefined,
        purchase_price: purchasePrice ? parseFloat(purchasePrice) : undefined,
        engine_make: engineMake.trim() || undefined,
        engine_model: engineModel.trim() || undefined,
        engine_serial: engineSerial.trim() || undefined,
        horsepower: horsepower ? parseInt(horsepower, 10) : undefined,
        fuel_type: fuelType || undefined,
        transmission: transmission || undefined,
        num_axles: numAxles ? parseInt(numAxles, 10) : undefined,
        gvwr_lbs: gvwrLbs ? parseInt(gvwrLbs, 10) : undefined,
        odometer_at_purchase: odometerAtPurchase ? parseInt(odometerAtPurchase, 10) : undefined,
        current_odometer: currentOdometer ? parseInt(currentOdometer, 10) : undefined,
        odometer_last_updated: odometerLastUpdated
          ? (odometerLastUpdated.length === 16 ? `${odometerLastUpdated}:00` : odometerLastUpdated)
          : undefined,
        insurance_carrier: insuranceCarrier.trim() || undefined,
        insurance_policy_number: insurancePolicyNumber.trim() || undefined,
        insurance_expiry: insuranceExpiry || undefined,
        status,
        notes: notes.trim() || undefined,
      });
      onSuccess();
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "Failed to update truck");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      <div
        className="absolute inset-0 z-0 bg-black/50"
        role="button"
        tabIndex={0}
        onClick={onCancel}
        onKeyDown={(e) => e.key === "Escape" && onCancel()}
        aria-label="Close"
      />
      <div
        className="relative z-10 ml-auto w-full max-w-xl bg-[var(--trk-bg)] border-l border-[var(--trk-border)] shadow-xl flex flex-col h-full overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--trk-border)] shrink-0">
          <h2 className="text-lg font-semibold text-[var(--trk-text)]">Edit Truck — {truck.unit_number}</h2>
          <button
            type="button"
            onClick={onCancel}
            className="p-2 text-[var(--trk-text-muted)] hover:text-[var(--trk-text)] rounded hover:bg-[var(--trk-border)]"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col min-h-0 overflow-y-auto">
          <div className="flex-1 px-6 py-5 space-y-6">
            <FormSection title="Basic Info">
              <FormField label="Unit #" required>
                <input value={unitNumber} onChange={(e) => setUnitNumber(e.target.value)} className={FORM_INPUT_CLS} required />
              </FormField>
              <FormField label="VIN" required>
                <input value={vin} onChange={(e) => setVin(e.target.value.toUpperCase())} className={FORM_INPUT_CLS} required />
              </FormField>
              <FormField label="Year">
                <input type="number" min={1900} max={2100} value={year} onChange={(e) => setYear(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
              <FormField label="Make">
                <input value={make} onChange={(e) => setMake(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
              <FormField label="Model">
                <input value={model} onChange={(e) => setModel(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
              <FormField label="Color">
                <input value={color} onChange={(e) => setColor(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
            </FormSection>
            <FormSection title="Registration & Ownership">
              <FormField label="Plate #">
                <input value={plateNumber} onChange={(e) => setPlateNumber(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
              <FormField label="Plate Region">
                <input value={plateRegion} onChange={(e) => setPlateRegion(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
              <FormField label="Ownership">
                <select value={ownershipType} onChange={(e) => setOwnershipType(e.target.value)} className={FORM_INPUT_CLS}>
                  {OWNERSHIP_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="Purchase Date">
                <input type="date" value={purchaseDate} onChange={(e) => setPurchaseDate(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
              <FormField label="Purchase Price ($)">
                <input type="number" min={0} step={0.01} value={purchasePrice} onChange={(e) => setPurchasePrice(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
            </FormSection>
            <FormSection title="Powertrain & Specs">
              <FormField label="Engine Make"><input value={engineMake} onChange={(e) => setEngineMake(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Engine Model"><input value={engineModel} onChange={(e) => setEngineModel(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Engine Serial"><input value={engineSerial} onChange={(e) => setEngineSerial(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Horsepower">
                <input type="number" min={1} value={horsepower} onChange={(e) => setHorsepower(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
              <FormField label="Fuel Type">
                <select value={fuelType} onChange={(e) => setFuelType(e.target.value)} className={FORM_INPUT_CLS}>
                  <option value="">—</option>
                  {FUEL_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="Transmission">
                <select value={transmission} onChange={(e) => setTransmission(e.target.value)} className={FORM_INPUT_CLS}>
                  <option value="">—</option>
                  {TRANSMISSION_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="Num Axles">
                <input type="number" min={1} value={numAxles} onChange={(e) => setNumAxles(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
              <FormField label="GVWR (lbs)">
                <input type="number" min={1} value={gvwrLbs} onChange={(e) => setGvwrLbs(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
            </FormSection>
            <FormSection title="Odometer">
              <FormField label="Odometer at Purchase">
                <input type="number" min={0} value={odometerAtPurchase} onChange={(e) => setOdometerAtPurchase(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
              <FormField label="Current Odometer">
                <input type="number" min={0} value={currentOdometer} onChange={(e) => setCurrentOdometer(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
              <FormField label="Odometer Last Updated">
                <input type="datetime-local" value={odometerLastUpdated} onChange={(e) => setOdometerLastUpdated(e.target.value)} className={FORM_INPUT_CLS} />
              </FormField>
            </FormSection>
            <FormSection title="Insurance">
              <FormField label="Insurance Carrier"><input value={insuranceCarrier} onChange={(e) => setInsuranceCarrier(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Policy #"><input value={insurancePolicyNumber} onChange={(e) => setInsurancePolicyNumber(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Expiry"><input type="date" value={insuranceExpiry} onChange={(e) => setInsuranceExpiry(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
            </FormSection>
            <FormSection title="Status & Notes">
              <FormField label="Status">
                <select value={status} onChange={(e) => setStatus(e.target.value)} className={FORM_INPUT_CLS}>
                  {TRUCK_STATUS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </FormField>
              <div className="col-span-2">
                <label className={FORM_LABEL_CLS}>Notes</label>
                <textarea value={notes} onChange={(e) => setNotes(e.target.value)} className={`${FORM_INPUT_CLS} min-h-[80px] resize-y`} rows={3} />
              </div>
            </FormSection>
          </div>
          {error && <div className="px-6 py-2 text-sm text-red-400">{error}</div>}
          <div className="flex gap-3 px-6 py-4 border-t border-[var(--trk-border)] shrink-0 bg-[var(--trk-bg)]">
            <button type="submit" disabled={saving} className="px-4 py-2 rounded bg-[var(--trk-heading)] text-[var(--trk-bg)] text-sm font-medium hover:bg-[var(--trk-heading)] disabled:opacity-50">
              {saving ? "Saving…" : "Save"}
            </button>
            <button type="button" onClick={onCancel} className="px-4 py-2 rounded border border-[var(--trk-border-strong)] text-[var(--trk-text-muted)] text-sm hover:bg-[var(--trk-border)]">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** Edit trailer form — full asset edit per fleet inventory spec */
function EditTrailerForm({
  trailer,
  onSuccess,
  onCancel,
  onError,
  error,
  saving,
  setSaving,
}: {
  trailer: Trailer;
  onSuccess: () => void;
  onCancel: () => void;
  onError: (s: string | null) => void;
  error: string | null;
  saving: boolean;
  setSaving: (v: boolean) => void;
}) {
  const t = trailer as Record<string, unknown>;
  const [unitNumber, setUnitNumber] = useState(String(trailer.unit_number ?? ""));
  const [vin, setVin] = useState(String(trailer.vin ?? ""));
  const [year, setYear] = useState((trailer.year ?? t.year) != null ? String(trailer.year ?? t.year) : "");
  const [make, setMake] = useState(String(trailer.make ?? t.make ?? ""));
  const [model, setModel] = useState(String(trailer.model ?? t.model ?? ""));

  const [plateNumber, setPlateNumber] = useState(String(trailer.plate_number ?? t.plate_number ?? ""));
  const [plateRegion, setPlateRegion] = useState(String(t.plate_region ?? ""));
  const [ownershipType, setOwnershipType] = useState(String(trailer.ownership_type ?? t.ownership_type ?? "company"));
  const [purchaseDate, setPurchaseDate] = useState(toDateInputValue(String(t.purchase_date ?? "")));
  const [purchasePrice, setPurchasePrice] = useState((t.purchase_price ?? 0) ? String(t.purchase_price) : "");

  const [trailerType, setTrailerType] = useState(String(trailer.trailer_type ?? t.trailer_type ?? "dry_van"));
  const [lengthFt, setLengthFt] = useState((t.length_ft ?? 0) ? String(t.length_ft) : "");
  const [numAxles, setNumAxles] = useState((t.num_axles ?? 0) ? String(t.num_axles) : "");
  const [gvwrLbs, setGvwrLbs] = useState((t.gvwr_lbs ?? 0) ? String(t.gvwr_lbs) : "");
  const [doorType, setDoorType] = useState(String(t.door_type ?? ""));

  const [reeferMake, setReeferMake] = useState(String(t.reefer_make ?? ""));
  const [reeferModel, setReeferModel] = useState(String(t.reefer_model ?? ""));
  const [reeferSerial, setReeferSerial] = useState(String(t.reefer_serial ?? ""));

  const [insuranceCarrier, setInsuranceCarrier] = useState(String(t.insurance_carrier ?? ""));
  const [insurancePolicyNumber, setInsurancePolicyNumber] = useState(String(t.insurance_policy_number ?? ""));
  const [insuranceExpiry, setInsuranceExpiry] = useState(toDateInputValue(String(t.insurance_expiry ?? "")));

  const [status, setStatus] = useState(String(trailer.status ?? t.status ?? "active"));
  const [notes, setNotes] = useState(String(t.notes ?? ""));

  const isReefer = trailerType === "reefer";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    onError(null);
    if (!unitNumber.trim()) {
      onError("Unit number is required");
      return;
    }
    setSaving(true);
    try {
      const payload: Parameters<typeof updateTrailer>[1] = {
        unit_number: unitNumber.trim(),
        vin: vin.trim() || undefined,
        year: year ? parseInt(year, 10) : undefined,
        make: make.trim() || undefined,
        model: model.trim() || undefined,
        plate_number: plateNumber.trim() || undefined,
        plate_region: plateRegion.trim() || undefined,
        ownership_type: ownershipType,
        purchase_date: purchaseDate || undefined,
        purchase_price: purchasePrice ? parseFloat(purchasePrice) : undefined,
        trailer_type: trailerType,
        length_ft: lengthFt ? parseInt(lengthFt, 10) : undefined,
        num_axles: numAxles ? parseInt(numAxles, 10) : undefined,
        gvwr_lbs: gvwrLbs ? parseInt(gvwrLbs, 10) : undefined,
        door_type: doorType || undefined,
        insurance_carrier: insuranceCarrier.trim() || undefined,
        insurance_policy_number: insurancePolicyNumber.trim() || undefined,
        insurance_expiry: insuranceExpiry || undefined,
        status,
        notes: notes.trim() || undefined,
      };
      if (isReefer) {
        payload.reefer_make = reeferMake.trim() || undefined;
        payload.reefer_model = reeferModel.trim() || undefined;
        payload.reefer_serial = reeferSerial.trim() || undefined;
      } else {
        payload.reefer_make = null;
        payload.reefer_model = null;
        payload.reefer_serial = null;
      }
      await updateTrailer(trailer.id, payload);
      onSuccess();
    } catch (err: unknown) {
      onError(err instanceof Error ? err.message : "Failed to update trailer");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 z-0 bg-black/50" role="button" tabIndex={0} onClick={onCancel} onKeyDown={(e) => e.key === "Escape" && onCancel()} aria-label="Close" />
      <div
        className="relative z-10 ml-auto w-full max-w-xl bg-[var(--trk-bg)] border-l border-[var(--trk-border)] shadow-xl flex flex-col h-full overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--trk-border)] shrink-0">
          <h2 className="text-lg font-semibold text-[var(--trk-text)]">Edit Trailer — {trailer.unit_number}</h2>
          <button type="button" onClick={onCancel} className="p-2 text-[var(--trk-text-muted)] hover:text-[var(--trk-text)] rounded hover:bg-[var(--trk-border)]" aria-label="Close">✕</button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col min-h-0 overflow-y-auto">
          <div className="flex-1 px-6 py-5 space-y-6">
            <FormSection title="Basic Info">
              <FormField label="Unit #" required><input value={unitNumber} onChange={(e) => setUnitNumber(e.target.value)} className={FORM_INPUT_CLS} required /></FormField>
              <FormField label="VIN"><input value={vin} onChange={(e) => setVin(e.target.value.toUpperCase())} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Year"><input type="number" min={1900} max={2100} value={year} onChange={(e) => setYear(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Make"><input value={make} onChange={(e) => setMake(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Model"><input value={model} onChange={(e) => setModel(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
            </FormSection>
            <FormSection title="Registration & Ownership">
              <FormField label="Plate #"><input value={plateNumber} onChange={(e) => setPlateNumber(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Plate Region"><input value={plateRegion} onChange={(e) => setPlateRegion(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Ownership">
                <select value={ownershipType} onChange={(e) => setOwnershipType(e.target.value)} className={FORM_INPUT_CLS}>
                  {OWNERSHIP_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </FormField>
              <FormField label="Purchase Date"><input type="date" value={purchaseDate} onChange={(e) => setPurchaseDate(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Purchase Price ($)"><input type="number" min={0} step={0.01} value={purchasePrice} onChange={(e) => setPurchasePrice(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
            </FormSection>
            <FormSection title="Trailer Specs">
              <FormField label="Trailer Type">
                <select value={trailerType} onChange={(e) => setTrailerType(e.target.value)} className={FORM_INPUT_CLS}>
                  {TRAILER_TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </FormField>
              <FormField label="Length (ft)"><input type="number" min={1} value={lengthFt} onChange={(e) => setLengthFt(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Num Axles"><input type="number" min={1} value={numAxles} onChange={(e) => setNumAxles(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="GVWR (lbs)"><input type="number" min={1} value={gvwrLbs} onChange={(e) => setGvwrLbs(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Door Type">
                <select value={doorType} onChange={(e) => setDoorType(e.target.value)} className={FORM_INPUT_CLS}>
                  <option value="">—</option>
                  {DOOR_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </FormField>
            </FormSection>
            {isReefer && (
              <FormSection title="Reefer Info">
                <FormField label="Reefer Make"><input value={reeferMake} onChange={(e) => setReeferMake(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
                <FormField label="Reefer Model"><input value={reeferModel} onChange={(e) => setReeferModel(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
                <FormField label="Reefer Serial"><input value={reeferSerial} onChange={(e) => setReeferSerial(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              </FormSection>
            )}
            <FormSection title="Insurance">
              <FormField label="Insurance Carrier"><input value={insuranceCarrier} onChange={(e) => setInsuranceCarrier(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Policy #"><input value={insurancePolicyNumber} onChange={(e) => setInsurancePolicyNumber(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
              <FormField label="Expiry"><input type="date" value={insuranceExpiry} onChange={(e) => setInsuranceExpiry(e.target.value)} className={FORM_INPUT_CLS} /></FormField>
            </FormSection>
            <FormSection title="Status & Notes">
              <FormField label="Status">
                <select value={status} onChange={(e) => setStatus(e.target.value)} className={FORM_INPUT_CLS}>
                  {TRAILER_STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </FormField>
              <div className="col-span-2">
                <label className={FORM_LABEL_CLS}>Notes</label>
                <textarea value={notes} onChange={(e) => setNotes(e.target.value)} className={`${FORM_INPUT_CLS} min-h-[80px] resize-y`} rows={3} />
              </div>
            </FormSection>
          </div>
          {error && <div className="px-6 py-2 text-sm text-red-400">{error}</div>}
          <div className="flex gap-3 px-6 py-4 border-t border-[var(--trk-border)] shrink-0 bg-[var(--trk-bg)]">
            <button type="submit" disabled={saving} className="px-4 py-2 rounded bg-[var(--trk-heading)] text-[var(--trk-bg)] text-sm font-medium hover:bg-[var(--trk-heading)] disabled:opacity-50">{saving ? "Saving…" : "Save"}</button>
            <button type="button" onClick={onCancel} className="px-4 py-2 rounded border border-[var(--trk-border-strong)] text-[var(--trk-text-muted)] text-sm hover:bg-[var(--trk-border)]">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}
