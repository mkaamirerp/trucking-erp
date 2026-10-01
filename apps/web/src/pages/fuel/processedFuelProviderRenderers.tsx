import type { ComponentType } from "react";
import FuelBvdProcessedRecordView from "../fuelBvdReview/FuelBvdProcessedRecordView";
import FuelNationwideProcessedRecordView from "../fuelNationwideReview/FuelNationwideProcessedRecordView";
import BvdProcessedEvidencePanel from "./BvdProcessedEvidencePanel";
import NationwideProcessedEvidencePanel from "./NationwideProcessedEvidencePanel";

export type ProcessedFuelEvidencePanelProps = {
  batchId: number;
  sourceImportRef: string | null;
  invoiceNumber: string;
  onOpenFull?: () => void;
};

export type ProcessedFuelRecordOverlayProps = {
  sourceImportRef: string;
  variant: "overlay";
  onClose: () => void;
};

const evidenceRenderers: Record<string, ComponentType<ProcessedFuelEvidencePanelProps>> = {
  BVD: BvdProcessedEvidencePanel,
  NATIONWIDE: NationwideProcessedEvidencePanel,
};

function FuelBvdProcessedRecordOverlay({
  sourceImportRef,
  onClose,
}: ProcessedFuelRecordOverlayProps) {
  return (
    <FuelBvdProcessedRecordView importId={sourceImportRef} variant="overlay" onClose={onClose} />
  );
}

function FuelNationwideProcessedRecordOverlay({
  sourceImportRef,
  onClose,
}: ProcessedFuelRecordOverlayProps) {
  return (
    <FuelNationwideProcessedRecordView
      importId={sourceImportRef}
      variant="overlay"
      onClose={onClose}
    />
  );
}

const recordOverlays: Record<string, ComponentType<ProcessedFuelRecordOverlayProps>> = {
  BVD: FuelBvdProcessedRecordOverlay,
  NATIONWIDE: FuelNationwideProcessedRecordOverlay,
};

export function getProcessedFuelEvidenceRenderer(
  providerCode: string,
): ComponentType<ProcessedFuelEvidencePanelProps> | null {
  return evidenceRenderers[providerCode] ?? null;
}

export function getProcessedFuelRecordOverlay(
  providerCode: string,
): ComponentType<ProcessedFuelRecordOverlayProps> | null {
  return recordOverlays[providerCode] ?? null;
}
