import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Card from "@/components/Card";
import Button from "@/components/Button";
import StatusBadge from "@/components/StatusBadge";
import {
  getLoad,
  listCustomsBrokers,
  updateLoad,
  confirmLoadDocumentSnapshot,
  type Load,
  type LoadStop,
  type CustomsBroker,
} from "@/api";
import { formatRouteFromStops, sortedStops as sortStops } from "@/utils/loadStops";

type DrawerId = "freight" | "rules" | "docs";

function LoadDrawerShell({
  title,
  open,
  onClose,
  children,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  if (!open) return null;
  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-40 bg-black/30"
        aria-label="Close panel"
        onClick={onClose}
      />
      <aside
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-gray-200 bg-white shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby={`drawer-h-${title.replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "")}`}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h2
            id={`drawer-h-${title.replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "")}`}
            className="text-sm font-semibold text-gray-900"
          >
            {title}
          </h2>
          <button type="button" className="text-sm font-medium text-indigo-600 hover:text-indigo-800" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 text-sm text-gray-800">{children}</div>
      </aside>
    </>
  );
}

function formatStopAddress(s: LoadStop): string {
  const line1 = [s.facility_name, s.street].filter(Boolean).join(" · ") || "";
  const cityLine = [s.city, s.state_or_province, s.postal_code].filter(Boolean).join(", ");
  const parts = [line1, cityLine, s.country].filter(Boolean);
  return parts.join(" · ") || "—";
}

