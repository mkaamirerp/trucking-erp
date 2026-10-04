import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createFuelManualEntryStage,
  discardFuelManualEntryStage,
  patchFuelManualEntryStage,
  processFuelManualEntryStage,
  uploadFuelManualEntryReceipt,
  type FuelManualEntryStage,
} from "../../api";
import FuelFullScreenOverlay from "./FuelFullScreenOverlay";

type EntryTab = "manual" | "receipt";

type DraftForm = {
  transaction_date: string;
  unit_number: string;
  product: string;
  total_amount: string;
  currency: string;
  transaction_time: string;
  driver_name: string;
  merchant_site: string;
  merchant_network: string;
  city: string;
  province_state: string;
  quantity: string;
  quantity_unit: string;
  unit_price: string;
  pre_tax_amount: string;
  gst_amount: string;
  hst_amount: string;
  pst_amount: string;
  qst_amount: string;
  card_or_account_id: string;
  receipt_ticket_number: string;
  authorization_number: string;
  pump: string;
  invoice_reference: string;
  trailer_number: string;
  notes: string;
};

const EMPTY_FORM: DraftForm = {
  transaction_date: "",
  unit_number: "",
  product: "",
  total_amount: "",
  currency: "",
  transaction_time: "",
  driver_name: "",
  merchant_site: "",
  merchant_network: "",
  city: "",
  province_state: "",
  quantity: "",
  quantity_unit: "",
  unit_price: "",
  pre_tax_amount: "",
  gst_amount: "",
  hst_amount: "",
  pst_amount: "",
  qst_amount: "",
  card_or_account_id: "",
  receipt_ticket_number: "",
  authorization_number: "",
  pump: "",
  invoice_reference: "",
  trailer_number: "",
  notes: "",
};

function draftToForm(draft: Record<string, unknown>): DraftForm {
  const str = (key: keyof DraftForm) => {
    const v = draft[key];
    if (v == null) return "";
    return String(v);
  };
  return {
    ...EMPTY_FORM,
    transaction_date: str("transaction_date"),
    unit_number: str("unit_number"),
    product: str("product"),
    total_amount: str("total_amount"),
    currency: str("currency"),
    transaction_time: str("transaction_time"),
    driver_name: str("driver_name"),
    merchant_site: str("merchant_site"),
    merchant_network: str("merchant_network"),
    city: str("city"),
    province_state: str("province_state"),
    quantity: str("quantity"),
    quantity_unit: str("quantity_unit"),
    unit_price: str("unit_price"),
    pre_tax_amount: str("pre_tax_amount"),
    gst_amount: str("gst_amount"),
    hst_amount: str("hst_amount"),
    pst_amount: str("pst_amount"),
    qst_amount: str("qst_amount"),
    card_or_account_id: str("card_or_account_id"),
    receipt_ticket_number: str("receipt_ticket_number"),
    authorization_number: str("authorization_number"),
    pump: str("pump"),
    invoice_reference: str("invoice_reference"),
    trailer_number: str("trailer_number"),
    notes: str("notes"),
  };
}

function formToDraftPatch(form: DraftForm): Record<string, string> {
  const out: Record<string, string> = {};
  (Object.keys(form) as (keyof DraftForm)[]).forEach((key) => {
    const trimmed = form[key].trim();
    if (trimmed) out[key] = trimmed;
  });
  return out;
}

type Props = {
  open: boolean;
  onClose: () => void;
  onProcessed: (payload: { importId: string; invoiceNumber?: string }) => void;
};

