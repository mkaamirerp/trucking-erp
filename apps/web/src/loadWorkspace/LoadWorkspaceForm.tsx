/**
 * Canonical load workspace form — always uses condensed layout (Task 17).
 */
import Button from "@/components/Button";
import type { LoadNote } from "@/api";
import { LoadWorkspaceCondensedForm } from "./LoadWorkspaceCondensedForm";
import {
  wsInputClass,
  wsLabelClass,
  wsSectionBody,
  wsSectionCard,
  wsSectionHeader,
  wsSectionTitle,
} from "./loadWorkspaceShared";
import type { LoadWorkspaceFormProps } from "./loadWorkspaceFormTypes";

export type { LoadWorkspaceFormProps } from "./loadWorkspaceFormTypes";

const L = wsLabelClass;
const I = wsInputClass;

export function LoadWorkspaceForm(p: LoadWorkspaceFormProps) {
  return <LoadWorkspaceCondensedForm {...p} />;
}

export type LoadWorkspaceNotesPanelProps = {
  internalNotes: string;
  setInternalNotes: (v: string) => void;
  showOperationalNotesTimeline: boolean;
  loadNotes: LoadNote[];
  newNoteBody: string;
  setNewNoteBody: (v: string) => void;
  onAddNote: () => void;
  saving: boolean;
  className?: string;
  dataEditable?: boolean;
  embedded?: boolean;
};

export function LoadWorkspaceNotesPanel(p: LoadWorkspaceNotesPanelProps) {
  const body = (
    <div className={p.embedded ? "px-3 py-2.5" : wsSectionBody}>
      <div>
        <label className={L}>Internal notes (load)</label>
        <textarea
          className={I}
          rows={5}
          value={p.internalNotes}
          onChange={(e) => p.setInternalNotes(e.target.value)}
          placeholder="e.g. rate confirmation excerpt, intake text…"
        />
      </div>
      {p.showOperationalNotesTimeline ? (
        <div className="mt-4 border-t border-[var(--trk-border)] pt-3">
          <p className={L}>Operational notes (timeline)</p>
          <ul className="mt-2 max-h-44 space-y-2 overflow-y-auto rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] p-2.5 text-sm">
            {p.loadNotes.length === 0 ? (
              <li className="text-xs text-[var(--trk-text-muted)]">No notes yet.</li>
            ) : (
              p.loadNotes.map((n) => (
                <li key={n.id} className="border-b border-[var(--trk-border)] pb-2 last:border-0">
                  <p className="text-[var(--trk-text)]">{n.body}</p>
                  <p className="text-[10px] text-[var(--trk-text-muted)]">{new Date(n.created_at).toLocaleString()}</p>
                </li>
              ))
            )}
          </ul>
          <div className="mt-2 flex flex-col gap-2">
            <input
              className={I}
              placeholder="Add operational note…"
              value={p.newNoteBody}
              onChange={(e) => p.setNewNoteBody(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), void p.onAddNote())}
            />
            <Button
              variant="secondary"
              type="button"
              disabled={p.saving || !p.newNoteBody.trim()}
              onClick={p.onAddNote}
            >
              Add note
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
  if (p.embedded) {
    return body;
  }
  return (
    <section className={`${wsSectionCard} ${p.className ?? ""}`} data-editable={p.dataEditable}>
      <div className={wsSectionHeader}>
        <span className={wsSectionTitle}>Notes & documents</span>
      </div>
      {body}
    </section>
  );
}
