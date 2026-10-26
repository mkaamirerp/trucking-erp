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
  bindDocFocus,
  docFocusForBroker,
  docFocusForBrokerContactEmail,
  docFocusForBrokerContactName,
  docFocusForBrokerContactPhone,
  docFocusForBrokerLoadReference,
  docFocusForFreightHints,
  docFocusForMoneyField,
  docFocusForStopAppointmentDate,
  docFocusForStopAppointmentTime,
  docFocusForStopAppointmentType,
  docFocusForStopCity,
  docFocusForStopCountry,
  docFocusForStopFacility,
  docFocusForStopNotes,
  docFocusForStopPostal,
  docFocusForStopReference,
  docFocusForStopState,
  docFocusForStopStreet,
  type DocFocusOpts,
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
import {
  ParseConfidenceField,
  confidenceTierForFieldKey,
  parseConfidenceTierLabel,
} from "@/loadWorkspace/parseFieldConfidenceUi";
import type { ParseScalarFieldKey } from "@/loadWorkspace/loadParseHydrationState";

const L = wsLabelClass;
const I = wsInputClass;
/** Dense stop cards — same tokens as Financials / Freight sections; layout only differs */
const stopLb = `${L} !mb-0.5`;
const stopIc = `${I} !py-1 !px-2 !text-[13px]`;
const stopGridCol =
  "grid grid-cols-6 gap-x-1.5 gap-y-1 sm:grid-cols-12 sm:gap-x-2 sm:gap-y-1";
const stopIconBtn =
  "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] text-[var(--trk-text-muted)] text-[12px] hover:border-[var(--trk-heading)]/40 disabled:opacity-40";

function stopCardShellClass(isPu: boolean, isDr: boolean): string {
  const base =
    "min-w-0 rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-2 py-1.5 shadow-none";
  if (isPu) return `${base} border-l-2 border-l-[var(--trk-success)]`;
  if (isDr) return `${base} border-l-2 border-l-[var(--trk-heading)]`;
  return `${base} border-l-2 border-l-[var(--trk-border-strong)]`;
}

/** Column count follows the stops section container width (sidebar constrains content — not viewport alone). */
function stopListGridClass(): string {
  return "grid grid-cols-1 gap-1 @[26rem]/stops:grid-cols-2 @[40rem]/stops:grid-cols-3 @[54rem]/stops:grid-cols-4 @[26rem]/stops:items-start";
}

function autoGrowStopNotes(el: HTMLTextAreaElement) {
  el.style.height = "2rem";
  el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
}

