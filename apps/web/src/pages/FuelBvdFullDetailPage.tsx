import { useParams } from "react-router-dom";
import FuelBvdProcessedRecordView from "./fuelBvdReview/FuelBvdProcessedRecordView";

/** Deep-link / compatibility route for processed BVD record. */
export default function FuelBvdFullDetailPage() {
  const { importId } = useParams<{ importId: string }>();

  if (!importId) {
    return <div className="p-6 text-sm text-[var(--trk-danger)]">Missing import</div>;
  }

  return (
    <div data-testid="fuel-bvd-detail-page">
      <FuelBvdProcessedRecordView importId={importId} variant="route" />
    </div>
  );
}
