import { useEffect, useState } from "react";
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
  type CustomsBroker,
} from "@/api";

export default function LoadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [load, setLoad] = useState<Load | null>(null);
  const [brokers, setBrokers] = useState<CustomsBroker[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customsMessage, setCustomsMessage] = useState<string | null>(null);

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Load {load.load_number}</h1>
          <p className="text-sm text-gray-600">Load details</p>
        </div>
        <Button variant="secondary" onClick={() => navigate("/loads")}>
          Back to Loads
        </Button>
      </div>

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

      <Card title="Details">
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-sm font-medium text-gray-500">Status</dt>
            <dd className="mt-1 text-sm">
              <StatusBadge status={load.status} />
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Pickup Location</dt>
            <dd className="mt-1 text-sm text-gray-900">{load.pickup_location || "—"}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Delivery Location</dt>
            <dd className="mt-1 text-sm text-gray-900">{load.delivery_location || "—"}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Pickup Date</dt>
            <dd className="mt-1 text-sm text-gray-900">{load.pickup_date || "—"}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Delivery Date</dt>
            <dd className="mt-1 text-sm text-gray-900">{load.delivery_date || "—"}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Driver</dt>
            <dd className="mt-1 text-sm text-gray-900">
              {load.driver
                ? `${load.driver.first_name} ${load.driver.last_name}`
                : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Broker</dt>
            <dd className="mt-1 text-sm text-gray-900">{load.broker?.name || "—"}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Rate</dt>
            <dd className="mt-1 text-sm text-gray-900">
              {load.rate != null ? `$${load.rate}` : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Miles</dt>
            <dd className="mt-1 text-sm text-gray-900">{load.miles ?? "—"}</dd>
          </div>
        </dl>
      </Card>
    </div>
  );
}
