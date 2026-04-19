import type { LoadDocumentParseStop } from "../api";

function trimNonEmpty(v: string | null | undefined): boolean {
  return typeof v === "string" && v.trim().length > 0;
}

/**
 * True if a parsed stop has at least one substantive field beyond `stop_type` / `sequence`.
 * Conservative gate to avoid blank rows in the draft UI from parser shells.
 */
export function isMeaningfulParsedStop(stop: LoadDocumentParseStop): boolean {
  return (
    trimNonEmpty(stop.facility_name) ||
    trimNonEmpty(stop.street) ||
    trimNonEmpty(stop.city) ||
    trimNonEmpty(stop.state_or_province) ||
    trimNonEmpty(stop.postal_code) ||
    trimNonEmpty(stop.country) ||
    trimNonEmpty(stop.reference_number) ||
    trimNonEmpty(stop.appointment_type) ||
    trimNonEmpty(stop.appointment_date) ||
    trimNonEmpty(stop.appointment_time_text) ||
    trimNonEmpty(stop.notes)
  );
}

export function filterMeaningfulParsedStops(stops: LoadDocumentParseStop[]): LoadDocumentParseStop[] {
  return stops.filter(isMeaningfulParsedStop);
}
