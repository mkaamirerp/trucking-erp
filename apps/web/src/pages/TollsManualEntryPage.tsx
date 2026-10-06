import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  createTollManualStage,
  discardTollManualStage,
  listTollManualStages,
  patchTollManualStage,
  processTollManualStage,
  validateTollManualStage,
  type TollManualStage,
} from "../api";
import EmptyState from "../components/EmptyState";
import { Table } from "../components/Table";
import TollsModuleNav from "./TollsModuleNav";

type Draft = {
  event_date: string;
  event_time: string;
  agency_raw: string;
  trip_charge: string;
  transponder_number: string;
  plate_number: string;
  plate_state: string;
  entry_location: string;
  exit_location: string;
  notes: string;
  unresolved_vehicle_identity: boolean;
};

const EMPTY_DRAFT: Draft = {
  event_date: "",
  event_time: "",
  agency_raw: "",
  trip_charge: "",
  transponder_number: "",
  plate_number: "",
  plate_state: "",
  entry_location: "",
  exit_location: "",
  notes: "",
  unresolved_vehicle_identity: false,
};

function isQuietTollListFailure(message: string): boolean {
  const text = message.trim().toLowerCase();
  return text === "internal server error" || text.includes('"detail":"internal server error"');
}

function apiErrorMessage(err: unknown): string {
  if (!(err instanceof Error)) return String(err);
  try {
    const parsed = JSON.parse(err.message) as { detail?: { message?: string } | string };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (parsed.detail && typeof parsed.detail === "object" && parsed.detail.message) {
      return parsed.detail.message;
    }
  } catch {
    /* raw text */
  }
  return err.message;
}

function stageToDraft(stage: TollManualStage): Draft {
  return {
    event_date: stage.event_date ?? "",
    event_time: stage.event_time ?? "",
    agency_raw: stage.agency_raw ?? "",
    trip_charge: stage.trip_charge ?? "",
    transponder_number: stage.transponder_number ?? "",
    plate_number: stage.plate_number ?? "",
    plate_state: stage.plate_state ?? "",
    entry_location: stage.entry_location ?? "",
    exit_location: stage.exit_location ?? "",
    notes: stage.notes ?? "",
    unresolved_vehicle_identity: Boolean(stage.unresolved_vehicle_identity),
  };
}

function draftPayload(draft: Draft) {
  return {
    event_date: draft.event_date || null,
    event_time: draft.event_time || null,
    agency_raw: draft.agency_raw || null,
    trip_charge: draft.trip_charge || null,
    transponder_number: draft.transponder_number || null,
    plate_number: draft.plate_number || null,
    plate_state: draft.plate_state || null,
    entry_location: draft.entry_location || null,
    exit_location: draft.exit_location || null,
    notes: draft.notes || null,
    unresolved_vehicle_identity: draft.unresolved_vehicle_identity,
  };
}

