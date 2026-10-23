import type { LoadWorkspaceDraft } from "@/api";

/** Short label for loads list / resume row. */
export function workspaceDraftListLabel(draft: LoadWorkspaceDraft): string {
  const j = draft.draft_json ?? {};
  const ref = String(j.brokerLoadReference ?? j.broker_load_reference ?? "").trim();
  const commodity = String(j.commodity ?? "").trim();
  const broker = String(j.brokerNameSnapshot ?? j.broker_name_snapshot ?? "").trim();
  if (ref) return ref;
  if (commodity) return commodity;
  if (broker) return broker;
  if (draft.pdf_filename?.trim()) return draft.pdf_filename.trim();
  return "Workspace draft";
}
