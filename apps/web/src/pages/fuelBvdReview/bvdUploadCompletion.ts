import { OPS } from "../../routes";

export const BVD_UPLOAD_COMPLETED_PARAM = "bvdCompleted";
export const BVD_UPLOAD_INVOICE_PARAM = "invoice";

export function buildBvdUploadCompletedPath(invoiceNumber?: string | null): string {
  const q = new URLSearchParams({ [BVD_UPLOAD_COMPLETED_PARAM]: "1" });
  if (invoiceNumber?.trim()) {
    q.set(BVD_UPLOAD_INVOICE_PARAM, invoiceNumber.trim());
  }
  return `${OPS.FUEL_BVD_UPLOAD}?${q.toString()}`;
}

export function readBvdUploadCompletion(search: string): { invoiceNumber?: string } | null {
  const params = new URLSearchParams(search);
  if (params.get(BVD_UPLOAD_COMPLETED_PARAM) !== "1") {
    return null;
  }
  const invoice = params.get(BVD_UPLOAD_INVOICE_PARAM);
  return invoice ? { invoiceNumber: invoice } : {};
}
