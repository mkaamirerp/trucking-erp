/**
 * Condensed load workspace form — post-parse draft layout (Task 16).
 * Same fields and save contracts as LoadWorkspaceForm; layout/density only.
 */
import { useMemo, useState } from "react";
import Button from "@/components/Button";
import OperatorLoadStatusChip from "@/components/OperatorLoadStatusChip";
import BrokerCarrierCombobox from "@/loadWorkspace/BrokerCarrierCombobox";
import {
  compactLoadReferencesForDisplay,
  displayOperationalReferenceLabel,
  VISIBLE_BROKER_LOAD_REFERENCE_LABEL,
  VISIBLE_REFERENCES_SECTION_LABEL,
} from "./loadOperationalReferences";
import {
  docFocusForStopAddress,
  docFocusForStopAppointment,
  docFocusForStopReference,
  formatEquipmentTempChip,
  wsInputClass,
  wsLabelClass,
  wsSectionBody,
  wsSectionCard,
  wsSectionHeader,
  wsSectionMeta,
  wsSectionTitle,
  type WorkspaceSection,
} from "./loadWorkspaceShared";
import { formatDateMonthFirst, parseDateMonthFirst } from "./loadWorkspaceDateFormat";
import type { LoadWorkspaceFormProps } from "./LoadWorkspaceForm";
import { LoadWorkspaceNotesPanel } from "./LoadWorkspaceForm";

const L = wsLabelClass;
const I = wsInputClass;
const wsGrid6 = "grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6";

function CollapseBar({
  title,
  hint,
  expanded,
  onToggle,
}: {
  title: string;
  hint: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className={`${wsSectionHeader} py-2`}>
      <span className="flex min-w-0 flex-wrap items-center gap-2">
        <span className={wsSectionTitle}>{title}</span>
        <span className={wsSectionMeta}>{hint}</span>
      </span>
      <button
        type="button"
        className="shrink-0 text-[11px] font-semibold text-[var(--trk-heading)] hover:underline"
        onClick={onToggle}
      >
        {expanded ? "Hide" : "Show"}
      </button>
    </div>
  );
}