type StopDenseCardProps = {
  stop: DraftStop;
  idx: number;
  total: number;
  verificationTabIndex: Map<string, number>;
  updateStop: (key: string, patch: Partial<DraftStop>) => void;
  removeStop: (key: string) => void;
  moveStop: (key: string, dir: -1 | 1) => void;
  focusDoc: (opts: DocFocusOpts) => void;
  sectionIndex: number;
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
  sectionIndex,
}: StopDenseCardProps) {
  const bind = (opts: DocFocusOpts) => bindDocFocus(focusDoc, opts);
  const u = (stop.stop_type || "").toUpperCase();
  const isPu = u === "PICKUP";
  const isDr = u === "DELIVERY" || u === "DROP";
  return (
    <div className={stopCardShellClass(isPu, isDr)}>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-x-1 gap-y-0.5 border-b border-[var(--trk-border)]/80 pb-1">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <span
            className="inline-flex h-7 min-w-[1.75rem] shrink-0 items-center justify-center rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-1.5 text-[10px] font-bold text-[var(--trk-heading)]"
            title={`Stop ${idx + 1} · sequence ${stop.sequence ?? idx}`}
          >
            {idx + 1}
          </span>
          <select
            className={`${stopIc} !w-auto min-w-[6.5rem] !bg-[var(--trk-bg)]`}
            aria-label="Stop type"
            value={stop.stop_type}
            onChange={(e) => updateStop(stop._key, { stop_type: e.target.value })}
          >
            <option value="PICKUP">PICKUP</option>
            <option value="DROP">DROP</option>
            <option value="DELIVERY">DELIVERY</option>
          </select>
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
        <div className="col-span-4 sm:col-span-8">
          <label className={stopLb}>Facility</label>
          <input
            className={stopIc}
            value={stop.facility_name ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::facility`)}
            onChange={(e) => updateStop(stop._key, { facility_name: e.target.value })}
            {...bind(docFocusForStopFacility(stop, sectionIndex))}
          />
        </div>
        <div className="col-span-2 sm:col-span-4">
          <label className={stopLb}>Ref #</label>
          <input
            className={stopIc}
            value={stop.reference_number ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::reference`)}
            onChange={(e) => updateStop(stop._key, { reference_number: e.target.value })}
            {...bind(docFocusForStopReference(stop, sectionIndex))}
          />
        </div>
        <div className="col-span-6 sm:col-span-12">
          <label className={stopLb}>Street</label>
          <input
            className={stopIc}
            value={stop.street ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::street`)}
            onChange={(e) => updateStop(stop._key, { street: e.target.value })}
            {...bind(docFocusForStopStreet(stop, sectionIndex))}
          />
        </div>
        <div className="col-span-3 sm:col-span-5">
          <label className={stopLb}>City</label>
          <input
            className={stopIc}
            value={stop.city ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::city`)}
            onChange={(e) => updateStop(stop._key, { city: e.target.value })}
            {...bind(docFocusForStopCity(stop, sectionIndex))}
          />
        </div>
        <div className="col-span-1 sm:col-span-2">
          <label className={stopLb}>St</label>
          <input
            className={stopIc}
            value={stop.state_or_province ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::state`)}
            onChange={(e) => updateStop(stop._key, { state_or_province: e.target.value })}
            {...bind(docFocusForStopState(stop, sectionIndex))}
          />
        </div>
        <div className="col-span-1 sm:col-span-3">
          <label className={stopLb}>Postal</label>
          <input
            className={stopIc}
            value={stop.postal_code ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::postal`)}
            onChange={(e) => updateStop(stop._key, { postal_code: e.target.value })}
            {...bind(docFocusForStopPostal(stop, sectionIndex))}
          />
        </div>
        <div className="col-span-1 sm:col-span-2">
          <label className={stopLb}>Ctry</label>
          <input
            className={stopIc}
            maxLength={2}
            value={stop.country ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::country`)}
            {...bind(docFocusForStopCountry(stop, sectionIndex))}
            onChange={(e) => updateStop(stop._key, { country: e.target.value })}
          />
        </div>
        <div className="col-span-2 sm:col-span-4">
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
            {...bind(docFocusForStopAppointmentDate(stop, sectionIndex))}
          />
        </div>
        <div className="col-span-2 sm:col-span-4">
          <label className={stopLb}>Time</label>
          <input
            className={stopIc}
            value={stop.appointment_time_text ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::apptTime`)}
            onChange={(e) => updateStop(stop._key, { appointment_time_text: e.target.value })}
            {...bind(docFocusForStopAppointmentTime(stop, sectionIndex))}
          />
        </div>
        <div className="col-span-2 sm:col-span-4">
          <label className={stopLb}>Appt type</label>
          <input
            className={stopIc}
            value={stop.appointment_type ?? ""}
            tabIndex={verificationTabIndex.get(`${stop._key}::apptType`)}
            onChange={(e) => updateStop(stop._key, { appointment_type: e.target.value })}
            {...bind(docFocusForStopAppointmentType(stop, sectionIndex))}
          />
        </div>
        <div className="col-span-3 sm:col-span-6">
          <label className={stopLb}>Stop notes</label>
          <textarea
            className={`${stopIc} min-h-[2rem] resize-y`}
            rows={1}
            data-testid="stop-notes-input"
            value={stop.notes ?? ""}
            onChange={(e) => updateStop(stop._key, { notes: e.target.value })}
            onInput={(e) => autoGrowStopNotes(e.currentTarget)}
            {...bind(docFocusForStopNotes(stop, sectionIndex, stop.notes ?? ""))}
          />
        </div>
        <div className="col-span-3 sm:col-span-6">
          <label className={stopLb}>Commodity notes</label>
          <textarea
            className={`${stopIc} min-h-[2rem] resize-y`}
            rows={1}
            data-testid="commodity-notes-input"
            value={stop.commodity_notes ?? ""}
            onChange={(e) => updateStop(stop._key, { commodity_notes: e.target.value })}
            onInput={(e) => autoGrowStopNotes(e.currentTarget)}
            {...bind(docFocusForStopNotes(stop, sectionIndex, stop.commodity_notes ?? ""))}
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
  focusDoc: (opts: DocFocusOpts) => void;
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
  /** Trip movement assignment (UI state before Create load creates the Trip). */
  driverId: number | null;
  truckId: number | null;
  trailerAssetId: number | null;
  setDriverId?: (v: number | null) => void;
  setTruckId?: (v: number | null) => void;
  setTrailerAssetId?: (v: number | null) => void;
  /** Policy warnings from equipment assignment suggestions (shown before confirm). */
  assignmentWarnings?: string[];
  onAssignmentDriverChange?: (driverId: number | null) => void;
  onAssignmentTruckChange?: (truckId: number | null) => void;
  onAssignmentTrailerChange?: (trailerId: number | null) => void;
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
  /** Parser field_confidence map for input-level review accents. */
  fieldConfidence?: Record<string, string>;
  parseManualOverrideKeys?: Set<ParseScalarFieldKey>;
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
  const bindFieldDoc = (opts: DocFocusOpts) => bindDocFocus(p.focusDoc, opts);
  const fieldConfidence = p.fieldConfidence ?? {};
  const manualScalar = (key: ParseScalarFieldKey) => p.parseManualOverrideKeys?.has(key) ?? false;
  const stopsRouteConfidence = confidenceTierForFieldKey("stops", fieldConfidence);

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
          <ParseConfidenceField
            label="Broker / carrier"
            labelClassName={L}
            confidenceKey="broker_name_snapshot"
            fieldConfidence={fieldConfidence}
            manualOverride={manualScalar("brokerNameSnapshot")}
          >
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
              docFocusHandlers={bindFieldDoc(docFocusForBroker(p.brokerNameSnapshot))}
            />
          </ParseConfidenceField>
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
              {...bindFieldDoc(
                docFocusForBrokerContactName(p.brokerContactNameSnapshot),
              )}
            >
              <option value="">— Select contact —</option>
              {p.brokerContacts.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <ParseConfidenceField
            label="Contact name"
            labelClassName={L}
            confidenceKey="broker_contact_name_snapshot"
            fieldConfidence={fieldConfidence}
          >
            <input
              className={I}
              value={p.brokerContactNameSnapshot}
              onChange={(e) => p.setBrokerContactNameSnapshot(e.target.value)}
              {...bindFieldDoc(docFocusForBrokerContactName(p.brokerContactNameSnapshot))}
            />
          </ParseConfidenceField>
          <ParseConfidenceField
            label="Contact phone"
            labelClassName={L}
            confidenceKey="broker_contact_phone_snapshot"
            fieldConfidence={fieldConfidence}
          >
            <input
              className={I}
              value={p.brokerContactPhoneSnapshot}
              onChange={(e) => p.setBrokerContactPhoneSnapshot(e.target.value)}
              {...bindFieldDoc(
                docFocusForBrokerContactPhone(
                  p.brokerContactPhoneSnapshot,
                  p.brokerContactExtensionSnapshot,
                ),
              )}
            />
          </ParseConfidenceField>
          <div>
            <label className={L}>Extension</label>
            <input
              className={I}
              value={p.brokerContactExtensionSnapshot}
              onChange={(e) => p.setBrokerContactExtensionSnapshot(e.target.value)}
              {...bindFieldDoc(
                docFocusForBrokerContactPhone(
                  p.brokerContactPhoneSnapshot,
                  p.brokerContactExtensionSnapshot,
                ),
              )}
            />
          </div>
          <ParseConfidenceField
            label="Contact email"
            labelClassName={L}
            confidenceKey="broker_contact_email_snapshot"
            fieldConfidence={fieldConfidence}
          >
            <input
              className={I}
              value={p.brokerContactEmailSnapshot}
              onChange={(e) => p.setBrokerContactEmailSnapshot(e.target.value)}
              {...bindFieldDoc(docFocusForBrokerContactEmail(p.brokerContactEmailSnapshot))}
            />
          </ParseConfidenceField>
          <div className="sm:col-span-2">
            <ParseConfidenceField
              label={VISIBLE_BROKER_LOAD_REFERENCE_LABEL}
              labelClassName={L}
              confidenceKey="broker_load_reference"
              fieldConfidence={fieldConfidence}
              manualOverride={manualScalar("brokerLoadReference")}
            >
              <input
                className={I}
                value={p.brokerLoadReference}
                tabIndex={p.verificationTabIndex.get("brokerLoadReference")}
                onChange={(e) => p.setBrokerLoadReference(e.target.value)}
                placeholder="Load number from broker"
                {...bindFieldDoc(docFocusForBrokerLoadReference(p.brokerLoadReference))}
              />
            </ParseConfidenceField>
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
            <ParseConfidenceField
              label=""
              confidenceKey="rate"
              fieldConfidence={fieldConfidence}
              manualOverride={manualScalar("rate")}
              className="shrink-0"
            >
              <input
                className="w-[8.5rem] shrink-0 rounded border border-emerald-900/50 bg-emerald-950/40 px-2.5 py-0.5 text-right font-mono text-sm font-bold text-[var(--trk-success)] placeholder:text-emerald-700/60 focus:border-emerald-600 focus:outline-none focus:ring-1 focus:ring-emerald-600/40"
                inputMode="decimal"
                value={p.rate}
                tabIndex={p.verificationTabIndex.get("rate")}
                onChange={(e) => p.setRate(e.target.value)}
                {...bindFieldDoc(docFocusForMoneyField(p.rate, "linehaul"))}
                aria-label="Linehaul rate"
                placeholder="Linehaul"
                title="Linehaul rate from rate confirmation — edit anytime before save"
              />
            </ParseConfidenceField>
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
          <ParseConfidenceField
            label="Customer rate"
            labelClassName={L}
            confidenceKey="customer_rate"
            fieldConfidence={fieldConfidence}
            manualOverride={manualScalar("customerRate")}
          >
            <input
              className={I}
              inputMode="decimal"
              value={p.customerRate.trim() === "" ? p.rate : p.customerRate}
              onChange={(e) => p.setCustomerRate(e.target.value)}
              title="Defaults to the RC rate if not set separately"
              {...bindFieldDoc(
                docFocusForMoneyField(
                  p.customerRate.trim() === "" ? p.rate : p.customerRate,
                  "customer",
                ),
              )}
            />
          </ParseConfidenceField>
          <ParseConfidenceField
            label="Miles (loaded)"
            labelClassName={L}
            confidenceKey="miles"
            fieldConfidence={fieldConfidence}
            manualOverride={manualScalar("miles")}
          >
            <input
              className={I}
              inputMode="numeric"
              value={p.miles}
              onChange={(e) => p.setMiles(e.target.value)}
              {...bindFieldDoc(docFocusForMoneyField(p.miles, "miles"))}
            />
          </ParseConfidenceField>
        </div>
        </div>
      </section>}

      {/* Assignment — WorkspaceSection: Assignment */}
      {vis("Assignment") && <section className={wsSectionCard} data-editable={editable("Assignment")}>
        <div className={wsSectionHeader}>
          <span className={wsSectionTitle}>Status &amp; assignment</span>
          <span className={wsSectionMeta}>
            {editable("Assignment") && !p.readOnly && !p.activeTripId && p.setDriverId ? "Optional" : "Read-only"}
          </span>
        </div>
        <div className={wsSectionBody}>
        <div className={wsGrid2}>
          <div>
            <label className={L}>Status</label>
            <input className={I} value={p.status || "draft"} readOnly disabled data-testid="load-status-readonly" />
          </div>
          {editable("Assignment") && !p.readOnly && !p.activeTripId && p.setDriverId ? (
            <>
              <div>
                <label className={L}>Driver</label>
                <select
                  className={I}
                  value={p.driverId ?? ""}
                  data-testid="load-driver-select"
                  onChange={(e) => {
                    const v = e.target.value === "" ? null : Number(e.target.value);
                    p.setDriverId?.(v);
                    p.onAssignmentDriverChange?.(v);
                  }}
                >
                  <option value="">— Unassigned —</option>
                  {p.drivers.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.first_name} {d.last_name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className={L}>Truck</label>
                <select
                  className={I}
                  value={p.truckId ?? ""}
                  data-testid="load-truck-select"
                  onChange={(e) => {
                    const v = e.target.value === "" ? null : Number(e.target.value);
                    p.setTruckId?.(v);
                    p.onAssignmentTruckChange?.(v);
                  }}
                >
                  <option value="">— None —</option>
                  {p.trucks.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.unit_number}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className={L}>Trailer</label>
                <select
                  className={I}
                  value={p.trailerAssetId ?? ""}
                  data-testid="load-trailer-select"
                  onChange={(e) => {
                    const v = e.target.value === "" ? null : Number(e.target.value);
                    p.setTrailerAssetId?.(v);
                    p.onAssignmentTrailerChange?.(v);
                  }}
                >
                  <option value="">— None —</option>
                  {p.trailers.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.unit_number}
                      {t.trailer_type ? ` · ${t.trailer_type}` : ""}
                    </option>
                  ))}
                </select>
              </div>
            </>
          ) : (
            <>
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
            </>
          )}
        </div>
        {p.assignmentWarnings && p.assignmentWarnings.length > 0 ? (
          <ul className="mt-2 space-y-0.5 text-[11px] text-amber-600">
            {p.assignmentWarnings.map((w) => (
              <li key={w}>{w.replace(/_/g, " ")}</li>
            ))}
          </ul>
        ) : null}
        <p className="mt-2 text-[11px] leading-snug text-[var(--trk-text-muted)]">
          {editable("Assignment") && !p.readOnly && !p.activeTripId && p.setDriverId
            ? "Optional before Create load — choosing a driver creates a trip automatically. Equipment is stored on the Trip, not the Load."
            : "Driver, truck, and trailer are set on the Trip, not on the Load."}
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
            {stopsRouteConfidence ? (
              <span
                className="inline-flex items-center gap-1 text-[10px] font-medium text-[var(--trk-text-muted)]"
                title={`Route stops (overall): ${parseConfidenceTierLabel(stopsRouteConfidence)}`}
              >
                <span
                  className={`inline-block h-1.5 w-1.5 rounded-full ${
                    stopsRouteConfidence === "high"
                      ? "bg-emerald-500"
                      : stopsRouteConfidence === "medium"
                        ? "bg-amber-500"
                        : "bg-red-500"
                  }`}
                  aria-hidden
                />
                Stops confidence
              </span>
            ) : null}
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
        <div className={`${wsSectionBody} !py-2`}>
        {isIntake && ip?.pickupDeliverySummary ? (
          <p className="mb-1.5 rounded border border-sky-900/40 bg-sky-950/30 px-2 py-1 text-[10px] text-sky-400">
            Intake: {ip.pickupDeliverySummary}
          </p>
        ) : null}
        <div className="@container/stops w-full">
        <div className={`${stopListGridClass()} gap-2`}>
          {p.sortedDraftStops.length === 0 ? (
            <p className="col-span-full py-1.5 text-center text-[11px] text-[var(--trk-text-muted)]">
              No stops yet — add pickup and delivery.
            </p>
          ) : (
            p.sortedDraftStops.map((stop, idx) => {
              const stopType = (stop.stop_type || "").toUpperCase();
              const sectionIndex = p.sortedDraftStops
                .slice(0, idx)
                .filter((s) => (s.stop_type || "").toUpperCase() === stopType).length;
              return (
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
                sectionIndex={sectionIndex}
              />
              );
            })
          )}
        </div>
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
          <ParseConfidenceField
            label="Mode"
            labelClassName={L}
            confidenceKey="mode"
            fieldConfidence={fieldConfidence}
            manualOverride={manualScalar("freightMode")}
          >
            <input
              className={I}
              value={p.freightMode}
              onChange={(e) => p.setFreightMode(e.target.value)}
              {...bindFieldDoc(docFocusForFreightHints(p.freightMode, ["mode", "ftl", "ltl", "freight"]))}
            />
          </ParseConfidenceField>
          <ParseConfidenceField
            label="Equipment type"
            labelClassName={L}
            confidenceKey="equipment_type"
            fieldConfidence={fieldConfidence}
            manualOverride={manualScalar("equipmentType")}
          >
            <input
              className={I}
              value={p.equipmentType}
              tabIndex={p.verificationTabIndex.get("equipmentType")}
              onChange={(e) => p.setEquipmentType(e.target.value)}
              {...bindFieldDoc(
                docFocusForFreightHints(p.equipmentType, ["equipment", "trailer", "van", "reefer", "flatbed"]),
              )}
            />
          </ParseConfidenceField>
          <ParseConfidenceField
            label="Trailer type"
            labelClassName={L}
            confidenceKey="trailer_type"
            fieldConfidence={fieldConfidence}
            manualOverride={manualScalar("trailerType")}
          >
            <input
              className={I}
              value={p.trailerType}
              tabIndex={p.verificationTabIndex.get("trailerType")}
              onChange={(e) => p.setTrailerType(e.target.value)}
              {...bindFieldDoc(
                docFocusForFreightHints(p.trailerType, [
                  "trailer type",
                  "trailer",
                  "equipment",
                  "dry van",
                  "reefer",
                  "flatbed",
                  "step deck",
                  "53",
                ]),
              )}
            />
          </ParseConfidenceField>
          <ParseConfidenceField
            label="Trailer size"
            labelClassName={L}
            confidenceKey="trailer_size"
            fieldConfidence={fieldConfidence}
            manualOverride={manualScalar("trailerSize")}
          >
            <input
              className={I}
              value={p.trailerSize}
              onChange={(e) => p.setTrailerSize(e.target.value)}
              {...bindFieldDoc(docFocusForFreightHints(p.trailerSize, ["trailer size", "length", "53", "48", "ft"]))}
            />
          </ParseConfidenceField>
          <div className="sm:col-span-2">
            <ParseConfidenceField
              label="Commodity"
              labelClassName={L}
              confidenceKey="commodity"
              fieldConfidence={fieldConfidence}
              manualOverride={manualScalar("commodity")}
            >
              <input
                className={I}
                value={p.commodity}
                tabIndex={p.verificationTabIndex.get("commodity")}
                onChange={(e) => p.setCommodity(e.target.value)}
                {...bindFieldDoc(
                  docFocusForFreightHints(p.commodity, [
                    "commodity",
                    "product",
                    "freight",
                    "description",
                    "cargo",
                    "sku",
                  ]),
                )}
              />
            </ParseConfidenceField>
          </div>
          <ParseConfidenceField
            label="Est. weight (lb)"
            labelClassName={L}
            confidenceKey="estimated_weight"
            fieldConfidence={fieldConfidence}
            manualOverride={manualScalar("estimatedWeight")}
          >
            <input
              className={I}
              inputMode="numeric"
              value={p.estimatedWeight}
              tabIndex={p.verificationTabIndex.get("estimatedWeight")}
              onChange={(e) => p.setEstimatedWeight(e.target.value)}
              {...bindFieldDoc(
                docFocusForFreightHints(p.estimatedWeight, [
                  "weight",
                  "lbs",
                  "lb",
                  "pounds",
                  "gross",
                  "net weight",
                ]),
              )}
            />
          </ParseConfidenceField>
          <div>
            <label className={L}>Hazmat</label>
            <select
              className={I}
              value={p.hazmat}
              onChange={(e) => p.setHazmat(e.target.value as "unset" | "yes" | "no")}
              {...bindFieldDoc(docFocusForFreightHints(p.hazmat === "yes" ? "hazmat" : "", ["hazmat", "hazardous", "dg"]))}
            >
              <option value="unset">— Unset —</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </div>
          <ParseConfidenceField
            label="Temperature"
            labelClassName={L}
            confidenceKey="temperature_requirement"
            fieldConfidence={fieldConfidence}
            manualOverride={manualScalar("temperatureRequirement")}
          >
            <input
              className={I}
              value={p.temperatureRequirement}
              onChange={(e) => p.setTemperatureRequirement(e.target.value)}
              {...bindFieldDoc(
                docFocusForFreightHints(p.temperatureRequirement, [
                  "temperature",
                  "temp",
                  "reefer",
                  "frozen",
                  "continuous",
                ]),
              )}
            />
          </ParseConfidenceField>
          <div>
            <label className={L}>Pallet / case count</label>
            <input
              className={I}
              value={p.palletCaseCount}
              onChange={(e) => p.setPalletCaseCount(e.target.value)}
              {...bindFieldDoc(
                docFocusForFreightHints(p.palletCaseCount, ["pallet", "pallets", "case", "cases", "pieces", "qty"]),
              )}
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
