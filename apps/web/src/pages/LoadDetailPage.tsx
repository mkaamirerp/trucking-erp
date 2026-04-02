import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Card from "@/components/Card";
import Button from "@/components/Button";
import StatusBadge from "@/components/StatusBadge";
import { getLoad, Load } from "@/api";

export default function LoadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [load, setLoad] = useState<Load | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getLoad(Number(id))
      .then(setLoad)
      .catch((e) => setError(e?.message || "Failed to load load"))
      .finally(() => setLoading(false));
  }, [id]);

  if (!id) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">Invalid load ID</p>
      </div>
    );
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">
            Load {load.load_number}
          </h1>
          <p className="text-sm text-gray-600">Load details</p>
        </div>
        <Button variant="secondary" onClick={() => navigate("/loads")}>
          Back to Loads
        </Button>
      </div>

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
            <dd className="mt-1 text-sm text-gray-900">
              {load.pickup_location || "—"}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Delivery Location</dt>
            <dd className="mt-1 text-sm text-gray-900">
              {load.delivery_location || "—"}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Pickup Date</dt>
            <dd className="mt-1 text-sm text-gray-900">
              {load.pickup_date || "—"}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Delivery Date</dt>
            <dd className="mt-1 text-sm text-gray-900">
              {load.delivery_date || "—"}
            </dd>
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
            <dd className="mt-1 text-sm text-gray-900">
              {load.broker?.name || "—"}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Rate</dt>
            <dd className="mt-1 text-sm text-gray-900">
              {load.rate != null ? `$${load.rate}` : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Miles</dt>
            <dd className="mt-1 text-sm text-gray-900">
              {load.miles ?? "—"}
            </dd>
          </div>
        </dl>
      </Card>
    </div>
  );
}
