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

const recordOverlays: Record<string, ComponentType<ProcessedFuelRecordOverlayProps>> = {
  BVD: FuelBvdProcessedRecordView,
  NATIONWIDE: FuelNationwideProcessedRecordView,
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
