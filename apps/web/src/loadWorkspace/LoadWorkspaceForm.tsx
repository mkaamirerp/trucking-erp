/**
 * Canonical editable load form — shared by LoadWorkspace (manual / detail / intake modes).
 */
import Button from "@/components/Button";
import type {
  Broker,
  BrokerContact,
  CustomsBroker,
  Driver,
  LoadDocumentParseReference,
  LoadNote,
  Trailer,
  Truck,
} from "@/api";
import {
  docFocusForStopAddress,
  docFocusForStopAppointment,
  docFocusForStopReference,
  formatEquipmentTempChip,
  formatLinehaulDisplay,
  wsGrid2,
  wsInputClass,
  wsLabelClass,
  wsSectionBody,
  wsSectionCard,
  wsSectionHeader,
  wsSectionMeta,
  wsSectionTitle,
  type DraftStop,
  type IntakeProposedFields,
  type LoadWorkspaceMode,
  type WorkspaceSection,
} from "./loadWorkspaceShared";
import { formatRouteFromStops } from "@/utils/loadStops";
import BrokerCarrierCombobox from "@/loadWorkspace/BrokerCarrierCombobox";
import {
  compactLoadReferencesForDisplay,
  displayOperationalReferenceLabel,
  VISIBLE_BROKER_LOAD_REFERENCE_LABEL,
  VISIBLE_INTERNAL_LOAD_NUMBER_LABEL,
  VISIBLE_REFERENCES_SECTION_LABEL,
} from "./loadOperationalReferences";

const L = wsLabelClass;
const I = wsInputClass;
/** Dense stop cards — same type scale as rest of form; tighten padding/gaps only */
const stopLb = `${L} !mb-0 leading-tight`;
const stopIc = `${I} !py-1 !px-1.5`;
/** Inner grid inside each stop card (half-width on lg — two columns of stops) */
const stopGridCol = "grid grid-cols-2 gap-x-1.5 gap-y-0.5";
const stopIconBtn =
  "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded border border-[var(--trk-border)] text-[13px] disabled:opacity-40";

type StopDenseCardProps = {
  stop: DraftStop;
  idx: number;
  total: number;
  verificationTabIndex: Map<string, number>;
  updateStop: (key: string, patch: Partial<DraftStop>) => void;
  removeStop: (key: string) => void;
  moveStop: (key: string, dir: -1 | 1) => void;
  focusDoc: (opts: { tokens: string[]; fallbackToken?: string }) => void;
};

