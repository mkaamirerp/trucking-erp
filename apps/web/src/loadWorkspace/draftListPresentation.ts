import type { Load, LoadWorkspaceDraft } from "@/api";
import type { WorkspaceDraftFields } from "@/loadWorkspace/loadWorkspaceShared";
import { workspaceFieldsFromDraftJson } from "@/loadWorkspace/loadWorkspaceShared";
import { listCreateLoadHardMissing } from "@/loadWorkspace/workspaceCreateLoadValidation";
import type { Broker } from "@/api";
import { formatRouteFromStops } from "@/utils/loadStops";

export type DraftListRowKind = "workspace_draft" | "load_draft";

export type DraftListRow = {
  kind: DraftListRowKind;
  id: string;
  title: string;
  missingLine: string | null;
  updatedAt: string;
  pdfHint: string | null;
  loadId?: number;
};

function loadNumberOrPoLabel(fields: WorkspaceDraftFields): string {
  const brokerRef = (fields.brokerLoadReference || "").trim();
  if (brokerRef) return brokerRef;
  const loadNum = (fields.loadNumber || "").trim();
  if (loadNum) return loadNum;
  for (const r of fields.loadReferences) {
    const v = (r.value || "").trim();
    if (v) return v;
  }
  return "";
}

export function draftTitleFromFields(
  fields: WorkspaceDraftFields,
  pdfFilename?: string | null,
): string {
  const broker = (fields.brokerNameSnapshot || "").trim();
  const route = formatRouteFromStops(fields.draftStops);
  if (broker && route && route !== "—") return `${broker} · ${route}`;
  const ref = loadNumberOrPoLabel(fields);
  if (ref) return ref;
  const commodity = (fields.commodity || "").trim();
  if (commodity) return commodity;
  const fn = (pdfFilename || "").trim();
  if (fn) return fn;
  return "Untitled draft";
}

export function missingLineForFields(fields: WorkspaceDraftFields, brokers: Broker[]): string | null {
  const missing = listCreateLoadHardMissing(fields, brokers);
  if (missing.length === 0) return null;
  return `Missing: ${missing.join(", ")}`;
}

export function workspaceDraftToListRow(draft: LoadWorkspaceDraft, brokers: Broker[]): DraftListRow {
  const fields = workspaceFieldsFromDraftJson(draft.draft_json ?? {});
  return {
    kind: "workspace_draft",
    id: draft.id,
    title: draftTitleFromFields(fields, draft.pdf_filename),
    missingLine: missingLineForFields(fields, brokers),
    updatedAt: draft.updated_at,
    pdfHint: draft.pdf_filename ? "PDF attached" : "No PDF",
  };
}

export function loadDraftToListRow(load: Load, brokers: Broker[]): DraftListRow {
  const broker = (load.broker_name_snapshot || "").trim();
  const route = formatRouteFromStops(load.stops ?? []);
  let title = "Untitled draft";
  if (broker && route && route !== "—") title = `${broker} · ${route}`;
  else if ((load.broker_load_reference || "").trim()) title = load.broker_load_reference!.trim();
  else if ((load.load_number || "").trim()) title = load.load_number!.trim();
  else if ((load.commodity || "").trim()) title = load.commodity!.trim();

  const fields: WorkspaceDraftFields = {
    ...workspaceFieldsFromDraftJson({}),
    brokerId: load.broker_id ?? null,
    brokerNameSnapshot: load.broker_name_snapshot ?? "",
    brokerLoadReference: load.broker_load_reference ?? "",
    commodity: load.commodity ?? "",
    draftStops: (load.stops ?? []).map((s, i) => ({
      id: s.id,
      load_id: load.id,
      stop_type: s.stop_type,
      sequence: s.sequence ?? i,
      facility_name: s.facility_name ?? null,
      street: s.street ?? null,
      city: s.city ?? null,
      state_or_province: s.state_or_province ?? null,
      postal_code: s.postal_code ?? null,
      country: s.country ?? null,
      reference_number: s.reference_number ?? null,
      appointment_type: s.appointment_type ?? null,
      appointment_date: s.appointment_date ?? null,
      appointment_time_text: s.appointment_time_text ?? null,
      scheduled_at: s.scheduled_at ?? null,
      notes: s.notes ?? null,
      commodity_notes: s.commodity_notes ?? null,
      created_at: s.created_at ?? null,
      updated_at: s.updated_at ?? null,
      _key: `load-${load.id}-stop-${s.id}`,
    })),
  };

  return {
    kind: "load_draft",
    id: String(load.id),
    loadId: load.id,
    title,
    missingLine: missingLineForFields(fields, brokers),
    updatedAt: load.updated_at ?? load.created_at ?? new Date().toISOString(),
    pdfHint: null,
  };
}
