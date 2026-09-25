import * as pdfjs from "pdfjs-dist";
import PdfjsWorker from "pdfjs-dist/build/pdf.worker.min.mjs?worker";
import { fetchWithTenant } from "../../api";

/** Vite bundles the worker — avoids brittle runtime `import(workerSrc)` against /assets/*.mjs */
if (typeof window !== "undefined" && !pdfjs.GlobalWorkerOptions.workerPort) {
  pdfjs.GlobalWorkerOptions.workerPort = new PdfjsWorker();
}

export async function loadBvdPdfDocument(documentUrl: string) {
  const res = await fetchWithTenant(documentUrl);
  if (!res.ok) {
    throw new Error(`Could not load PDF (${res.status})`);
  }
  const data = await res.arrayBuffer();
  return pdfjs.getDocument({ data }).promise;
}