function StopDenseCard({
  stop,
  idx,
  total,
  verificationTabIndex,
  updateStop,
  removeStop,
  moveStop,
  focusDoc,
}: StopDenseCardProps) {
  const u = (stop.stop_type || "").toUpperCase();
  const isPu = u === "PICKUP";
  const isDr = u === "DELIVERY" || u === "DROP";
  const pillClass = isPu
    ? "border border-emerald-800 bg-emerald-950/50 text-emerald-400"
    : isDr
      ? "border border-sky-800 bg-sky-950/40 text-sky-300"
      : "border border-[var(--trk-border)] bg-[var(--trk-surface-2)] text-[var(--trk-text-muted)]";

  return (
    <div className="min-w-0 rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-1.5 py-1">
      <div className="mb-0.5 flex flex-wrap items-center justify-between gap-x-1 gap-y-0.5">
        <div className="flex min-w-0 flex-wrap items-center gap-1">
          <span
            className={`inline-flex h-7 shrink-0 items-center rounded px-1.5 text-[10px] font-bold uppercase tracking-wide ${pillClass}`}
          >
            {idx + 1}
          </span>
          <select
            className={`${stopIc} !w-auto min-w-[6.5rem] !py-0.5`}
            aria-label="Stop type"
            value={stop.stop_type}
            onChange={(e) => updateStop(stop._key, { stop_type: e.target.value })}
          >
            <option value="PICKUP">PICKUP</option>
            <option value="DROP">DROP</option>
            <option value="DELIVERY">DELIVERY</option>
          </select>
          <input
            className={`${stopIc} !w-12 !px-1 text-center`}
            inputMode="numeric"
            title="Sequence"
            aria-label="Sequence"
            value={String(stop.sequence ?? 0)}
            onChange={(e) => updateStop(stop._key, { sequence: parseInt(e.target.value, 10) || 0 })}
          />
        </div>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            title="Move up"
            disabled={idx === 0}
            className={stopIconBtn}
            onClick={() => moveStop(stop._key, -1)}
          >
            ↑
          </button>
          <button
            type="button"
            title="Move down"
            disabled={idx === total - 1}
            className={stopIconBtn}
            onClick={() => moveStop(stop._key, 1)}
          >
            ↓
          </button>
          <button
            type="button"
            title="Remove"
            className={`${stopIconBtn} text-red-400`}
            onClick={() => removeStop(stop._key)}
          >
            ✕
          </button>
        </div>
      </div>
      <div className={stopGridCol}>
        <div className="col-span-2">
          <label className={stopLb}>Facility</label>
          <input
            className={stopIc}
            value={stop.facility_name ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::facility`)}
            onChange={(e) => updateStop(stop._key, { facility_name: e.target.value })}
            onFocus={() => focusDoc(docFocusForStopAddress(stop))}
          />
        </div>
        <div className="col-span-2">
          <label className={stopLb}>Street</label>
          <input
            className={stopIc}
            value={stop.street ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::street`)}
            onChange={(e) => updateStop(stop._key, { street: e.target.value })}
            onFocus={() => focusDoc(docFocusForStopAddress(stop))}
          />
        </div>
        <div className="col-span-2">
          <label className={stopLb}>Ref #</label>
          <input
            className={stopIc}
            value={stop.reference_number ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::reference`)}
            onChange={(e) => updateStop(stop._key, { reference_number: e.target.value })}
            onFocus={() => focusDoc(docFocusForStopReference(stop))}
          />
        </div>
        <div>
          <label className={stopLb}>City</label>
          <input
            className={stopIc}
            value={stop.city ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::city`)}
            onChange={(e) => updateStop(stop._key, { city: e.target.value })}
            onFocus={() => focusDoc(docFocusForStopAddress(stop))}
          />
        </div>
        <div>
          <label className={stopLb}>State</label>
          <input
            className={stopIc}
            value={stop.state_or_province ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::state`)}
            onChange={(e) => updateStop(stop._key, { state_or_province: e.target.value })}
            onFocus={() => focusDoc(docFocusForStopAddress(stop))}
          />
        </div>
        <div>
          <label className={stopLb}>Postal</label>
          <input
            className={stopIc}
            value={stop.postal_code ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::postal`)}
            onChange={(e) => updateStop(stop._key, { postal_code: e.target.value })}
            onFocus={() => focusDoc(docFocusForStopAddress(stop))}
          />
        </div>
        <div>
          <label className={stopLb}>Ctry</label>
          <input
            className={stopIc}
            maxLength={2}
            value={stop.country ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::country`)}
            onFocus={() => focusDoc(docFocusForStopAddress(stop))}
            onChange={(e) => updateStop(stop._key, { country: e.target.value })}
          />
        </div>
        <div>
          <label className={stopLb}>Date</label>
          <input
            className={stopIc}
            type="date"
            value={
              stop.appointment_date && stop.appointment_date.length >= 10
                ? stop.appointment_date.slice(0, 10)
                : (stop.appointment_date ?? "")
            }
            tabIndex={verificationTabIndex.get(`${stop._key}::apptDate`)}
            onChange={(e) => updateStop(stop._key, { appointment_date: e.target.value || null })}
            onFocus={() => focusDoc(docFocusForStopAppointment(stop))}
          />
        </div>
        <div>
          <label className={stopLb}>Time</label>
          <input
            className={stopIc}
            value={stop.appointment_time_text ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::apptTime`)}
            onChange={(e) => updateStop(stop._key, { appointment_time_text: e.target.value })}
            onFocus={() => focusDoc(docFocusForStopAppointment(stop))}
          />
        </div>
        <div className="col-span-2">
          <label className={stopLb}>Appt type</label>
          <input
            className={stopIc}
            value={stop.appointment_type ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::apptType`)}
            onChange={(e) => updateStop(stop._key, { appointment_type: e.target.value })}
            onFocus={() => focusDoc(docFocusForStopAppointment(stop))}
          />
        </div>
        <div className="col-span-2">
          <label className={`${stopLb} text-[var(--trk-heading)]`}>Stop notes</label>
          <textarea
            className={`${stopIc} min-h-[2rem] resize-y`}
            rows={1}
            data-testid="stop-notes-input"
            value={stop.notes ?? ""}
            onChange={(e) => updateStop(stop._key, { notes: e.target.value })}
          />
        </div>
        <div className="col-span-2">
          <label className={`${stopLb} text-[var(--trk-heading)]`}>Commodity notes</label>
          <textarea
            className={`${stopIc} min-h-[2rem] resize-y`}
            rows={1}
            data-testid="commodity-notes-input"
            value={stop.commodity_notes ?? ""}
            onChange={(e) => updateStop(stop._key, { commodity_notes: e.target.value })}
          />
        </div>
      </div>
    </div>
  );
}

export type LoadWorkspaceFormProps = {
  mode: LoadWorkspaceMode;
  /** Intake-pipeline proposed values. Null in manual/detail. Only fields the backend currently exposes. */
  intakeProposed: IntakeProposedFields | null;
  saving: boolean;
  freightBrokers: Broker[];
  brokerContacts: BrokerContact[];
  drivers: Driver[];
  trucks: Truck[];
  trailers: Trailer[];
  customsBrokers: CustomsBroker[];
  customsMessage: string | null;
  /** When true, customs broker select is frozen (edit + snapshot confirmed). */
  customsBrokerLocked: boolean;
  onCustomsBrokerChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  /** Edit mode only — confirm document snapshot */
  onConfirmSnapshot?: () => void;
  showOperationalNotesTimeline: boolean;
  loadNotes: LoadNote[];
  newNoteBody: string;
  setNewNoteBody: (v: string) => void;
  onAddNote: () => void;
  focusDoc: (opts: { tokens: string[]; fallbackToken?: string }) => void;
  verificationTabIndex: Map<string, number>;
  /** Stored Load.status — displayed only; readiness changes go through Mark ready. */
  status: string;
  loadNumber: string;
  setLoadNumber: (v: string) => void;
  brokerId: number | null;
  setBrokerId: (v: number | null) => void;
  brokerContactId: number | null;
  setBrokerContactId: (v: number | null) => void;
  brokerNameSnapshot: string;
  setBrokerNameSnapshot: (v: string) => void;
  brokerContactNameSnapshot: string;
  setBrokerContactNameSnapshot: (v: string) => void;
  brokerContactPhoneSnapshot: string;
  setBrokerContactPhoneSnapshot: (v: string) => void;
  brokerContactExtensionSnapshot: string;
  setBrokerContactExtensionSnapshot: (v: string) => void;
  brokerContactEmailSnapshot: string;
  setBrokerContactEmailSnapshot: (v: string) => void;
  brokerLoadReference: string;
  setBrokerLoadReference: (v: string) => void;
  loadReferences: LoadDocumentParseReference[];
  freightMode: string;
  setFreightMode: (v: string) => void;
  equipmentType: string;
  setEquipmentType: (v: string) => void;
  trailerType: string;
  setTrailerType: (v: string) => void;
  trailerSize: string;
  setTrailerSize: (v: string) => void;
  commodity: string;
  setCommodity: (v: string) => void;
  estimatedWeight: string;
  setEstimatedWeight: (v: string) => void;
  hazmat: "unset" | "yes" | "no";
  setHazmat: (v: "unset" | "yes" | "no") => void;
  temperatureRequirement: string;
  setTemperatureRequirement: (v: string) => void;
  palletCaseCount: string;
  setPalletCaseCount: (v: string) => void;
  rate: string;
  setRate: (v: string) => void;
  customerRate: string;
  setCustomerRate: (v: string) => void;
  miles: string;
  setMiles: (v: string) => void;
  /** Historical Load equipment — displayed only; equipment is assigned on the Trip. */
  driverId: number | null;
  truckId: number | null;
  trailerAssetId: number | null;
  /** When set, operational movement assignment is owned on the trip workspace (Slice 15A). */
  activeTripId?: number | null;
  customsBrokerId: number | null;
  internalNotes: string;
  setInternalNotes: (v: string) => void;
  draftStops: DraftStop[];
  sortedDraftStops: DraftStop[];
  updateStop: (key: string, patch: Partial<DraftStop>) => void;
  removeStop: (key: string) => void;
  addStop: () => void;
  moveStop: (key: string, dir: -1 | 1) => void;
  /** Sections to render. When omitted, all sections are shown (backwards-compatible). */
  visibleSections?: WorkspaceSection[];
  /** Sections that allow editing. When omitted, all visible sections are editable. */
  editableSections?: WorkspaceSection[];
  /** When true, all controls are disabled (e.g. Load Lab read-only preview). Uses a disabled fieldset. */
  readOnly?: boolean;
  /** When false, Notes render outside this form (page sidebar). Default true. */
  renderNotes?: boolean;
};

export function LoadWorkspaceForm(p: LoadWorkspaceFormProps) {
  const modeCreate = p.mode === "manual";
  const isIntake = p.mode === "intake";
  const ip = p.intakeProposed;

  /** Returns true when the section should be rendered. Omitting visibleSections shows all (backwards-compatible). */
  const vis = (s: WorkspaceSection) => !p.visibleSections || p.visibleSections.includes(s);
  /** Returns true when the section allows editing. Omitting editableSections allows all (backwards-compatible). */
  const editable = (s: WorkspaceSection) => !p.editableSections || p.editableSections.includes(s);

  /** Returns blue-tint inline style when a proposed value exists for this field; {} otherwise. */
  function prefill(proposedVal: string | null | undefined): React.CSSProperties {
    if (!proposedVal) return {};
    return { borderColor: "rgba(77,159,255,0.3)", backgroundColor: "rgba(77,159,255,0.04)", color: "#4d9fff" };
  }

  const compactReferences = compactLoadReferencesForDisplay(p.loadReferences ?? [], p.sortedDraftStops);

  const driver = p.driverId != null ? p.drivers.find((d) => d.id === p.driverId) : undefined;
  const driverLabel =
    p.driverId == null ? "— Unassigned —" : driver ? `${driver.first_name} ${driver.last_name}` : `Driver #${p.driverId}`;
  const truck = p.truckId != null ? p.trucks.find((t) => t.id === p.truckId) : undefined;
  const truckLabel = p.truckId == null ? "— None —" : truck ? truck.unit_number : `Truck #${p.truckId}`;
  const trailer = p.trailerAssetId != null ? p.trailers.find((t) => t.id === p.trailerAssetId) : undefined;
  const trailerLabel =
    p.trailerAssetId == null
      ? "— None —"
      : trailer
        ? `${trailer.unit_number}${trailer.trailer_type ? ` · ${trailer.trailer_type}` : ""}`
        : `Trailer #${p.trailerAssetId}`;

  return (
    <fieldset disabled={!!p.readOnly} className="m-0 min-w-0 border-0 p-0">
    <div className="grid grid-cols-1 gap-3 pb-4 lg:grid-cols-2">
      {/* Broker/Carrier — WorkspaceSection: Parties */}
      {vis("Parties") && <section className={wsSectionCard} data-editable={editable("Parties")}>
        <div className={`${wsSectionHeader} py-3`}>
          <span className={wsSectionTitle}>Broker/Carrier</span>
          <span className="rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-0.5 text-[11px] font-semibold text-[var(--trk-text-muted)]">
            {formatEquipmentTempChip(p.trailerType, p.equipmentType, p.temperatureRequirement)}
          </span>
        </div>
        <div className={wsSectionBody}>
        <div className={wsGrid2}>
          <BrokerCarrierCombobox
            brokers={p.freightBrokers}
            brokerId={p.brokerId}
            brokerNameSnapshot={p.brokerNameSnapshot}
            disabled={!!p.readOnly}
            onPick={(id, name) => {
              p.setBrokerId(id);
              p.setBrokerNameSnapshot(name);
              if (id === null) p.setBrokerContactId(null);
            }}
          />
          <div>
            <label className={L}>Contact</label>
            <select
              className={I}
              value={p.brokerContactId ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                p.setBrokerContactId(v === "" ? null : Number(v));
              }}
              disabled={!p.brokerId}
            >
              <option value="">— Select contact —</option>
              {p.brokerContacts.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={L}>Contact name</label>
            <input
              className={I}
              value={p.brokerContactNameSnapshot}
              onChange={(e) => p.setBrokerContactNameSnapshot(e.target.value)}
            />
          </div>
          <div>
            <label className={L}>Contact phone</label>
            <input
              className={I}
              value={p.brokerContactPhoneSnapshot}
              onChange={(e) => p.setBrokerContactPhoneSnapshot(e.target.value)}
            />
          </div>
          <div>
            <label className={L}>Extension</label>
            <input
              className={I}
              value={p.brokerContactExtensionSnapshot}
              onChange={(e) => p.setBrokerContactExtensionSnapshot(e.target.value)}
            />
          </div>
          <div>
            <label className={L}>Contact email</label>
            <input
              className={I}
              value={p.brokerContactEmailSnapshot}
              onChange={(e) => p.setBrokerContactEmailSnapshot(e.target.value)}
            />
          </div>
          <div className="sm:col-span-2">
            <label className={L}>{VISIBLE_BROKER_LOAD_REFERENCE_LABEL}</label>
            <input
              className={I}
              value={p.brokerLoadReference}
              tabIndex={p.verificationTabIndex.get("brokerLoadReference")}
              onChange={(e) => p.setBrokerLoadReference(e.target.value)}
              placeholder="Load number from broker"
              onFocus={() =>
                p.focusDoc({
                  tokens: [p.brokerLoadReference, "broker load", "load ref", "ref", "reference", "confirmation", "rate con", "bol"],
                  fallbackToken: "ref",
                })
              }
            />
          </div>
          {compactReferences.length > 0 ? (
            <div className="sm:col-span-2">
              <label className={L}>{VISIBLE_REFERENCES_SECTION_LABEL}</label>
              <ul className="mt-1 space-y-1 rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm">
                {compactReferences.map((r, i) => (
                  <li key={`${r.kind}-${r.value}-${i}`} className="flex flex-wrap gap-x-2 gap-y-0.5">
                    <span className="text-[var(--trk-text-muted)]">{displayOperationalReferenceLabel(r)}</span>
                    <span className="font-mono text-[var(--trk-text)]">{r.value}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
        </div>
      </section>}

      {(vis("Equipment") || vis("Assignment")) && (
        <div className="flex flex-col gap-3">
      {/* Financials — WorkspaceSection: Equipment (financial/cargo parameters travel together) */}
      {vis("Equipment") && <section className={wsSectionCard} data-editable={editable("Equipment")}>
        <div className={`${wsSectionHeader} py-3`}>
          <div className="min-w-0">
            <span className={wsSectionTitle}>Financials</span>
            {editable("Equipment") && !p.readOnly ? (
              <p className="mt-0.5 text-[10px] font-normal text-[var(--trk-text-muted)]">
                Linehaul rate is editable in any load state — correct parser mistakes here, then save.
              </p>
            ) : null}
          </div>
          {editable("Equipment") && !p.readOnly ? (
            <input
              className="w-[8.5rem] shrink-0 rounded border border-emerald-900/50 bg-emerald-950/40 px-2.5 py-0.5 text-right font-mono text-sm font-bold text-[var(--trk-success)] placeholder:text-emerald-700/60 focus:border-emerald-600 focus:outline-none focus:ring-1 focus:ring-emerald-600/40"
              inputMode="decimal"
              value={p.rate}
              tabIndex={p.verificationTabIndex.get("rate")}
              onChange={(e) => p.setRate(e.target.value)}
              onFocus={() =>
                p.focusDoc({
                  tokens: [p.rate, "rate", "linehaul", "$", "total", "amount"],
                  fallbackToken: "rate",
                })
              }
              aria-label="Linehaul rate"
              placeholder="Linehaul"
              title="Linehaul rate from rate confirmation — edit anytime before save"
            />
          ) : (
            <span className="rounded border border-emerald-900/50 bg-emerald-950/40 px-2.5 py-0.5 font-mono text-sm font-bold text-[var(--trk-success)]">
              {formatLinehaulDisplay(p.rate) ?? "—"}
            </span>
          )}
        </div>
        <div className={wsSectionBody}>
        <div className={wsGrid2}>
          <div className="sm:col-span-2">
            <label className={L}>{VISIBLE_INTERNAL_LOAD_NUMBER_LABEL}</label>
            <p className="font-mono text-sm text-[var(--trk-text)]">
              {(p.loadNumber || "").trim() || "—"}
            </p>
            <p className="mt-0.5 text-xs text-[var(--trk-muted)]">
              Assigned when the load is created; cannot be edited.
            </p>
          </div>
          <div>
            <label className={L}>Customer rate</label>
            <input
              className={I}
              inputMode="decimal"
              value={p.customerRate}
              onChange={(e) => p.setCustomerRate(e.target.value)}
            />
          </div>
          <div>
            <label className={L}>Miles (loaded)</label>
            <input
              className={I}
              inputMode="numeric"
              value={p.miles}
              onChange={(e) => p.setMiles(e.target.value)}
            />
          </div>
        </div>
        </div>
      </section>}

      {/* Assignment — WorkspaceSection: Assignment */}
      {vis("Assignment") && <section className={wsSectionCard} data-editable={editable("Assignment")}>
        <div className={wsSectionHeader}>
          <span className={wsSectionTitle}>Status &amp; assignment</span>
          <span className={wsSectionMeta}>Read-only</span>
        </div>
        <div className={wsSectionBody}>
        <div className={wsGrid2}>
          <div>
            <label className={L}>Status</label>
            <input className={I} value={p.status || "draft"} readOnly disabled data-testid="load-status-readonly" />
          </div>
          <div>
            <label className={L}>Driver</label>
            <input className={I} value={driverLabel} readOnly disabled data-testid="load-driver-readonly" />
          </div>
          <div>
            <label className={L}>Truck</label>
            <input className={I} value={truckLabel} readOnly disabled data-testid="load-truck-readonly" />
          </div>
          <div>
            <label className={L}>Trailer</label>
            <input className={I} value={trailerLabel} readOnly disabled data-testid="load-trailer-readonly" />
          </div>
        </div>
        <p className="mt-2 text-[11px] leading-snug text-[var(--trk-text-muted)]">
          Use <span className="font-medium text-[var(--trk-text)]">Mark ready</span> for draft → ready. Driver, truck,
          trailer, and trip status are set on the Trip, not on the Load.
        </p>
        {p.activeTripId != null && p.activeTripId > 0 ? (
          <p className="mt-1.5 text-[10px] leading-snug text-[var(--trk-text-muted)]">
            This load is on a trip — use{" "}
            <span className="font-medium text-[var(--trk-text)]">View / Assign on Trip</span> in the header to set driver,
            truck, and trailer.
          </p>
        ) : null}
        </div>
      </section>}
        </div>
      )}

      {/* Stops — WorkspaceSection: Stops */}
      {vis("Stops") && <section className={`${wsSectionCard} lg:col-span-2`} data-editable={editable("Stops")}>
        <div className={`${wsSectionHeader} !py-1.5`}>
          <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0">
            <span className={wsSectionTitle}>Stops</span>
            <span className={wsSectionMeta}>
              {p.sortedDraftStops.length} · {formatRouteFromStops(p.sortedDraftStops)}
            </span>
          </span>
          <button
            type="button"
            onClick={p.addStop}
            className="shrink-0 text-[11px] font-semibold text-[var(--trk-heading)] hover:underline"
          >
            + Add stop
          </button>
        </div>
        <div className="px-2 py-1.5">
        {isIntake && ip?.pickupDeliverySummary ? (
          <p className="mb-1.5 rounded border border-sky-900/40 bg-sky-950/30 px-2 py-1 text-[10px] text-sky-400">
            Intake: {ip.pickupDeliverySummary}
          </p>
        ) : null}
        <div className="grid w-full grid-cols-1 gap-1 lg:grid-cols-2 lg:items-start">
          {p.sortedDraftStops.length === 0 ? (
            <p className="col-span-full py-1.5 text-center text-[11px] text-[var(--trk-text-muted)]">
              No stops yet — add pickup and delivery.
            </p>
          ) : (
            p.sortedDraftStops.map((stop, idx) => (
              <StopDenseCard
                key={stop._key}
                stop={stop}
                idx={idx}
                total={p.sortedDraftStops.length}
                verificationTabIndex={p.verificationTabIndex}
                updateStop={p.updateStop}
                removeStop={p.removeStop}
                moveStop={p.moveStop}
                focusDoc={p.focusDoc}
              />
            ))
          )}
        </div>
        </div>
      </section>}

      {/* Freight & equipment — WorkspaceSection: Equipment */}
      {vis("Equipment") && <section className={wsSectionCard} data-editable={editable("Equipment")}>
        <div className={wsSectionHeader}>
          <span className={wsSectionTitle}>Freight & equipment</span>
        </div>
        <div className={wsSectionBody}>
        <div className={wsGrid2}>
          <div>
            <label className={L}>Mode</label>
            <input
              className={I}
              value={p.freightMode}
              onChange={(e) => p.setFreightMode(e.target.value)}
            />
          </div>
          <div>
            <label className={L}>Equipment type</label>
            <input
              className={I}
              value={p.equipmentType}
              tabIndex={p.verificationTabIndex.get("equipmentType")}
              onChange={(e) => p.setEquipmentType(e.target.value)}
              onFocus={() =>
                p.focusDoc({
                  tokens: [p.equipmentType, "equipment", "trailer", "van", "reefer", "flatbed"],
                  fallbackToken: "equipment",
                })
              }
            />
          </div>
          <div>
            <label className={L}>Trailer type</label>
            <input
              className={I}
              value={p.trailerType}
              tabIndex={p.verificationTabIndex.get("trailerType")}
              onChange={(e) => p.setTrailerType(e.target.value)}
              onFocus={() =>
                p.focusDoc({
                  tokens: [
                    p.trailerType,
                    "trailer type",
                    "trailer",
                    "equipment",
                    "dry van",
                    "reefer",
                    "flatbed",
                    "step deck",
                    "53",
                  ],
                  fallbackToken: "trailer",
                })
              }
            />
          </div>
          <div>
            <label className={L}>Trailer size</label>
            <input
              className={I}
              value={p.trailerSize}
              onChange={(e) => p.setTrailerSize(e.target.value)}
            />
          </div>
          <div className="sm:col-span-2">
            <label className={L}>Commodity</label>
            <input
              className={I}
              value={p.commodity}
              tabIndex={p.verificationTabIndex.get("commodity")}
              onChange={(e) => p.setCommodity(e.target.value)}
              onFocus={() =>
                p.focusDoc({
                  tokens: [
                    p.commodity,
                    "commodity",
                    "product",
                    "freight",
                    "description",
                    "cargo",
                    "sku",
                  ],
                  fallbackToken: "commodity",
                })
              }
            />
          </div>
          <div>
            <label className={L}>Est. weight (lb)</label>
            <input
              className={I}
              inputMode="numeric"
              value={p.estimatedWeight}
              tabIndex={p.verificationTabIndex.get("estimatedWeight")}
              onChange={(e) => p.setEstimatedWeight(e.target.value)}
              onFocus={() =>
                p.focusDoc({
                  tokens: [
                    p.estimatedWeight,
                    "weight",
                    "lbs",
                    "lb",
                    "pounds",
                    "gross",
                    "net weight",
                  ],
                  fallbackToken: "weight",
                })
              }
            />
          </div>
          <div>
            <label className={L}>Hazmat</label>
            <select
              className={I}
              value={p.hazmat}
              onChange={(e) => p.setHazmat(e.target.value as "unset" | "yes" | "no")}
            >
              <option value="unset">— Unset —</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </div>
          <div>
            <label className={L}>Temperature</label>
            <input
              className={I}
              value={p.temperatureRequirement}
              onChange={(e) => p.setTemperatureRequirement(e.target.value)}
            />
          </div>
          <div>
            <label className={L}>Pallet / case count</label>
            <input
              className={I}
              value={p.palletCaseCount}
              onChange={(e) => p.setPalletCaseCount(e.target.value)}
            />
          </div>
        </div>
        </div>
      </section>}

      {/* Customs — WorkspaceSection: Documents */}
      {vis("Documents") && <section className={wsSectionCard} data-editable={editable("Documents")}>
        <div className={wsSectionHeader}>
          <span className={wsSectionTitle}>Customs</span>
        </div>
        <div className={wsSectionBody}>
        {p.customsMessage ? <p className="mb-3 text-sm text-[var(--trk-text)]">{p.customsMessage}</p> : null}
        <div className="space-y-4">
          <div>
            <label className={L}>Customs broker</label>
            <select
              className={I}
              disabled={p.saving || p.customsBrokerLocked}
              value={p.customsBrokerId ?? ""}
              onChange={p.onCustomsBrokerChange}
            >
              <option value="">— None —</option>
              {p.customsBrokers.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.legal_name}
                </option>
              ))}
            </select>
            {modeCreate ? (
              <p className="mt-1 text-xs text-[var(--trk-text-muted)]">
                Stored on the new load. Document snapshot confirmation is available after you create the load.
              </p>
            ) : !p.customsBrokerLocked ? (
              <p className="mt-1 text-xs text-[var(--trk-warning)]">
                Changing this selection saves immediately (before snapshot confirm).
              </p>
            ) : null}
          </div>
          {!modeCreate && (
            <div className="flex flex-wrap gap-2">
              <Button
                variant="primary"
                disabled={p.saving || !p.customsBrokerId || p.customsBrokerLocked || !p.onConfirmSnapshot}
                onClick={p.onConfirmSnapshot}
              >
                Confirm document snapshot
              </Button>
            </div>
          )}
          {!modeCreate &&
            (p.customsBrokerLocked ? (
              <p className="text-xs text-[var(--trk-text-muted)]">Customs broker link is frozen after snapshot confirm.</p>
            ) : (
              <p className="text-xs text-[var(--trk-text-muted)]">
                Link a customs broker, then confirm to freeze customs snapshot fields on this load.
              </p>
            ))}
        </div>
        </div>
      </section>}

      {/* Notes & documents — WorkspaceSection: Notes */}
      {vis("Notes") && p.renderNotes !== false ? (
        <LoadWorkspaceNotesPanel
          className="lg:col-span-2"
          dataEditable={editable("Notes")}
          internalNotes={p.internalNotes}
          setInternalNotes={p.setInternalNotes}
          showOperationalNotesTimeline={p.showOperationalNotesTimeline}
          loadNotes={p.loadNotes}
          newNoteBody={p.newNoteBody}
          setNewNoteBody={p.setNewNoteBody}
          onAddNote={p.onAddNote}
          saving={p.saving}
        />
      ) : null}

      <p className="text-center text-[10px] text-[var(--trk-text-muted)]">UI bundle {__UI_BUILD_ID__}</p>
    </div>
    </fieldset>
  );
}

export type LoadWorkspaceNotesPanelProps = {
  internalNotes: string;
  setInternalNotes: (v: string) => void;
  showOperationalNotesTimeline: boolean;
  loadNotes: LoadNote[];
  newNoteBody: string;
  setNewNoteBody: (v: string) => void;
  onAddNote: () => void;
  saving: boolean;
  className?: string;
  dataEditable?: boolean;
};

export function LoadWorkspaceNotesPanel(p: LoadWorkspaceNotesPanelProps) {
  return (
    <section className={`${wsSectionCard} ${p.className ?? ""}`} data-editable={p.dataEditable}>
      <div className={wsSectionHeader}>
        <span className={wsSectionTitle}>Notes & documents</span>
      </div>
      <div className={wsSectionBody}>
        <div>
          <label className={L}>Internal notes (load)</label>
          <textarea
            className={I}
            rows={5}
            value={p.internalNotes}
            onChange={(e) => p.setInternalNotes(e.target.value)}
            placeholder="e.g. rate confirmation excerpt, intake text…"
          />
        </div>
        {p.showOperationalNotesTimeline ? (
          <div className="mt-4 border-t border-[var(--trk-border)] pt-3">
            <p className={L}>Operational notes (timeline)</p>
            <ul className="mt-2 max-h-44 space-y-2 overflow-y-auto rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] p-2.5 text-sm">
              {p.loadNotes.length === 0 ? (
                <li className="text-xs text-[var(--trk-text-muted)]">No notes yet.</li>
              ) : (
                p.loadNotes.map((n) => (
                  <li key={n.id} className="border-b border-[var(--trk-border)] pb-2 last:border-0">
                    <p className="text-[var(--trk-text)]">{n.body}</p>
                    <p className="text-[10px] text-[var(--trk-text-muted)]">{new Date(n.created_at).toLocaleString()}</p>
                  </li>
                ))
              )}
            </ul>
            <div className="mt-2 flex flex-col gap-2">
              <input
                className={I}
                placeholder="Add operational note…"
                value={p.newNoteBody}
                onChange={(e) => p.setNewNoteBody(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), void p.onAddNote())}
              />
              <Button
                variant="secondary"
                type="button"
                disabled={p.saving || !p.newNoteBody.trim()}
                onClick={p.onAddNote}
              >
                Add note
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