function StopIconButton({
  title,
  disabled,
  onClick,
  children,
}: {
  title: string;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className="inline-flex h-7 w-7 items-center justify-center rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] text-[var(--trk-text-muted)] hover:border-[var(--trk-border-strong)] hover:text-[var(--trk-text)] disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

export function LoadWorkspaceCondensedForm(p: LoadWorkspaceFormProps) {
  const modeCreate = p.mode === "manual";
  const isIntake = p.mode === "intake";
  const ip = p.intakeProposed;

  const vis = (s: WorkspaceSection) => !p.visibleSections || p.visibleSections.includes(s);
  const editable = (s: WorkspaceSection) => !p.editableSections || p.editableSections.includes(s);

  const compactReferences = compactLoadReferencesForDisplay(p.loadReferences ?? [], p.sortedDraftStops);

  const driver = p.driverId != null ? p.drivers.find((d) => d.id === p.driverId) : undefined;
  const driverLabel =
    p.driverId == null ? "—" : driver ? `${driver.first_name} ${driver.last_name}` : `Driver #${p.driverId}`;
  const truck = p.truckId != null ? p.trucks.find((t) => t.id === p.truckId) : undefined;
  const truckLabel = p.truckId == null ? "—" : truck ? truck.unit_number : `Truck #${p.truckId}`;
  const trailer = p.trailerAssetId != null ? p.trailers.find((t) => t.id === p.trailerAssetId) : undefined;
  const trailerLabel =
    p.trailerAssetId == null
      ? "—"
      : trailer
        ? `${trailer.unit_number}${trailer.trailer_type ? ` · ${trailer.trailer_type}` : ""}`
        : `Trailer #${p.trailerAssetId}`;

  const [brokerMore, setBrokerMore] = useState(false);
  const [freightMore, setFreightMore] = useState(false);
  const [stopMore, setStopMore] = useState<Record<string, boolean>>({});
  const notesHaveContent =
    p.internalNotes.trim().length > 0 || p.loadNotes.length > 0 || (p.newNoteBody?.trim().length ?? 0) > 0;
  const [notesExpanded, setNotesExpanded] = useState(notesHaveContent);
  const customsInUse = p.customsBrokerId != null || !!p.customsMessage?.trim();
  const [customsExpanded, setCustomsExpanded] = useState(customsInUse);

  const notesHint = useMemo(() => {
    const noteCount = p.showOperationalNotesTimeline ? p.loadNotes.length : 0;
    const pdfCount = p.workspaceHasRateConfirmationPdf ? 1 : 0;
    return `${noteCount} note${noteCount === 1 ? "" : "s"} · ${pdfCount} PDF`;
  }, [p.loadNotes.length, p.showOperationalNotesTimeline, p.workspaceHasRateConfirmationPdf]);

  const customsHint = customsInUse ? "Customs broker linked" : "not used on this load";

  const operatorStatusLoad =
    p.mode === "detail"
      ? {
          status: p.status,
          active_trip_id: p.activeTripId ?? null,
          open_planned_trip_id: null,
          open_future_movement_plan_id: null,
          custody_owner: null,
        }
      : { status: "draft" as const };

  return (
    <fieldset disabled={!!p.readOnly} className="m-0 min-w-0 border-0 p-0">
      <div className="flex flex-col gap-2.5 pb-3">
        {vis("Parties") && (
          <section className={wsSectionCard} data-editable={editable("Parties")}>
            <div className={`${wsSectionHeader} py-2`}>
              <span className={wsSectionTitle}>Broker &amp; references</span>
              <span className="rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-0.5 text-[10px] font-semibold text-[var(--trk-text-muted)]">
                {formatEquipmentTempChip(p.trailerType, p.equipmentType, p.temperatureRequirement)}
              </span>
            </div>
            <div className={wsSectionBody}>
              <div className={wsGrid6}>
                <div className="xl:col-span-2">
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
                  <label className={L}>Phone</label>
                  <input
                    className={I}
                    value={p.brokerContactPhoneSnapshot}
                    onChange={(e) => p.setBrokerContactPhoneSnapshot(e.target.value)}
                  />
                </div>
                <div>
                  <label className={L}>Ext</label>
                  <input
                    className={I}
                    value={p.brokerContactExtensionSnapshot}
                    onChange={(e) => p.setBrokerContactExtensionSnapshot(e.target.value)}
                  />
                </div>
                <div className="xl:col-span-2">
                  <label className={L}>Contact email</label>
                  <input
                    className={I}
                    value={p.brokerContactEmailSnapshot}
                    onChange={(e) => p.setBrokerContactEmailSnapshot(e.target.value)}
                  />
                </div>
                <div className="xl:col-span-2">
                  <label className={L}>{VISIBLE_BROKER_LOAD_REFERENCE_LABEL}</label>
                  <input
                    className={I}
                    value={p.brokerLoadReference}
                    tabIndex={p.verificationTabIndex.get("brokerLoadReference")}
                    onChange={(e) => p.setBrokerLoadReference(e.target.value)}
                    onFocus={() =>
                      p.focusDoc({
                        tokens: [p.brokerLoadReference, "broker load", "load ref", "ref", "reference", "confirmation", "rate con", "bol"],
                        fallbackToken: "ref",
                      })
                    }
                  />
                </div>
                <div>
                  <label className={L}>Linehaul</label>
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
                  <label className={L}>Miles</label>
                  <input
                    className={I}
                    inputMode="numeric"
                    value={p.miles}
                    onChange={(e) => p.setMiles(e.target.value)}
                  />
                </div>
              </div>
              {compactReferences.length > 0 ? (
                <div className="mt-2">
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
              <button
                type="button"
                className="mt-2 text-[11px] font-semibold text-[var(--trk-heading)] hover:underline"
                onClick={() => setBrokerMore((v) => !v)}
              >
                {brokerMore ? "Less" : "More"}
              </button>
              {brokerMore ? (
                <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
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
                </div>
              ) : null}
            </div>
          </section>
        )}

        {vis("Stops") && (
          <section className={wsSectionCard} data-editable={editable("Stops")}>
            <div className={`${wsSectionHeader} py-2`}>
              <span className="flex flex-wrap items-center gap-2">
                <span className={wsSectionTitle}>Stops</span>
                <span className={wsSectionMeta}>
                  {p.sortedDraftStops.length} stop{p.sortedDraftStops.length === 1 ? "" : "s"}
                </span>
              </span>
              <button
                type="button"
                onClick={p.addStop}
                className="text-[11px] font-semibold text-[var(--trk-heading)] hover:underline"
              >
                + Add stop
              </button>
            </div>
            <div className={wsSectionBody}>
              {isIntake && ip?.pickupDeliverySummary ? (
                <p className="mb-2 rounded border border-sky-900/40 bg-sky-950/30 px-2.5 py-1.5 text-[11px] text-sky-400">
                  Intake context: {ip.pickupDeliverySummary}
                </p>
              ) : null}
              <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
                {p.sortedDraftStops.length === 0 ? (
                  <p className="py-3 text-center text-xs text-[var(--trk-text-muted)] md:col-span-2">
                    No stops yet — add pickup and delivery.
                  </p>
                ) : (
                  p.sortedDraftStops.map((stop, idx) => {
                    const u = (stop.stop_type || "").toUpperCase();
                    const isPu = u === "PICKUP";
                    const isDr = u === "DELIVERY" || u === "DROP";
                    const dateBits = [
                      stop.appointment_date ? formatDateMonthFirst(stop.appointment_date.slice(0, 10)) : null,
                      stop.appointment_time_text,
                    ].filter(Boolean);
                    const moreOpen = !!stopMore[stop._key];
                    return (
                      <div
                        key={stop._key}
                        className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2.5 py-2"
                      >
                        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                          <span
                            className={`inline-block rounded px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
                              isPu
                                ? "border border-emerald-800 bg-emerald-950/50 text-emerald-400"
                                : isDr
                                  ? "border border-sky-800 bg-sky-950/40 text-sky-300"
                                  : "border border-[var(--trk-border)] bg-[var(--trk-surface-2)] text-[var(--trk-text-muted)]"
                            }`}
                          >
                            {idx + 1} · {isPu ? "Pickup" : isDr ? "Delivery" : stop.stop_type || "Stop"}
                          </span>
                          <span className="text-[11px] text-[var(--trk-text-muted)]">{dateBits.join(" · ") || "—"}</span>
                          <div className="flex gap-1">
                            <StopIconButton
                              title="Move up"
                              disabled={idx === 0}
                              onClick={() => p.moveStop(stop._key, -1)}
                            >
                              ↑
                            </StopIconButton>
                            <StopIconButton
                              title="Move down"
                              disabled={idx === p.sortedDraftStops.length - 1}
                              onClick={() => p.moveStop(stop._key, 1)}
                            >
                              ↓
                            </StopIconButton>
                            <StopIconButton title="Remove stop" onClick={() => p.removeStop(stop._key)}>
                              ✕
                            </StopIconButton>
                          </div>
                        </div>
                        <div className="space-y-2">
                          <div>
                            <label className={L}>Facility</label>
                            <input
                              className={I}
                              value={stop.facility_name ?? ""}
                              tabIndex={p.verificationTabIndex.get(`${stop._key}::facility`)}
                              onChange={(e) => p.updateStop(stop._key, { facility_name: e.target.value })}
                              onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                            />
                          </div>
                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto]">
                            <div>
                              <label className={L}>Street</label>
                              <input
                                className={I}
                                value={stop.street ?? ""}
                                tabIndex={p.verificationTabIndex.get(`${stop._key}::street`)}
                                onChange={(e) => p.updateStop(stop._key, { street: e.target.value })}
                                onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                              />
                            </div>
                            <div className="sm:w-28">
                              <label className={L}>Ref #</label>
                              <input
                                className={I}
                                value={stop.reference_number ?? ""}
                                tabIndex={p.verificationTabIndex.get(`${stop._key}::reference`)}
                                onChange={(e) => p.updateStop(stop._key, { reference_number: e.target.value })}
                                onFocus={() => p.focusDoc(docFocusForStopReference(stop))}
                              />
                            </div>
                          </div>
                          <div className="grid grid-cols-3 gap-2">
                            <div>
                              <label className={L}>City</label>
                              <input
                                className={I}
                                value={stop.city ?? ""}
                                onChange={(e) => p.updateStop(stop._key, { city: e.target.value })}
                                onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                              />
                            </div>
                            <div>
                              <label className={L}>State</label>
                              <input
                                className={I}
                                value={stop.state_or_province ?? ""}
                                onChange={(e) => p.updateStop(stop._key, { state_or_province: e.target.value })}
                                onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                              />
                            </div>
                            <div>
                              <label className={L}>Postal</label>
                              <input
                                className={I}
                                value={stop.postal_code ?? ""}
                                onChange={(e) => p.updateStop(stop._key, { postal_code: e.target.value })}
                                onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                              />
                            </div>
                          </div>
                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                            <div>
                              <label className={L}>Date</label>
                              <input
                                className={I}
                                placeholder="MM/DD/YYYY"
                                value={formatDateMonthFirst(
                                  stop.appointment_date && stop.appointment_date.length >= 10
                                    ? stop.appointment_date.slice(0, 10)
                                    : stop.appointment_date,
                                )}
                                tabIndex={p.verificationTabIndex.get(`${stop._key}::apptDate`)}
                                onChange={(e) => {
                                  const parsed = parseDateMonthFirst(e.target.value);
                                  if (parsed) p.updateStop(stop._key, { appointment_date: parsed });
                                  else if (!e.target.value.trim()) p.updateStop(stop._key, { appointment_date: null });
                                }}
                                onBlur={(e) => {
                                  const parsed = parseDateMonthFirst(e.target.value);
                                  if (parsed) p.updateStop(stop._key, { appointment_date: parsed });
                                }}
                                onFocus={() => p.focusDoc(docFocusForStopAppointment(stop))}
                              />
                            </div>
                            <div>
                              <label className={L}>Time window</label>
                              <input
                                className={I}
                                value={stop.appointment_time_text ?? ""}
                                tabIndex={p.verificationTabIndex.get(`${stop._key}::apptTime`)}
                                onChange={(e) => p.updateStop(stop._key, { appointment_time_text: e.target.value })}
                                onFocus={() => p.focusDoc(docFocusForStopAppointment(stop))}
                              />
                            </div>
                            <div>
                              <label className={L}>Appt type</label>
                              <input
                                className={I}
                                value={stop.appointment_type ?? ""}
                                tabIndex={p.verificationTabIndex.get(`${stop._key}::apptType`)}
                                onChange={(e) => p.updateStop(stop._key, { appointment_type: e.target.value })}
                                onFocus={() => p.focusDoc(docFocusForStopAppointment(stop))}
                              />
                            </div>
                          </div>
                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                            <div>
                              <label className={`${L} text-[var(--trk-heading)]`}>Stop notes</label>
                              <textarea
                                className={I}
                                rows={3}
                                data-testid="stop-notes-input"
                                value={stop.notes ?? ""}
                                onChange={(e) => p.updateStop(stop._key, { notes: e.target.value })}
                              />
                            </div>
                            <div>
                              <label className={`${L} text-[var(--trk-heading)]`}>Commodity notes</label>
                              <textarea
                                className={I}
                                rows={3}
                                data-testid="commodity-notes-input"
                                value={stop.commodity_notes ?? ""}
                                onChange={(e) => p.updateStop(stop._key, { commodity_notes: e.target.value })}
                              />
                            </div>
                          </div>
                          <button
                            type="button"
                            className="text-[11px] font-semibold text-[var(--trk-heading)] hover:underline"
                            onClick={() =>
                              setStopMore((prev) => ({ ...prev, [stop._key]: !prev[stop._key] }))
                            }
                          >
                            {moreOpen ? "Less" : "More"}
                          </button>
                          {moreOpen ? (
                            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
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
                              <div>
                                <label className={L}>Country</label>
                                <input
                                  className={I}
                                  maxLength={2}
                                  value={stop.country ?? ""}
                                  onChange={(e) => p.updateStop(stop._key, { country: e.target.value })}
                                  onFocus={() => p.focusDoc(docFocusForStopAddress(stop))}
                                />
                              </div>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
              {modeCreate ? (
                <p className="mt-2 text-[10px] text-[var(--trk-text-muted)]">Create saves this full stop list.</p>
              ) : null}
            </div>
          </section>
        )}

        {vis("Equipment") && (
          <section className={wsSectionCard} data-editable={editable("Equipment")}>
            <div className={`${wsSectionHeader} py-2`}>
              <span className={wsSectionTitle}>Freight &amp; equipment</span>
            </div>
            <div className={wsSectionBody}>
              <div className={wsGrid6}>
                <div className="xl:col-span-2">
                  <label className={L}>Commodity</label>
                  <input
                    className={I}
                    value={p.commodity}
                    tabIndex={p.verificationTabIndex.get("commodity")}
                    onChange={(e) => p.setCommodity(e.target.value)}
                    onFocus={() =>
                      p.focusDoc({
                        tokens: [p.commodity, "commodity", "product", "freight", "description", "cargo"],
                        fallbackToken: "commodity",
                      })
                    }
                  />
                </div>
                <div>
                  <label className={L}>Weight (lb)</label>
                  <input
                    className={I}
                    inputMode="numeric"
                    value={p.estimatedWeight}
                    tabIndex={p.verificationTabIndex.get("estimatedWeight")}
                    onChange={(e) => p.setEstimatedWeight(e.target.value)}
                    onFocus={() =>
                      p.focusDoc({
                        tokens: [p.estimatedWeight, "weight", "lbs", "lb", "pounds"],
                        fallbackToken: "weight",
                      })
                    }
                  />
                </div>
                <div>
                  <label className={L}>Pallets</label>
                  <input
                    className={I}
                    value={p.palletCaseCount}
                    onChange={(e) => p.setPalletCaseCount(e.target.value)}
                  />
                </div>
                <div>
                  <label className={L}>Equipment</label>
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
                  <label className={L}>Size</label>
                  <input
                    className={I}
                    value={p.trailerSize}
                    onChange={(e) => p.setTrailerSize(e.target.value)}
                  />
                </div>
                <div>
                  <label className={L}>Temp</label>
                  <input
                    className={I}
                    value={p.temperatureRequirement}
                    onChange={(e) => p.setTemperatureRequirement(e.target.value)}
                  />
                </div>
                <div>
                  <label className={L}>Hazmat</label>
                  <select
                    className={I}
                    value={p.hazmat}
                    onChange={(e) => p.setHazmat(e.target.value as "unset" | "yes" | "no")}
                  >
                    <option value="unset">—</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </div>
              </div>
              <button
                type="button"
                className="mt-2 text-[11px] font-semibold text-[var(--trk-heading)] hover:underline"
                onClick={() => setFreightMore((v) => !v)}
              >
                {freightMore ? "Less" : "More"}
              </button>
              {freightMore ? (
                <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <div>
                    <label className={L}>Mode</label>
                    <input className={I} value={p.freightMode} onChange={(e) => p.setFreightMode(e.target.value)} />
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
                          tokens: [p.trailerType, "trailer type", "dry van", "reefer", "flatbed"],
                          fallbackToken: "trailer",
                        })
                      }
                    />
                  </div>
                </div>
              ) : null}
            </div>
          </section>
        )}

        {vis("Assignment") && (
          <section className={wsSectionCard} data-editable={editable("Assignment")}>
            <div className={`${wsSectionHeader} py-2`}>
              <span className={wsSectionTitle}>Status &amp; assignment</span>
              <span className={wsSectionMeta}>Assigned from Dispatch</span>
            </div>
            <div className={wsSectionBody}>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <div>
                  <label className={L}>Status</label>
                  <div className="pt-1" data-testid="load-status-readonly">
                    <OperatorLoadStatusChip load={operatorStatusLoad} />
                  </div>
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
            </div>
          </section>
        )}

        {vis("Documents") && (
          <section className={wsSectionCard} data-editable={editable("Documents")}>
            <CollapseBar
              title="Customs"
              hint={customsHint}
              expanded={customsExpanded}
              onToggle={() => setCustomsExpanded((v) => !v)}
            />
            {customsExpanded ? (
              <div className={wsSectionBody}>
                {p.customsMessage ? <p className="mb-3 text-sm text-[var(--trk-text)]">{p.customsMessage}</p> : null}
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
                </div>
                {!modeCreate && p.onConfirmSnapshot ? (
                  <div className="mt-3">
                    <Button
                      variant="primary"
                      disabled={p.saving || !p.customsBrokerId || p.customsBrokerLocked}
                      onClick={p.onConfirmSnapshot}
                    >
                      Confirm document snapshot
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        )}

        {vis("Notes") && p.renderNotes !== false ? (
          <section className={wsSectionCard} data-editable={editable("Notes")}>
            <CollapseBar
              title="Notes & documents"
              hint={notesHint}
              expanded={notesExpanded}
              onToggle={() => setNotesExpanded((v) => !v)}
            />
            {notesExpanded ? (
              <LoadWorkspaceNotesPanel
                embedded
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
          </section>
        ) : null}

        <p className="text-center text-[10px] text-[var(--trk-text-muted)]">UI bundle {__UI_BUILD_ID__}</p>
      </div>
    </fieldset>
  );
}
