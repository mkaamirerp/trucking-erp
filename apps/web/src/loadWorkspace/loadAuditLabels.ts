/** Friendly labels for load audit_events.action values (History panel + audit mode). */

export function loadAuditActionLabel(action: string): string {
  switch (action) {
    case "load_created":
      return "Load created";
    case "load_updated":
      return "Load updated";
    case "load_status_changed":
      return "Status changed";
    case "load_assigned":
      return "Driver assignment changed";
    case "load_dispatched":
      return "Load dispatched";
    case "document_snapshot_confirmed":
      return "Document snapshot confirmed";
    case "customs_broker_changed":
      return "Customs broker changed";
    case "note_added":
      return "Note added";
    case "load_marked_ready":
      return "Marked ready";
    case "load_cancelled":
      return "Load cancelled";
    case "load_stops_changed":
      return "Pickup / delivery changed";
    case "load_revised_rc_attached":
      return "Revised RC uploaded";
    case "load_reparse_pdf_accepted":
      return "Revised RC saved";
    case "pod_evidence_uploaded":
      return "POD uploaded";
    default:
      return action;
  }
}

export function formatLoadAuditActor(
  row: { actor_label?: string | null; actor_user_id?: number | null },
): string {
  const label = row.actor_label?.trim();
  if (label) return label;
  if (row.actor_user_id != null) return `User #${row.actor_user_id}`;
  return "System";
}

export function formatLoadStopsAuditSummary(changedFields: Record<string, unknown>): string {
  const raw = changedFields.stops;
  if (!raw || typeof raw !== "object") {
    return "Stops changed";
  }
  const diff = raw as { added?: unknown[]; removed?: unknown[]; updated?: unknown[] };
  const parts: string[] = [];
  const updated = Array.isArray(diff.updated) ? diff.updated.length : 0;
  const added = Array.isArray(diff.added) ? diff.added.length : 0;
  const removed = Array.isArray(diff.removed) ? diff.removed.length : 0;
  if (updated > 0) parts.push(`${updated} updated`);
  if (added > 0) parts.push(`${added} added`);
  if (removed > 0) parts.push(`${removed} removed`);
  if (parts.length === 0) {
    return "Stops changed";
  }
  return `Stops: ${parts.join(", ")}`;
}

export function formatAuditValue(v: unknown): string {
  if (v === null) return "null";
  if (v === undefined) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

function startOfLocalDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

export function loadAuditDayGroupLabel(eventAt: Date, now: Date = new Date()): string {
  const eventDay = startOfLocalDay(eventAt);
  const today = startOfLocalDay(now);
  const yesterday = today - 86400000;
  if (eventDay === today) return "Today";
  if (eventDay === yesterday) return "Yesterday";
  return eventAt.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: eventAt.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
  });
}

export type LoadAuditDayGroup<T extends { id: number; event_at: string }> = {
  label: string;
  rows: T[];
};

/** Rows must already be sorted newest-first. */
export function groupLoadAuditRowsByDay<T extends { id: number; event_at: string }>(
  rows: T[],
  now: Date = new Date(),
): LoadAuditDayGroup<T>[] {
  const groups: LoadAuditDayGroup<T>[] = [];
  let currentLabel: string | null = null;
  let bucket: T[] = [];
  for (const row of rows) {
    const label = loadAuditDayGroupLabel(new Date(row.event_at), now);
    if (label !== currentLabel) {
      if (bucket.length) {
        groups.push({ label: currentLabel!, rows: bucket });
      }
      currentLabel = label;
      bucket = [row];
    } else {
      bucket.push(row);
    }
  }
  if (bucket.length && currentLabel) {
    groups.push({ label: currentLabel, rows: bucket });
  }
  return groups;
}
