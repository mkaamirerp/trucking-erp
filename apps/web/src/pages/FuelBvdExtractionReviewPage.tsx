import { Navigate, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { getFuelBvdImportRows, type FuelBvdRow } from "../api";
import { OPS } from "../routes";
import FuelBvdProcessingWorkspace from "./fuelBvdReview/FuelBvdProcessingWorkspace";

/** Deep-link / compatibility route for BVD processing workspace. */
export default function FuelBvdExtractionReviewPage() {
  const { importId } = useParams();
  const [rows, setRows] = useState<FuelBvdRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!importId) {
      setError("Missing import id");
      setLoading(false);
      return;
    }
    setLoading(true);
    getFuelBvdImportRows(importId)
      .then(setRows)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [importId]);

  if (!importId) {
    return <div className="p-6 text-sm text-[var(--trk-danger)]">Missing import id</div>;
  }

  if (loading) {
    return <div className="p-6 text-sm text-[var(--trk-text-muted)]">Loading processing workspace…</div>;
  }

  if (error) {
    return <div className="p-6 text-sm text-[var(--trk-danger)]">{error}</div>;
  }

  const sourceReviewed = rows?.some((r) => r.review_status === "SOURCE_REVIEWED");
  if (sourceReviewed) {
    return <Navigate to={OPS.FUEL_BVD_DETAIL(importId)} replace />;
  }

  return <FuelBvdProcessingWorkspace importId={importId} variant="route" />;
}