export default function TollsManualEntryPage() {
  const [items, setItems] = useState<TollManualStage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [stageId, setStageId] = useState<number | null>(null);
  const [status, setStatus] = useState<string>("DRAFT");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await listTollManualStages());
    } catch (err) {
      const message = apiErrorMessage(err);
      setItems([]);
      setError(isQuietTollListFailure(message) ? null : message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  function applyStage(stage: TollManualStage, extraNote?: string) {
    setStageId(stage.stage_id);
    setStatus(stage.status);
    setDraft(stageToDraft(stage));
    if (extraNote) setNote(extraNote);
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNote(null);
    try {
      const stage = await createTollManualStage(draftPayload(draft));
      applyStage(stage, "Manual Toll draft saved for review. Canonical tolls are not created.");
      await loadList();
    } catch (err) {
      setNote(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function onSave() {
    if (stageId == null) return;
    setBusy(true);
    setNote(null);
    try {
      const stage = await patchTollManualStage(stageId, draftPayload(draft));
      applyStage(stage, "Manual Toll draft updated. Still review-stage only.");
      await loadList();
    } catch (err) {
      setNote(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function onValidate() {
    if (stageId == null) return;
    setBusy(true);
    setNote(null);
    try {
      const result = await validateTollManualStage(stageId);
      applyStage(result.stage);
      setNote(
        result.ok
          ? `Validated as ${result.stage.status}. Ready to Process.`
          : result.errors.map((item) => item.message).join(" "),
      );
      await loadList();
    } catch (err) {
      setNote(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function onDiscard() {
    if (stageId == null) return;
    setBusy(true);
    setNote(null);
    try {
      await discardTollManualStage(stageId);
      setStageId(null);
      setStatus("DRAFT");
      setDraft(EMPTY_DRAFT);
      setNote("Manual Toll draft discarded.");
      await loadList();
    } catch (err) {
      setNote(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function onProcess() {
    if (stageId == null) return;
    setBusy(true);
    setNote(null);
    try {
      const result = await processTollManualStage(stageId);
      setStatus(result.process_status);
      setNote(
        `Processed ${result.processed_transaction_count} TollTransaction totaling ${result.processed_total}.`,
      );
      await loadList();
    } catch (err) {
      setNote(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const readOnly = status === "PROCESSED";
  const canProcess = status === "NEEDS_REVIEW" && stageId != null && !busy;

  return (
    <div className="trk-page trk-page--constrained space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-[var(--trk-text)]">Tolls</h1>
        <p className="mt-1 text-sm text-[var(--trk-text-muted)]">
          Manual Entry is a first-class Toll source. Validate to NEEDS_REVIEW, then Process to
          create one canonical TollTransaction.
        </p>
        <div className="mt-3">
          <TollsModuleNav active="manual" />
        </div>
      </div>

      <form
        onSubmit={onCreate}
        className="space-y-3 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] p-4"
      >
        <h2 className="text-sm font-semibold text-[var(--trk-text)]">Manual Toll draft</h2>
        <p className="text-sm text-[var(--trk-text-muted)]">
          Review evidence only. Do not assign a unit, driver, owner operator, payroll, or settlement.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm font-medium text-[var(--trk-text)]">
            Toll date
            <input
              type="date"
              value={draft.event_date}
              disabled={readOnly}
              onChange={(ev) => setDraft({ ...draft, event_date: ev.target.value })}
              className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm disabled:opacity-60"
            />
          </label>
          <label className="text-sm font-medium text-[var(--trk-text)]">
            Time optional
            <input
              type="time"
              value={draft.event_time}
              disabled={readOnly}
              onChange={(ev) => setDraft({ ...draft, event_time: ev.target.value })}
              className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm disabled:opacity-60"
            />
          </label>
          <label className="text-sm font-medium text-[var(--trk-text)]">
            Agency
            <input
              value={draft.agency_raw}
              disabled={readOnly}
              onChange={(ev) => setDraft({ ...draft, agency_raw: ev.target.value })}
              className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm disabled:opacity-60"
            />
          </label>
          <label className="text-sm font-medium text-[var(--trk-text)]">
            Amount
            <input
              value={draft.trip_charge}
              disabled={readOnly}
              onChange={(ev) => setDraft({ ...draft, trip_charge: ev.target.value })}
              className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm disabled:opacity-60"
            />
          </label>
          <label className="text-sm font-medium text-[var(--trk-text)]">
            Transponder
            <input
              value={draft.transponder_number}
              disabled={readOnly}
              onChange={(ev) => setDraft({ ...draft, transponder_number: ev.target.value })}
              className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm disabled:opacity-60"
            />
          </label>
          <label className="text-sm font-medium text-[var(--trk-text)]">
            Plate
            <input
              value={draft.plate_number}
              disabled={readOnly}
              onChange={(ev) => setDraft({ ...draft, plate_number: ev.target.value })}
              className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm disabled:opacity-60"
            />
          </label>
          <label className="text-sm font-medium text-[var(--trk-text)]">
            Plate state
            <input
              value={draft.plate_state}
              disabled={readOnly}
              onChange={(ev) => setDraft({ ...draft, plate_state: ev.target.value })}
              className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm disabled:opacity-60"
            />
          </label>
          <label className="text-sm font-medium text-[var(--trk-text)]">
            Entry location
            <input
              value={draft.entry_location}
              disabled={readOnly}
              onChange={(ev) => setDraft({ ...draft, entry_location: ev.target.value })}
              className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm disabled:opacity-60"
            />
          </label>
          <label className="text-sm font-medium text-[var(--trk-text)]">
            Exit location
            <input
              value={draft.exit_location}
              disabled={readOnly}
              onChange={(ev) => setDraft({ ...draft, exit_location: ev.target.value })}
              className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm disabled:opacity-60"
            />
          </label>
          <label className="sm:col-span-2 text-sm font-medium text-[var(--trk-text)]">
            Notes
            <textarea
              value={draft.notes}
              disabled={readOnly}
              onChange={(ev) => setDraft({ ...draft, notes: ev.target.value })}
              className="mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm disabled:opacity-60"
              rows={3}
            />
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm text-[var(--trk-text)]">
          <input
            type="checkbox"
            checked={draft.unresolved_vehicle_identity}
            disabled={readOnly}
            onChange={(ev) => setDraft({ ...draft, unresolved_vehicle_identity: ev.target.checked })}
          />
          Vehicle identity unresolved
        </label>
        {stageId != null ? (
          <p className="text-sm text-[var(--trk-text-muted)]">
            Stage #{stageId} · {status} · source MANUAL
          </p>
        ) : null}
        {note ? <p className="text-sm text-[var(--trk-text-muted)]">{note}</p> : null}
        <div className="flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-[var(--trk-btn-primary)] px-4 py-2 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
          >
            {busy ? "Saving…" : "Create draft"}
          </button>
          <button
            type="button"
            disabled={busy || stageId == null || readOnly}
            onClick={() => void onSave()}
            className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-4 py-2 text-sm font-medium text-[var(--trk-text)] disabled:opacity-50"
          >
            Save edits
          </button>
          <button
            type="button"
            disabled={busy || stageId == null || readOnly}
            onClick={() => void onValidate()}
            className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-4 py-2 text-sm font-medium text-[var(--trk-text)] disabled:opacity-50"
          >
            Validate
          </button>
          <button
            type="button"
            disabled={!canProcess}
            onClick={() => void onProcess()}
            className="rounded-md bg-[var(--trk-btn-primary)] px-4 py-2 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
          >
            Process
          </button>
          <button
            type="button"
            disabled={busy || stageId == null || readOnly}
            onClick={() => void onDiscard()}
            className="rounded-md border border-[var(--trk-border)] px-4 py-2 text-sm font-medium text-[var(--trk-text)] disabled:opacity-50"
          >
            Discard
          </button>
        </div>
      </form>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-[var(--trk-text)]">Manual review drafts</h2>
        {loading ? <p className="text-sm text-[var(--trk-text-muted)]">Loading manual drafts…</p> : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState
            title="No manual Toll drafts"
            description="Create a MANUAL review stage. Canonical toll transactions are not created."
          />
        ) : null}
        {!loading && items.length > 0 ? (
          <Table headers={["Stage", "Date", "Agency", "Amount", "Status"]}>
            {items.map((item) => (
              <tr key={item.stage_id}>
                <td className="px-4 py-2 text-sm">
                  <button
                    type="button"
                    className="text-[var(--trk-accent)] underline-offset-2 hover:underline"
                    onClick={() => applyStage(item)}
                  >
                    #{item.stage_id}
                  </button>
                </td>
                <td className="px-4 py-2 text-sm text-[var(--trk-text-muted)]">{item.event_date || "—"}</td>
                <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{item.agency_raw || "—"}</td>
                <td className="px-4 py-2 text-sm text-[var(--trk-text)]">{item.trip_charge || "—"}</td>
                <td className="px-4 py-2 text-sm text-[var(--trk-text-muted)]">{item.status}</td>
              </tr>
            ))}
          </Table>
        ) : null}
      </section>
    </div>
  );
}
