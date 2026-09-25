import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadFuelBvdPdf } from "../api";
import { OPS } from "../routes";

export default function FuelBvdUploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Choose a BVD PDF file.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const out = await uploadFuelBvdPdf(file);
      navigate(OPS.FUEL_BVD_REVIEW(out.import_id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg p-6">
      <h1 className="text-lg font-semibold text-gray-900">BVD PDF upload (Implementation 1)</h1>
      <p className="mt-1 text-sm text-gray-600">
        Digital BVD PDF only. Extracts exact source fields into <code className="text-xs">fuel_bvd</code> for
        side-by-side review.
      </p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <input
          type="file"
          accept="application/pdf,.pdf"
          onChange={(ev) => setFile(ev.target.files?.[0] ?? null)}
          className="block w-full text-sm"
        />
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        <button
          type="submit"
          disabled={busy || !file}
          className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Uploading…" : "Upload and extract"}
        </button>
      </form>
    </div>
  );
}
