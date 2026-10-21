import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Button from "@/components/Button";
import {
  cancelFutureMovementPlan,
  getFutureMovementPlan,
  listFutureMovementPlans,
  type FutureMovementPlan,
} from "@/api";
import { OPS } from "@/routes";

export default function FutureMovementPlansPage() {
  const { planId } = useParams<{ planId?: string }>();
  const navigate = useNavigate();
  const [list, setList] = useState<FutureMovementPlan[]>([]);
  const [detail, setDetail] = useState<FutureMovementPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshList = useCallback(() => {
    setLoading(true);
    listFutureMovementPlans({ status: "unassigned", page: 1, size: 100 })
      .then((res) => setList(res.items || []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!planId) {
      refreshList();
      return;
    }
    setLoading(true);
    getFutureMovementPlan(Number(planId))
      .then(setDetail)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [planId, refreshList]);

  const onCancel = async () => {
    if (!detail) return;
    setBusy(true);
    try {
      await cancelFutureMovementPlan(detail.id, detail.concurrency_version);
      navigate("/dispatch/future-plans");
      refreshList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancel failed");
    } finally {
      setBusy(false);
    }
  };

  const onOpenTrip = async () => {
    if (!detail?.converted_trip_id) return;
    navigate(OPS.TRIP_DETAIL(detail.converted_trip_id));
  };

  if (planId && detail) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-4">
        <Link to="/dispatch/future-plans" className="text-xs text-[var(--trk-text-muted)] hover:underline">
          ← Unassigned plans
        </Link>
        <h1 className="text-lg font-semibold">Future movement plan #{detail.id}</h1>
        <p className="text-sm text-[var(--trk-text-muted)]">Status: {detail.status}</p>
        <ul className="text-sm">
          {detail.lines.map((ln) => (
            <li key={ln.id ?? ln.load_id}>
              Load {ln.load_number || ln.load_id}
              {ln.inbound_trip_id ? ` (inbound trip ${ln.inbound_trip_id})` : ""}
            </li>
          ))}
        </ul>
        {detail.converted_trip_id ? (
          <Button type="button" onClick={() => void onOpenTrip()}>
            Open trip {detail.converted_trip_number || detail.converted_trip_id}
          </Button>
        ) : (
          <Button type="button" variant="secondary" disabled={busy} onClick={() => void onCancel()}>
            Cancel plan
          </Button>
        )}
        {error ? <p className="text-xs text-red-700">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-4">
      <h1 className="text-lg font-semibold">Unassigned future movement plans</h1>
      <p className="text-sm text-[var(--trk-text-muted)]">
        Pre-trip follow-up dispatch. These plans do not have trip numbers until converted.
      </p>
      {loading ? <p className="text-sm">Loading…</p> : null}
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <ul className="divide-y divide-[var(--trk-border)] rounded border border-[var(--trk-border)]">
        {list.map((p) => (
          <li key={p.id} className="flex items-center justify-between px-3 py-2 text-sm">
            <span>
              Plan #{p.id} · {p.lines.length} load(s)
              {p.planned_start_at ? ` · ${new Date(p.planned_start_at).toLocaleString()}` : ""}
            </span>
            <Link to={`/dispatch/future-plans/${p.id}`} className="font-semibold hover:underline">
              Edit →
            </Link>
          </li>
        ))}
        {!loading && list.length === 0 ? (
          <li className="px-3 py-4 text-sm text-[var(--trk-text-muted)]">No unassigned plans.</li>
        ) : null}
      </ul>
    </div>
  );
}
