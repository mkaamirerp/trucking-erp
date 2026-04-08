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
  labelClass,
  inputClass,
  grid2,
  sectionTitleClass,
  docFocusForStopAddress,
  docFocusForStopAppointment,
  docFocusForStopReference,
  type DraftStop,
  type LoadWorkspaceMode,
} from "./loadWorkspaceShared";

export type LoadWorkspaceFormProps = {
  mode: LoadWorkspaceMode;
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
  customsBrokerId: number | null;
  internalNotes: string;
  setInternalNotes: (v: string) => void;
  draftStops: DraftStop[];
  sortedDraftStops: DraftStop[];
  updateStop: (key: string, patch: Partial<DraftStop>) => void;
  removeStop: (key: string) => void;
  addStop: () => void;
  moveStop: (key: string, dir: -1 | 1) => void;
};

export function LoadWorkspaceForm(p: LoadWorkspaceFormProps) {
  const modeCreate = p.mode === "manual";

  return (
    <div className="space-y-5">

      {/* ── 1. BROKER & CONTACT ── */}
      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className={sectionTitleClass}>Broker & contact</h2>
        <div className={grid2}>
          <div>
            <label className={labelClass}>Broker</label>
            <select
              className={inputClass}
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
            <label className={labelClass}>Contact</label>
            <select
              className={inputClass}
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
            <label className={labelClass}>Broker name</label>
            <input
              className={inputClass}
              value={p.brokerNameSnapshot}
              onChange={(e) => p.setBrokerNameSnapshot(e.target.value)}
              placeholder="As shown on the rate confirmation"
            />
          </div>
          <div>
            <label className={labelClass}>Contact name</label>
            <input
              className={inputClass}
              value={p.brokerContactNameSnapshot}
              onChange={(e) => p.setBrokerContactNameSnapshot(e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Contact phone</label>
            <input
              className={inputClass}
              value={p.brokerContactPhoneSnapshot}
              onChange={(e) => p.setBrokerContactPhoneSnapshot(e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Extension</label>
            <input
              className={inputClass}
              value={p.brokerContactExtensionSnapshot}
              onChange={(e) => p.setBrokerContactExtensionSnapshot(e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Contact email</label>
            <input
              className={inputClass}
              value={p.brokerContactEmailSnapshot}
              onChange={(e) => p.setBrokerContactEmailSnapshot(e.target.value)}
            />
          </div>
          <div className="sm:col-span-2">
            <label className={labelClass}>Broker load reference</label>
            <input
              className={inputClass}
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
      </section>

      {/* ── 2. STOPS ── */}
      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className={sectionTitleClass}>Stops</h2>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-gray-500 flex-1">
            {modeCreate
              ? "Saving creates the load with this full stop list."
              : "Saving replaces the full ordered stop list on the server (full-array PATCH)."}
          </p>
          <Button variant="secondary" type="button" onClick={p.addStop}>
            Add stop
          </Button>
        </div>
        <div className="space-y-4">
          {p.sortedDraftStops.length === 0 ? (
            <p className="text-sm text-gray-600">No stops — add at least pickup and delivery for most workflows.</p>
          ) : (
            p.sortedDraftStops.map((stop, idx) => (
              <div
                key={stop._key}
                className="rounded-lg border border-gray-200 bg-gray-50/80 p-4 shadow-inner"
              >
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                    Stop {idx + 1}
                    {stop.id <= 0 ? (
                      <span className="ml-2 font-normal normal-case text-gray-400">· new</span>
                    ) : null}
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
                <div className={grid2}>
                  <div>
                    <label className={labelClass}>Stop type</label>
                    <select
                      className={inputClass}
                      value={stop.stop_type}
                      onChange={(e) => p.updateStop(stop._key, { stop_type: e.target.value })}
                    >
                      <option value="PICKUP">PICKUP</option>
                      <option value="DROP">DROP</option>
                      <option value="DELIVERY">DELIVERY</option>
                    </select>
                  </div>
                  <div>
                    <label className={labelClass}>Sequence</label>
                    <input
                      className={inputClass}
                      inputMode="numeric"
                      value={String(stop.sequence ?? 0)}
                      onChange={(e) =>
                        p.updateStop(stop._key, { sequence: parseInt(e.target.value, 10) || 0 })
                      }
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className={labelClass}>Facility name</label>
                    <input
                      className={inputClass}
                      value={stop.facility_name ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::facility`)}
                      onChange={(e) => p.updateStop(stop._key, { facility_name: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className={labelClass}>Street</label>
                    <input
                      className={inputClass}
                      value={stop.street ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::street`)}
                      onChange={(e) => p.updateStop(stop._key, { street: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                    />
                  </div>
                  <div>
                    <label className={labelClass}>City</label>
                    <input
                      className={inputClass}
                      value={stop.city ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::city`)}
                      onChange={(e) => p.updateStop(stop._key, { city: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                    />
                  </div>
                  <div>
                    <label className={labelClass}>State / province</label>
                    <input
                      className={inputClass}
                      value={stop.state_or_province ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::state`)}
                      onChange={(e) => p.updateStop(stop._key, { state_or_province: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                    />
                  </div>
                  <div>
                    <label className={labelClass}>Postal code</label>
                    <input
                      className={inputClass}
                      value={stop.postal_code ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::postal`)}
                      onChange={(e) => p.updateStop(stop._key, { postal_code: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                    />
                  </div>
                  <div>
                    <label className={labelClass}>Country</label>
                    <input
                      className={inputClass}
                      maxLength={2}
                      value={stop.country ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::country`)}
                      onChange={(e) => p.updateStop(stop._key, { country: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                    />
                  </div>
                  <div>
                    <label className={labelClass}>Reference number</label>
                    <input
                      className={inputClass}
                      value={stop.reference_number ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::reference`)}
                      onChange={(e) => p.updateStop(stop._key, { reference_number: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopReference(stop))}
                    />
                  </div>
                  <div>
                    <label className={labelClass}>Appointment type</label>
                    <input
                      className={inputClass}
                      value={stop.appointment_type ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::apptType`)}
                      onChange={(e) => p.updateStop(stop._key, { appointment_type: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAppointment(stop))}
                    />
                  </div>
                  <div>
                    <label className={labelClass}>Appointment date</label>
                    <input
                      className={inputClass}
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
                    <label className={labelClass}>Appointment time (text)</label>
                    <input
                      className={inputClass}
                      value={stop.appointment_time_text ?? ""}
                      tabIndex={p.verificationTabIndex.get(`${stop._key}::apptTime`)}
                      onChange={(e) => p.updateStop(stop._key, { appointment_time_text: e.target.value })}
                      onFocus={() => p.focusDoc(docFocusForStopAppointment(stop))}
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className={labelClass}>Stop notes</label>
                    <textarea
                      className={inputClass}
                      rows={2}
                      value={stop.notes ?? ""}
                      onChange={(e) => p.updateStop(stop._key, { notes: e.target.value })}
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className={labelClass}>Commodity notes</label>
                    <textarea
                      className={inputClass}
                      rows={2}
                      value={stop.commodity_notes ?? ""}
                      onChange={(e) => p.updateStop(stop._key, { commodity_notes: e.target.value })}
                    />
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {/* ── 3. FREIGHT & EQUIPMENT ── */}
      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className={sectionTitleClass}>Freight & equipment</h2>
        <div className={grid2}>
          <div>
            <label className={labelClass}>Mode</label>
            <input
              className={inputClass}
              value={p.freightMode}
              onChange={(e) => p.setFreightMode(e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Equipment type</label>
            <input
              className={inputClass}
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
            <label className={labelClass}>Trailer type</label>
            <input
              className={inputClass}
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
            <label className={labelClass}>Trailer size</label>
            <input
              className={inputClass}
              value={p.trailerSize}
              onChange={(e) => p.setTrailerSize(e.target.value)}
            />
          </div>
          <div className="sm:col-span-2">
            <label className={labelClass}>Commodity</label>
            <input
              className={inputClass}
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
            <label className={labelClass}>Est. weight (lb)</label>
            <input
              className={inputClass}
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
            <label className={labelClass}>Hazmat</label>
            <select
              className={inputClass}
              value={p.hazmat}
              onChange={(e) => p.setHazmat(e.target.value as "unset" | "yes" | "no")}
            >
              <option value="unset">— Unset —</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </div>
          <div>
            <label className={labelClass}>Temperature</label>
            <input
              className={inputClass}
              value={p.temperatureRequirement}
              onChange={(e) => p.setTemperatureRequirement(e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Pallet / case count</label>
            <input
              className={inputClass}
              value={p.palletCaseCount}
              onChange={(e) => p.setPalletCaseCount(e.target.value)}
            />
          </div>
        </div>
      </section>

      {/* ── 4. ASSIGNMENT ── */}
      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className={sectionTitleClass}>Assignment</h2>
        <div className={grid2}>
          <div>
            <label className={labelClass}>Driver</label>
            <select
              className={inputClass}
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
            <label className={labelClass}>Truck</label>
            <select
              className={inputClass}
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
            <label className={labelClass}>Trailer</label>
            <select
              className={inputClass}
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
      </section>

      {/* ── 5. RATES & IDENTITY ── */}
      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className={sectionTitleClass}>Rates & identity</h2>
        <div className={grid2}>
          <div>
            <label className={labelClass}>Status</label>
            <select
              className={inputClass}
              value={p.status}
              onChange={(e) => p.setStatus(e.target.value)}
            >
              {LOAD_STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass}>Load number</label>
            <input
              className={inputClass}
              value={p.loadNumber}
              tabIndex={p.verificationTabIndex.get("loadNumber")}
              onChange={(e) => p.setLoadNumber(e.target.value)}
              placeholder="Internal load #"
            />
          </div>
          <div>
            <label className={labelClass}>Linehaul rate</label>
            <input
              className={inputClass}
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
            <label className={labelClass}>Customer rate</label>
            <input
              className={inputClass}
              inputMode="decimal"
              value={p.customerRate}
              onChange={(e) => p.setCustomerRate(e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Miles (loaded)</label>
            <input
              className={inputClass}
              inputMode="numeric"
              value={p.miles}
              onChange={(e) => p.setMiles(e.target.value)}
            />
          </div>
        </div>
      </section>

      {/* ── 6. CUSTOMS ── */}
      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className={sectionTitleClass}>Customs</h2>
        {p.customsMessage ? <p className="mb-3 text-sm text-gray-700">{p.customsMessage}</p> : null}
        <div className="space-y-4">
          <div>
            <label className={labelClass}>Customs broker</label>
            <select
              className={inputClass}
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
              <p className="mt-1 text-xs text-gray-500">
                Stored on the new load. Document snapshot confirmation is available after you create the load.
              </p>
            ) : !p.customsBrokerLocked ? (
              <p className="mt-1 text-xs text-amber-800">
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
              <p className="text-xs text-gray-600">Customs broker link is frozen after snapshot confirm.</p>
            ) : (
              <p className="text-xs text-gray-500">
                Link a customs broker, then confirm to freeze customs snapshot fields on this load.
              </p>
            ))}
        </div>
      </section>

      {/* ── 7. DOCUMENTS & NOTES ── */}
      <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className={sectionTitleClass}>Documents & notes</h2>
        <div>
          <label className={labelClass}>Internal notes (load)</label>
          <textarea
            className={inputClass}
            rows={6}
            value={p.internalNotes}
            onChange={(e) => p.setInternalNotes(e.target.value)}
            placeholder="e.g. rate confirmation excerpt, intake text…"
          />
        </div>
        {p.showOperationalNotesTimeline ? (
          <div className="mt-6 border-t border-gray-100 pt-4">
            <p className={labelClass}>Operational notes (timeline)</p>
            <ul className="max-h-48 space-y-2 overflow-y-auto rounded-md border border-gray-100 bg-gray-50 p-3 text-sm">
              {p.loadNotes.length === 0 ? (
                <li className="text-gray-500">No notes yet.</li>
              ) : (
                p.loadNotes.map((n) => (
                  <li key={n.id} className="border-b border-gray-200 pb-2 last:border-0">
                    <p className="text-gray-900">{n.body}</p>
                    <p className="text-xs text-gray-500">{new Date(n.created_at).toLocaleString()}</p>
                  </li>
                ))
              )}
            </ul>
            <div className="mt-3 flex gap-2">
              <input
                className={inputClass}
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
      </section>

      <p className="text-center text-[10px] text-gray-400">UI bundle {__UI_BUILD_ID__}</p>
    </div>
  );
}
