import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getFuelBvdUploadErrorDisplay, type FuelBvdUploadErrorDisplay, uploadFuelBvdPdf } from "../api";
import { OPS } from "../routes";

function FuelBvdUploadAlert({ title, message }: FuelBvdUploadErrorDisplay) {
  return (
    <div
      role="alert"
      className="flex gap-3 rounded-xl border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-4 py-3"
    >
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--trk-heading)]/15"
        aria-hidden
      >
        <svg
          viewBox="0 0 24 24"
          className="h-5 w-5 text-[var(--trk-warning)]"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6M12 18v-2M12 13v-2" />
        </svg>
      </div>
      <div className="min-w-0 pt-0.5">
        <p className="text-sm font-semibold text-[var(--trk-text)]">{title}</p>
        <p className="mt-1 text-sm leading-relaxed text-[var(--trk-text-muted)]">
          {message.split("\n").map((line, i) => (
            <span key={i} className="block">
              {line}
            </span>
          ))}
        </p>
      </div>
    </div>
  );
}

export default function FuelBvdUploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<FuelBvdUploadErrorDisplay | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setError({ title: "No file selected", message: "Choose a BVD PDF file before uploading." });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const out = await uploadFuelBvdPdf(file);
      navigate(OPS.FUEL_BVD_REVIEW(out.import_id));
    } catch (err: unknown) {
      setError(getFuelBvdUploadErrorDisplay(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-6">
      <h1 className="text-lg font-semibold text-[var(--trk-text)]">BVD PDF upload (Implementation 1)</h1>
      <p className="mt-1 text-sm text-[var(--trk-text-muted)]">
        Digital BVD PDF only. Extracts exact source fields into{" "}
        <code className="rounded bg-[var(--trk-surface-2)] px-1 py-0.5 text-xs text-[var(--trk-accent)]">
          fuel_bvd
        </code>{" "}
        for side-by-side review.
      </p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <input
          type="file"
          accept="application/pdf,.pdf"
          onChange={(ev) => {
            setFile(ev.target.files?.[0] ?? null);
            setError(null);
          }}
          className="block w-full text-sm text-[var(--trk-text-muted)] file:mr-3 file:rounded-md file:border file:border-[var(--trk-border)] file:bg-[var(--trk-surface)] file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-[var(--trk-text)] hover:file:bg-[var(--trk-surface-2)]"
        />
        {error ? <FuelBvdUploadAlert title={error.title} message={error.message} /> : null}
        <button
          type="submit"
          disabled={busy || !file}
          className="rounded-md bg-[var(--trk-btn-primary)] px-4 py-2 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
        >
          {busy ? "Uploading…" : "Upload and extract"}
        </button>
      </form>
    </div>
  );
}
