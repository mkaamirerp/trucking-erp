/**
 * Canonical editable load form — shared by LoadWorkspace (manual / detail / intake modes).
 */
import Button from "@/components/Button";
import type {
  Broker,
  BrokerContact,
  CustomsBroker,
  Driver,
  LoadNote,
  Trailer,
  Truck,
} from "@/api";
import {
  LOAD_STATUSES,
  isLoadStatusOptionDisabled,
  docFocusForStopAddress,
  docFocusForStopAppointment,
  docFocusForStopReference,
  wsGrid2,
  wsGrid3,
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

const L = wsLabelClass;
const I = wsInputClass;

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
  status: string;
  setStatus: (v: string) => void;
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
  driverId: number | null;
  setDriverId: (v: number | null) => void;
  truckId: number | null;
  setTruckId: (v: number | null) => void;
  trailerAssetId: number | null;
  setTrailerAssetId: (v: number | null) => void;
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

  return (
    <fieldset disabled={!!p.readOnly} className="m-0 min-w-0 border-0 p-0">
    <div className="flex flex-col gap-2.5 pb-4">
      {/* Broker — WorkspaceSection: Parties */}
      {vis("Parties") && <section className={wsSectionCard} data-editable={editable("Parties")}>
        <div className={wsSectionHeader}>
          <span className={wsSectionTitle}>Broker</span>
          {!modeCreate && p.brokerNameSnapshot.trim() ? (
            <span className="text-[10px] font-medium text-sky-400">Snapshot · {p.brokerNameSnapshot.trim()}</span>
          ) : null}
        </div>
        <div className={wsSectionBody}>
        <div className={wsGrid2}>
          <div>
            <label className={L}>Broker</label>
            <select
              className={I}
              value={p.brokerId ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                p.setBrokerId(v === "" ? null : Number(v));
                p.setBrokerContactId(null);
              }}
            >
              <option value="">— Select broker —</option>
              {p.freightBrokers.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </div>
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
          <div className="sm:col-span-2">
            <label className={L}>Broker name</label>
            <input
              className={I}
              style={prefill(ip?.brokerNameSnapshot ?? null)}
              value={p.brokerNameSnapshot}
              onChange={(e) => p.setBrokerNameSnapshot(e.target.value)}
              placeholder="As shown on the rate confirmation"
            />
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
            <label className={L}>Broker load reference</label>
            <input
              className={I}
              value={p.brokerLoadReference}
              tabIndex={p.verificationTabIndex.get("brokerLoadReference")}
              onChange={(e) => p.setBrokerLoadReference(e.target.value)}
              placeholder="Rate con # / load ref from broker"
              onFocus={() =>
                p.focusDoc({
                  tokens: [p.brokerLoadReference, "broker load", "load ref", "ref", "reference", "confirmation", "rate con", "bol"],
                  fallbackToken: "ref",
                })
              }
            />
          </div>
        </div>
        </div>
      </section>}

      {/* Stops — WorkspaceSection: Stops */}
      {vis("Stops") && <section className={wsSectionCard} data-editable={editable("Stops")}>
        <div className={wsSectionHeader}>
          <span className={wsSectionTitle}>Stops</span>
          <span className={wsSectionMeta}>
            {p.sortedDraftStops.length} stop{p.sortedDraftStops.length === 1 ? "" : "s"}
          </span>
        </div>
        <div className={wsSectionBody}>
        <p className="mb-2 text-[11px] text-[var(--trk-text-muted)]">
          {modeCreate
            ? "Create saves this full stop list."
            : "Save replaces the ordered stop list on the server (full-array PATCH)."}
        </p>
        {isIntake && ip?.pickupDeliverySummary ? (
          <p className="mb-2 rounded border border-sky-900/40 bg-sky-950/30 px-2.5 py-1.5 text-[11px] text-sky-400">
            Intake context: {ip.pickupDeliverySummary}
          </p>
        ) : null}
        <div className="space-y-2">
          {p.sortedDraftStops.length === 0 ? (
            <p className="py-4 text-center text-xs text-[var(--trk-text-muted)]">No stops yet — add pickup and delivery.</p>
          ) : (
            p.sortedDraftStops.map((stop, idx) => {
              const u = (stop.stop_type || "").toUpperCase();
              const isPu = u === "PICKUP";
              const isDr = u === "DELIVERY" || u === "DROP";
              const edge = isPu ? "border-l-emerald-500" : isDr ? "border-l-rose-500" : "border-l-slate-300";
              return (
              <div
                key={stop._key}
                className={`rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface-2)] py-2.5 pl-2.5 pr-3 shadow-sm border-l-[3px] ${edge}`}
              >
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <span
                    className={`inline-block rounded px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
                      isPu ? "bg-emerald-900/40 text-emerald-400" : isDr ? "bg-rose-900/40 text-rose-400" : "bg-[var(--trk-border)] text-[var(--trk-text-muted)]"
                    }`}
                  >
                    {stop.stop_type || "STOP"} · {idx + 1}
                    {stop.id <= 0 ? <span className="ml-1 font-normal normal-case text-[var(--trk-text-muted)]">· new</span> : null}
                  </span>
                  <div className="flex flex-wrap gap-1">
                    <Button
                      variant="secondary"
                      type="button"
                      className="!px-2 !py-1 text-xs"
                      onClick={() => p.moveStop(stop._key, -1)}
                      disabled={idx === 0}
                    >
                      Up
                    </Button>
                    <Button
                      variant="secondary"
                      type="button"
                      className="!px-2 !py-1 text-xs"
                      onClick={() => p.moveStop(stop._key, 1)}
                      disabled={idx === p.sortedDraftStops.length - 1}
                    >
                      Down
                    </Button>
                    <Button
                      variant="secondary"
                      type="button"
                      className="!px-2 !py-1 text-xs text-red-700"
                      onClick={() => p.removeStop(stop._key)}
                    >
                      Remove
                    </Button>
                  </div>
                </div>
                <div className={wsGrid2}>
                  <div>
                    <label className={L}>Stop type</label>
                    <select
                      className={I}
                      value={stop.stop_type}
                      onChange={(e) => p.updateStop(stop._key, { stop_type: e.target.value })}
                    >
                      <option value="PICKUP">PICKUP</option>
                      <option value="DROP">DROP</option>
                      <option value="DELIVERY">DELIVERY</option>
                    </select>
                  </div>
                  <div>
                    <label className={L}>Sequence</label>
                    <input
                      className={I}
                      inputMode="numeric"
                      value={String(stop.sequence ?? 0)}
                      onChange={(e) =>
                        p.updateStop(stop._key, { sequence: parseInt(e.target.value, 10) || 0 })
                      }
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className={L}>Facility name</label>
                    <input
                      className={I}
                      value={stop.facility_name ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::facility`)}
                      onChange={(e) => p.updateStop(stop._key, { facility_name: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className={L}>Street</label>
                    <input
                      className={I}
                      value={stop.street ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::street`)}
                      onChange={(e) => p.updateStop(stop._key, { street: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                    />
                  </div>
                  <div>
                    <label className={L}>City</label>
                    <input
                      className={I}
                      value={stop.city ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::city`)}
                      onChange={(e) => p.updateStop(stop._key, { city: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                    />
                  </div>
                  <div>
                    <label className={L}>State / province</label>
                    <input
                      className={I}
                      value={stop.state_or_province ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::state`)}
                      onChange={(e) => p.updateStop(stop._key, { state_or_province: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                    />
                  </div>
                  <div>
                    <label className={L}>Postal code</label>
                    <input
                      className={I}
                      value={stop.postal_code ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::postal`)}
                      onChange={(e) => p.updateStop(stop._key, { postal_code: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                    />
                  </div>
                  <div>
                    <label className={L}>Country</label>
                    <input
                      className={I}
                      maxLength={2}
                      value={stop.country ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::country`)}
                      onChange={(e) => p.updateStop(stop._key, { country: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                    />
                  </div>
                  <div>
                    <label className={L}>Reference number</label>
                    <input
                      className={I}
                      value={stop.reference_number ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::reference`)}
                      onChange={(e) => p.updateStop(stop._key, { reference_number: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopReference(stop))}
                    />
                  </div>
                  <div>
                    <label className={L}>Appointment type</label>
                    <input
                      className={I}
                      value={stop.appointment_type ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::apptType`)}
                      onChange={(e) => p.updateStop(stop._key, { appointment_type: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAppointment(stop))}
                    />
                  </div>
                  <div>
                    <label className={L}>Appointment date</label>
                    <input
                      className={I}
                      type="date"
                      value={
                        stop.appointment_date && stop.appointment_date.length >= 10
                          ? stop.appointment_date.slice(0, 10)
                          : (stop.appointment_date ?? "")
                      }
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::apptDate`)}
                      onChange={(e) => p.updateStop(stop._key, { appointment_date: e.target.value || null })}
                      onFocus={() => p.focusDoc(docFocusForStopAppointment(stop))}
                    />
                  </div>
                  <div>
                    <label className={L}>Appointment time (text)</label>
                    <input
                      className={I}
                      value={stop.appointment_time_text ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::apptTime`)}
                      onChange={(e) => p.updateStop(stop._key, { appointment_time_text: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAppointment(stop))}
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className={L}>Stop notes</label>
                    <textarea
                      className={I}
                      rows={2}
                      value={stop.notes ?? ""}
                      onChange={(e) => p.updateStop(stop._key, { notes: e.target.value })}
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className={L}>Commodity notes</label>
                    <textarea
                      className={I}
                      rows={2}
                      value={stop.commodity_notes ?? ""}
                      onChange={(e) => p.updateStop(stop._key, { commodity_notes: e.target.value })}
                    />
                  </div>
                </div>
              </div>
              );
            })
          )}
        </div>
        <button
          type="button"
          onClick={p.addStop}
          className="mt-2 w-full rounded-md border border-dashed border-[var(--trk-border)] bg-transparent py-2 text-center text-[11px] font-medium text-[var(--trk-text-muted)] transition hover:border-amber-400 hover:text-amber-400"
        >
          + Add stop
        </button>
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

      {/* Financials — WorkspaceSection: Equipment (financial/cargo parameters travel together) */}
      {vis("Equipment") && <section className={wsSectionCard} data-editable={editable("Equipment")}>
        <div className={wsSectionHeader}>
          <span className={wsSectionTitle}>Financials</span>
        </div>
        <div className={wsSectionBody}>
        <div className={wsGrid3}>
          <div>
            <label className={L}>Load number</label>
            <input
              className={I}
              value={p.loadNumber}
              tabIndex={p.verificationTabIndex.get("loadNumber")}
              onChange={(e) => p.setLoadNumber(e.target.value)}
              placeholder="Internal load #"
            />
          </div>
          <div>
            <label className={L}>Linehaul rate</label>
            <input
              className={I}
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
            />
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
          <span className={wsSectionTitle}>Assignment & status</span>
          <span className={wsSectionMeta}>Planning & load record — trip workspace owns movement assignment</span>
        </div>
        <div className={wsSectionBody}>
        <div className={wsGrid2}>
          <div>
            <label className={L}>Status</label>
            <select
              className={I}
              value={p.status}
              onChange={(e) => p.setStatus(e.target.value)}
            >
              {LOAD_STATUSES.map((s) => {
                const legacyOperationalBlocked = isLoadStatusOptionDisabled(s, p.status);
                return (
                  <option key={s} value={s} disabled={legacyOperationalBlocked}>
                    {legacyOperationalBlocked ? `${s} (legacy — use Trip workspace)` : s}
                  </option>
                );
              })}
            </select>
            <p className="mt-1.5 text-[10px] leading-snug text-[var(--trk-text-muted)]">
              Use <span className="font-medium text-[var(--trk-text)]">Mark ready</span> in the toolbar for validated
              draft → ready (broker, reference, stops). Legacy operational statuses in the list remain for historical
              compatibility. Driver/truck/trailer commitment lives on the{" "}
              <span className="font-medium text-[var(--trk-text)]">trip workspace</span> — not via setting{" "}
              <span className="font-mono text-[var(--trk-text-muted)]">Load.status</span> to an operational value.
            </p>
          </div>
          <div>
            <label className={L}>Driver</label>
            <select
              className={I}
              value={p.driverId ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                p.setDriverId(v === "" ? null : Number(v));
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
              onChange={(e) => {
                const v = e.target.value;
                p.setTruckId(v === "" ? null : Number(v));
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
              onChange={(e) => {
                const v = e.target.value;
                p.setTrailerAssetId(v === "" ? null : Number(v));
              }}
            >
              <option value="">— None —</option>
              {p.trailers.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.unit_number}{t.trailer_type ? ` · ${t.trailer_type}` : ""}
                </option>
              ))}
            </select>
          </div>
        </div>
        {p.activeTripId != null && p.activeTripId > 0 ? (
          <p className="mt-3 text-[10px] leading-snug text-[var(--trk-text-muted)]">
            This load is on a trip — use{" "}
            <span className="font-medium text-[var(--trk-text)]">View / Assign on Trip</span> in the header to set driver,
            truck, and trailer.
          </p>
        ) : null}
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
      {vis("Notes") && <section className={wsSectionCard} data-editable={editable("Notes")}>
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
            <div className="mt-2 flex flex-wrap gap-2">
              <input
                className={`${I} min-w-[12rem] flex-1`}
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
      </section>}

      <p className="text-center text-[10px] text-[var(--trk-text-muted)]">UI bundle {__UI_BUILD_ID__}</p>
    </div>
    </fieldset>
  );
}
