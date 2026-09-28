import type { FuelBvdRow } from "../../api";
import {
  extractedValue,
  isFieldCorrected,
  reviewedValue,
  type DraftMap,
} from "./bvdReviewValues";

type Props = {
  row: FuelBvdRow;
  field: string;
  drafts?: DraftMap;
  presentation: "processing-review" | "full-stored-detail";
};

export default function BvdCorrectedFieldCell({
  row,
  field,
  drafts = {},
  presentation,
}: Props) {
  const extracted = extractedValue(row, field);
  const effective = reviewedValue(row, field, drafts);
  const corrected = isFieldCorrected(row, field, drafts);
  const display = effective || extracted || "—";

  if (!corrected) {
    return <>{display}</>;
  }

  if (presentation === "full-stored-detail") {
    return (
      <div className="bvd-corrected-cell bvd-corrected-cell--detail">
        <span className="bvd-corrected-cell__effective">{display}</span>
        <span className="bvd-corrected-cell__badge">Corrected during review</span>
        <span className="bvd-corrected-cell__extracted">Extracted: {extracted || "—"}</span>
      </div>
    );
  }

  return (
    <span
      className="bvd-corrected-cell bvd-corrected-cell--inline"
      title={`Extracted: ${extracted || "—"}\nReviewed: ${effective}`}
    >
      {display}
      <span className="bvd-corrected-cell__mark" aria-label="Corrected"> *</span>
    </span>
  );
}
