import * as pdfjs from "pdfjs-dist";
import { fetchWithTenant } from "../../api";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export async function loadBvdPdfDocument(documentUrl: string) {
  const res = await fetchWithTenant(documentUrl);
  if (!res.ok) {
    throw new Error(`Could not load PDF (${res.status})`);
  }
  const data = await res.arrayBuffer();
  return pdfjs.getDocument({ data }).promise;
}