export default function LoadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [load, setLoad] = useState<Load | null>(null);
  const [brokers, setBrokers] = useState<CustomsBroker[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customsMessage, setCustomsMessage] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<DrawerId | null>(null);

  useEffect(() => {
    if (!id) return;
    const loadId = Number(id);
    setLoading(true);
    setError(null);
    Promise.all([
      getLoad(loadId),
      listCustomsBrokers({ page: 1, size: 200, include_inactive: false }),
    ])
      .then(([l, paged]) => {
        setLoad(l);
        setBrokers(paged.items || []);
      })
      .catch((e) => setError(e?.message || "Failed to load"))
      .finally(() => setLoading(false));
  }, [id]);

  const stops = load ? sortStops(load.stops) : [];

  /**
   * TEMP (Step 1 only): pickup # / delivery # are not yet first-class load fields.
   * Derive display labels from the first PICKUP and last DROP stop `reference_number` until a dedicated API exists.
   */
  const { pickupNumberDerived, deliveryNumberDerived } = useMemo(() => {
    const norm = (t: string | undefined) => (t || "").toUpperCase();
    const pickups = stops.filter((s) => norm(s.stop_type) === "PICKUP");
    const drops = stops.filter((s) => {
      const n = norm(s.stop_type);
      return n === "DROP" || n === "DELIVERY";
    });
    return {
      pickupNumberDerived: pickups[0]?.reference_number?.trim() || null,
      deliveryNumberDerived: drops.length ? drops[drops.length - 1]?.reference_number?.trim() || null : null,
    };
  }, [stops]);

  if (!id) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">Invalid load ID</p>
      </div>
    );
  }

  const confirmed = Boolean(load?.document_snapshot_confirmed_at);

  async function onCustomsBrokerChange(ev: React.ChangeEvent<HTMLSelectElement>) {
    if (!load || confirmed) return;
    const v = ev.target.value;
    const customs_broker_id = v === "" ? null : Number(v);
    setSaving(true);
    setCustomsMessage(null);
    try {
      const updated = await updateLoad(load.id, { customs_broker_id });
      setLoad(updated);
      setCustomsMessage("Customs broker updated.");
    } catch (e: unknown) {
      setCustomsMessage((e as Error)?.message || "Could not update customs broker");
    } finally {
      setSaving(false);
    }
  }

  async function onConfirmSnapshot() {
    if (!load) return;
    setSaving(true);
    setCustomsMessage(null);
    try {
      const updated = await confirmLoadDocumentSnapshot(load.id);
      setLoad(updated);
      setCustomsMessage("Document snapshot confirmed.");
    } catch (e: unknown) {
      setCustomsMessage((e as Error)?.message || "Confirm failed");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="p-4 text-sm text-gray-600">Loading...</div>;
  if (error)
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">{error}</p>
        <Button variant="secondary" onClick={() => navigate("/loads")} className="mt-2">
          Back to Loads
        </Button>
      </div>
    );
  if (!load)
    return (
      <div className="p-4">
        <p className="text-sm text-gray-600">Load not found</p>
        <Button variant="secondary" onClick={() => navigate("/loads")} className="mt-2">
          Back to Loads
        </Button>
      </div>
    );

  const snap = load.customs_snapshot;

  const brokerDisplayName = load.broker?.name || load.broker_name_snapshot || "—";
  const brokerContactName =
    load.broker_contact?.name || load.broker_contact_name_snapshot || null;
  const brokerContactPhone =
    load.broker_contact?.phone || load.broker_contact_phone_snapshot || null;
  const brokerContactEmail =
    load.broker_contact?.email || load.broker_contact_email_snapshot || null;

  const hasEquipmentAssignment = Boolean(load.truck || load.trailer);
  const routeSubtitle = formatRouteFromStops(load.stops);

  return (
    <div className="space-y-6">
      <LoadDrawerShell
        title="Freight & equipment"
        open={drawer === "freight"}
        onClose={() => setDrawer(null)}
      >
        <dl className="space-y-3">
          <DetailRow label="Mode" value={load.mode} />
          <DetailRow label="Equipment type" value={load.equipment_type} />
          <DetailRow label="Commodity" value={load.commodity} />
          <DetailRow
            label="Est. weight (lb)"
            value={load.estimated_weight != null ? String(load.estimated_weight) : null}
          />
          <DetailRow label="Hazmat" value={load.hazmat_flag === true ? "Yes" : load.hazmat_flag === false ? "No" : null} />
          <DetailRow label="Temperature" value={load.temperature_requirement} />
          <DetailRow label="Pallet / case count" value={load.pallet_case_count} />
          <DetailRow label="Trailer type (load)" value={load.trailer_type} />
          <DetailRow label="Trailer size" value={load.trailer_size} />
          <DetailRow label="Assigned truck" value={load.truck ? load.truck.unit_number : null} />
          <DetailRow
            label="Assigned trailer"
            value={
              load.trailer
                ? [load.trailer.unit_number, load.trailer.trailer_type].filter(Boolean).join(" · ") || null
                : null
            }
          />
        </dl>
      </LoadDrawerShell>

      <LoadDrawerShell title="Rules & alerts" open={drawer === "rules"} onClose={() => setDrawer(null)}>
        <p className="text-gray-600">
          Load-level rules and alerts summaries will appear here after a structured rules service exists. No alerts are
          wired for this load yet.
        </p>
      </LoadDrawerShell>

      <LoadDrawerShell
        title="Documents & references"
        open={drawer === "docs"}
        onClose={() => setDrawer(null)}
      >
        <p className="text-gray-600">
          Document list, uploads, and extra reference links will be added in a later step. This panel is a placeholder only.
        </p>
      </LoadDrawerShell>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Load {load.load_number}</h1>
          <p className="text-sm text-gray-600">Dispatch detail · route from stops</p>
          {routeSubtitle !== "—" && (
            <p className="mt-1 text-sm font-medium text-gray-800">{routeSubtitle}</p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" type="button" onClick={() => setDrawer("freight")}>
            Freight / equipment
          </Button>
          <Button variant="secondary" type="button" onClick={() => setDrawer("rules")}>
            Rules / alerts
          </Button>
          <Button variant="secondary" type="button" onClick={() => setDrawer("docs")}>
            Documents
          </Button>
          <Button variant="secondary" onClick={() => navigate("/loads")}>
            Back to Loads
          </Button>
        </div>
      </div>

      {load.internal_notes?.trim() ? (
        <Card title="Rate confirmation (PDF excerpt)">
          <p className="mb-3 text-xs text-gray-600">
            Text extracted from the rate confirmation PDF on intake (e.g. TQL digital rate cons), up to ~4,000
            characters. Total rate, miles, and commodity on the load may be prefilled when the parser finds them —
            always verify against this excerpt.
          </p>
          <pre className="max-h-[28rem] overflow-auto rounded-md border border-gray-200 bg-gray-50 p-3 text-xs leading-snug whitespace-pre-wrap break-words font-mono text-gray-900">
            {load.internal_notes.trim()}
          </pre>
        </Card>
      ) : null}

      <Card title="1. Who is involved">
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <dt className="text-sm font-medium text-gray-500">Driver</dt>
            <dd className="mt-1 text-sm text-gray-900">
              {load.driver ? (
                <>
                  {load.driver.first_name} {load.driver.last_name}
                  {(load.driver.phone || load.driver.email) && (
                    <span className="mt-1 block text-gray-600">
                      {[load.driver.phone, load.driver.email].filter(Boolean).join(" · ") || null}
                    </span>
                  )}
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Broker</dt>
            <dd className="mt-1 text-sm text-gray-900">{brokerDisplayName}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Broker contact</dt>
            <dd className="mt-1 text-sm text-gray-900">
              {brokerContactName || brokerContactPhone || brokerContactEmail ? (
                <>
                  {brokerContactName || "—"}
                  {(brokerContactPhone || brokerContactEmail) && (
                    <span className="mt-1 block text-gray-600">
                      {[brokerContactPhone, brokerContactEmail].filter(Boolean).join(" · ")}
                    </span>
                  )}
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-sm font-medium text-gray-500">Dispatcher (contact)</dt>
            <dd className="mt-1 text-sm italic text-gray-500">Not available on this load yet (placeholder).</dd>
          </div>
          <div className="sm:col-span-2 rounded-md border border-amber-100 bg-amber-50/80 px-3 py-2 text-sm text-amber-950">
            <p className="font-medium">Assigned tractor / trailer</p>
            <p className="mt-1 text-amber-900/90">
              {hasEquipmentAssignment ? (
                <>
                  {load.truck && <span>Truck {load.truck.unit_number}</span>}
                  {load.truck && load.trailer && <span> · </span>}
                  {load.trailer && (
                    <span>
                      Trailer {load.trailer.unit_number}
                      {load.trailer.trailer_type ? ` (${load.trailer.trailer_type})` : ""}
                    </span>
                  )}
                </>
              ) : (
                "—"
              )}
            </p>
            <p className="mt-2 text-xs text-amber-800/90">
              Shown from current dispatch assignment only. There is no separate &quot;carrier&quot; company record tied to this
              view.
            </p>
          </div>
        </dl>
      </Card>

      <Card title="2. Load identity">
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-sm font-medium text-gray-500">Status</dt>
            <dd className="mt-1 text-sm">
              <StatusBadge status={load.status} />
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Load number</dt>
            <dd className="mt-1 text-sm text-gray-900">{load.load_number}</dd>
          </div>
          <div className="sm:col-span-2 text-xs text-gray-500">
            Customer PO and extra shipper refs are not modeled yet — use broker load reference, stop refs, or the PDF
            excerpt above.
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Broker load reference</dt>
            <dd className="mt-1 text-sm text-gray-900">{load.broker_load_reference || "—"}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Pickup number</dt>
            <dd className="mt-1 text-sm text-gray-900">{pickupNumberDerived || "—"}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Delivery number</dt>
            <dd className="mt-1 text-sm text-gray-900">{deliveryNumberDerived || "—"}</dd>
          </div>
          <div className="sm:col-span-2 text-xs text-gray-500">
            Pickup and delivery numbers above are derived from the first pickup and last drop stop reference (temporary
            UI only).
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Linehaul rate</dt>
            <dd className="mt-1 text-sm text-gray-900">{load.rate != null ? `$${load.rate}` : "—"}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Customer rate</dt>
            <dd className="mt-1 text-sm text-gray-900">{load.customer_rate != null ? `$${load.customer_rate}` : "—"}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Miles</dt>
            <dd className="mt-1 text-sm text-gray-900">{load.miles ?? "—"}</dd>
          </div>
        </dl>
      </Card>

      <Card title="3. Stops">
        {stops.length === 0 ? (
          <p className="text-sm text-gray-600">No stops on this load yet.</p>
        ) : (
          <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200">
            {stops.map((stop) => (
              <li key={stop.id} className="p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium text-gray-900">
                    Stop {stop.sequence}: {stop.stop_type}
                  </span>
                  {stop.reference_number && (
                    <span className="text-xs text-gray-500">Ref {stop.reference_number}</span>
                  )}
                </div>
                <p className="mt-2 text-sm text-gray-800">{formatStopAddress(stop)}</p>
                <dl className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-xs font-medium text-gray-500">Appointment type</dt>
                    <dd>{stop.appointment_type || "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-gray-500">Appointment date</dt>
                    <dd>{stop.appointment_date || "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-gray-500">Appointment time</dt>
                    <dd>{stop.appointment_time_text || "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-gray-500">Scheduled at</dt>
                    <dd>
                      {stop.scheduled_at
                        ? new Date(stop.scheduled_at).toLocaleString(undefined, {
                            dateStyle: "short",
                            timeStyle: "short",
                          })
                        : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-gray-500">Appointment end</dt>
                    <dd className="italic text-gray-500">Placeholder — not available yet.</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-gray-500">Facility contact</dt>
                    <dd className="italic text-gray-500">Placeholder — not available yet.</dd>
                  </div>
                </dl>
                {(stop.notes || stop.commodity_notes) && (
                  <div className="mt-2 text-xs text-gray-600">
                    {stop.notes && <p className="whitespace-pre-wrap">Notes: {stop.notes}</p>}
                    {stop.commodity_notes && (
                      <p className="mt-1 whitespace-pre-wrap">Commodity: {stop.commodity_notes}</p>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Customs broker & document snapshot">
        {customsMessage && (
          <p className="mb-3 text-sm text-gray-700">{customsMessage}</p>
        )}
        {confirmed && snap ? (
          <div className="space-y-2 text-sm">
            <p className="font-medium text-gray-800">Frozen customs snapshot (read-only)</p>
            <p className="text-gray-500">
              Confirmed {new Date(snap.confirmed_at).toLocaleString()} · Version{" "}
              {load.document_snapshot_version ?? "—"}
            </p>
            <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <div>
                <dt className="text-xs font-medium text-gray-500">Legal name</dt>
                <dd>{snap.legal_name_snapshot || "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500">Primary phone</dt>
                <dd>{snap.phone_primary_snapshot || "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500">Fax</dt>
                <dd>{snap.fax_snapshot || "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500">Email</dt>
                <dd>{snap.generic_email_snapshot || "—"}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs font-medium text-gray-500">Address</dt>
                <dd>
                  {[snap.address_line1_snapshot, snap.address_line2_snapshot, snap.city_snapshot]
                    .filter(Boolean)
                    .join(", ") || "—"}
                </dd>
              </div>
            </dl>
            {load.customs_broker && (
              <p className="mt-3 text-xs text-gray-500">
                Current master record: {load.customs_broker.legal_name} (edits do not change the frozen
                snapshot)
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-3 text-sm">
            <div>
              <label className="block text-xs font-medium text-gray-600">Linked customs broker</label>
              <select
                className="mt-1 w-full max-w-md rounded border border-gray-300 px-2 py-1.5 text-sm"
                disabled={saving || confirmed}
                value={load.customs_broker_id ?? ""}
                onChange={onCustomsBrokerChange}
              >
                <option value="">— None —</option>
                {brokers.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.legal_name}
                  </option>
                ))}
              </select>
              {load.customs_broker && (
                <p className="mt-1 text-xs text-gray-500">
                  Selected: {load.customs_broker.legal_name}
                  {load.customs_broker.phone_primary ? ` · ${load.customs_broker.phone_primary}` : ""}
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="primary"
                disabled={saving || !load.customs_broker_id}
                onClick={onConfirmSnapshot}
              >
                Confirm document snapshot
              </Button>
            </div>
            <p className="text-xs text-gray-500">
              Link a customs broker, then confirm to freeze customs fields on this load. After confirm,
              the broker link cannot be changed here.
            </p>
          </div>
        )}
      </Card>

      <p className="pt-2 text-center text-[10px] text-gray-400" title="Confirm you are running the latest deployed frontend bundle">
        UI bundle {__UI_BUILD_ID__}
      </p>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs font-medium text-gray-500">{label}</dt>
      <dd className="mt-0.5 text-gray-900">{value && String(value).trim() !== "" ? value : "—"}</dd>
    </div>
  );
}