export default function FuelManualEntryModal({ open, onClose, onProcessed }: Props) {
  const receiptInputRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<EntryTab>("manual");
  const [stage, setStage] = useState<FuelManualEntryStage | null>(null);
  const [form, setForm] = useState<DraftForm>(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewReasons, setReviewReasons] = useState<string[]>([]);

  const requiresReview = stage?.requires_review || reviewReasons.length > 0;

  const resetLocal = useCallback(() => {
    setStage(null);
    setForm(EMPTY_FORM);
    setError(null);
    setReviewReasons([]);
    setTab("manual");
  }, []);

  useEffect(() => {
    if (!open) resetLocal();
  }, [open, resetLocal]);

  const applyStage = useCallback((next: FuelManualEntryStage) => {
    setStage(next);
    setForm(draftToForm(next.draft ?? {}));
    setReviewReasons(
      Array.isArray(next.draft?.review_reasons)
        ? (next.draft.review_reasons as string[])
        : [],
    );
  }, []);

  async function startDirectEntry() {
    setError(null);
    setBusy(true);
    try {
      const created = await createFuelManualEntryStage();
      applyStage(created);
      setTab("manual");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not start manual entry.");
    } finally {
      setBusy(false);
    }
  }

  async function onReceiptChosen(file: File) {
    setError(null);
    setBusy(true);
    try {
      const created = await uploadFuelManualEntryReceipt(file);
      applyStage(created);
      setTab("receipt");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Receipt upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function saveDraft(e?: FormEvent) {
    e?.preventDefault();
    if (!stage) return;
    setError(null);
    setBusy(true);
    try {
      const updated = await patchFuelManualEntryStage(stage.stage_id, formToDraftPatch(form));
      applyStage(updated);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not save draft.");
    } finally {
      setBusy(false);
    }
  }

  async function processEntry() {
    if (!stage) return;
    setError(null);
    setBusy(true);
    try {
      await patchFuelManualEntryStage(stage.stage_id, formToDraftPatch(form));
      const processed = await processFuelManualEntryStage(stage.stage_id);
      onProcessed({
        importId: stage.stage_id,
        invoiceNumber: form.invoice_reference.trim() || undefined,
      });
      setStage(null);
      onClose();
      void processed;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Process failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleClose() {
    if (stage) {
      try {
        await discardFuelManualEntryStage(stage.stage_id);
      } catch {
        /* best-effort */
      }
    }
    onClose();
  }

  const subtitle = useMemo(() => {
    if (!stage) return "Enter required details or upload a receipt to hydrate the form.";
    if (stage.entry_method === "RECEIPT" && stage.source_file_name) {
      return `Receipt: ${stage.source_file_name}`;
    }
    return "Direct manual entry";
  }, [stage]);

  const fieldClass =
    "w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-1 text-xs text-[var(--trk-text)]";

  return (
    <FuelFullScreenOverlay
      open={open}
      title="Manual Fuel Entry"
      subtitle={subtitle}
      onClose={() => void handleClose()}
      testId="fuel-manual-entry-modal"
      closeLabel="Cancel"
    >
      <div className="mx-auto max-w-3xl space-y-3 px-3 py-2">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded-md border border-[var(--trk-border-strong)] px-3 py-1.5 text-xs font-medium disabled:opacity-50"
            onClick={() => receiptInputRef.current?.click()}
          >
            Upload receipt
          </button>
          <button
            type="button"
            disabled={busy}
            className="rounded-md bg-[var(--trk-btn-primary)] px-3 py-1.5 text-xs font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
            onClick={() => void startDirectEntry()}
          >
            Enter manually
          </button>
          <input
            ref={receiptInputRef}
            type="file"
            accept="image/*,.pdf,application/pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onReceiptChosen(f);
              e.target.value = "";
            }}
          />
          {tab === "receipt" ? (
            <span className="text-xs text-[var(--trk-text-muted)]">Receipt mode — review and complete required fields.</span>
          ) : null}
        </div>

        {error ? (
          <p className="text-xs text-[var(--trk-danger)]" role="alert">{error}</p>
        ) : null}

        {requiresReview ? (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-xs text-[var(--trk-text)]">
            <span className="font-semibold">Review before process:</span>{" "}
            {reviewReasons.length ? reviewReasons.join(", ") : "Additional confirmation needed."}
          </div>
        ) : null}

        {stage ? (
          <form className="space-y-3" onSubmit={(e) => void saveDraft(e)}>
            <section className="rounded-lg border border-[var(--trk-border)] p-3">
              <h2 className="mb-2 text-xs font-semibold text-[var(--trk-text)]">Required</h2>
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="text-[10px] text-[var(--trk-text-muted)]">
                  Transaction date
                  <input
                    type="date"
                    required
                    className={fieldClass}
                    value={form.transaction_date}
                    onChange={(e) => setForm((f) => ({ ...f, transaction_date: e.target.value }))}
                  />
                </label>
                <label className="text-[10px] text-[var(--trk-text-muted)]">
                  Unit number
                  <input
                    className={fieldClass}
                    required
                    value={form.unit_number}
                    onChange={(e) => setForm((f) => ({ ...f, unit_number: e.target.value }))}
                  />
                </label>
                <label className="text-[10px] text-[var(--trk-text-muted)]">
                  Product
                  <input
                    className={fieldClass}
                    required
                    value={form.product}
                    onChange={(e) => setForm((f) => ({ ...f, product: e.target.value }))}
                  />
                </label>
                <label className="text-[10px] text-[var(--trk-text-muted)]">
                  Final amount
                  <input
                    className={fieldClass}
                    required
                    inputMode="decimal"
                    value={form.total_amount}
                    onChange={(e) => setForm((f) => ({ ...f, total_amount: e.target.value }))}
                  />
                </label>
                <label className="text-[10px] text-[var(--trk-text-muted)] sm:col-span-2">
                  Currency
                  <select
                    className={fieldClass}
                    required
                    value={form.currency}
                    onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value }))}
                  >
                    <option value="">Select…</option>
                    <option value="USD">USD</option>
                    <option value="CAD">CAD</option>
                  </select>
                </label>
              </div>
            </section>

            <details className="rounded-lg border border-[var(--trk-border)] p-3">
              <summary className="cursor-pointer text-xs font-semibold text-[var(--trk-text)]">
                Optional details
              </summary>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {(
                  [
                    ["transaction_time", "Time"],
                    ["driver_name", "Driver"],
                    ["merchant_site", "Vendor / store"],
                    ["merchant_network", "Network"],
                    ["city", "City"],
                    ["province_state", "Province / state"],
                    ["quantity", "Quantity"],
                    ["quantity_unit", "Quantity unit (L, gal)"],
                    ["unit_price", "Unit / billed price"],
                    ["pre_tax_amount", "Pre-tax amount"],
                    ["gst_amount", "GST"],
                    ["hst_amount", "HST"],
                    ["pst_amount", "PST"],
                    ["qst_amount", "QST"],
                    ["card_or_account_id", "Card / account"],
                    ["receipt_ticket_number", "Receipt / ticket #"],
                    ["authorization_number", "Authorization #"],
                    ["pump", "Pump"],
                    ["invoice_reference", "Invoice / reference"],
                    ["trailer_number", "Trailer"],
                  ] as const
                ).map(([key, label]) => (
                  <label key={key} className="text-[10px] text-[var(--trk-text-muted)]">
                    {label}
                    <input
                      className={fieldClass}
                      value={form[key]}
                      onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                    />
                  </label>
                ))}
                <label className="text-[10px] text-[var(--trk-text-muted)] sm:col-span-2">
                  Notes
                  <textarea
                    className={`${fieldClass} min-h-[4rem]`}
                    value={form.notes}
                    onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                  />
                </label>
              </div>
            </details>

            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={busy}
                className="rounded-md border border-[var(--trk-border-strong)] px-3 py-1.5 text-xs font-medium disabled:opacity-50"
              >
                Save draft
              </button>
              <button
                type="button"
                disabled={busy || requiresReview}
                title={requiresReview ? "Resolve review items before processing" : undefined}
                className="rounded-md bg-[var(--trk-btn-primary)] px-3 py-1.5 text-xs font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
                onClick={() => void processEntry()}
              >
                Process
              </button>
            </div>
          </form>
        ) : (
          <p className="text-xs text-[var(--trk-text-muted)]">
            Choose <strong>Enter manually</strong> or <strong>Upload receipt</strong> to begin.
          </p>
        )}
      </div>
    </FuelFullScreenOverlay>
  );
}
