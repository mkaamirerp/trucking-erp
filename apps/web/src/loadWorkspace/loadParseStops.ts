import type { LoadDocumentParseStop } from "../api";

function t(v: string | null | undefined): string {
  return typeof v === "string" ? v.trim() : "";
}

/** Parser shells often have a 2-letter state from regex noise or a stray short token. */
const MIN_FACILITY_LEN = 3;
const MIN_STREET_LEN = 5;
const MIN_CITY_STANDALONE = 3;
const MIN_US_ZIP = 5;
const MIN_REF_LEN = 4;
const MIN_NOTE_LEN = 8;

/**
 * Address / stop fields shared by parsed stops, draft rows, and persist payloads.
 * `commodity_notes` exists on saved draft UI rows only; optional here for one shared gate.
 */
export type StopRowIdentity = {
  facility_name?: string | null;
  street?: string | null;
  city?: string | null;
  state_or_province?: string | null;
  postal_code?: string | null;
  country?: string | null;
  reference_number?: string | null;
  appointment_type?: string | null;
  appointment_date?: string | null;
  appointment_time_text?: string | null;
  notes?: string | null;
  commodity_notes?: string | null;
};

/**
 * True when a stop row is worth keeping for hydration, draft UI, and save (not a blank shell).
 * Rejects: state-only, appointment-only, notes shorter than {@link MIN_NOTE_LEN}, 1–2 char tokens, etc.
 */
export function hasUsefulStopIdentity(row: StopRowIdentity): boolean {
  const fac = t(row.facility_name);
  const st = t(row.street);
  const city = t(row.city);
  const state = t(row.state_or_province);
  const zip = t(row.postal_code);
  const ctry = t(row.country);
  const ref = t(row.reference_number);
  const notes = t(row.notes);
  const cnotes = t(row.commodity_notes);
  const apptType = t(row.appointment_type);
  const apptDate = t(row.appointment_date);
  const apptTime = t(row.appointment_time_text);
  const hasAppt = apptType.length > 0 || apptDate.length > 0 || apptTime.length > 0;

  if (fac.length >= MIN_FACILITY_LEN) return true;
  if (st.length >= MIN_STREET_LEN) return true;
  if (city.length >= MIN_CITY_STANDALONE) return true;
  if (city.length >= 2 && state.length >= 2) return true;
  if (zip.length >= MIN_US_ZIP) return true;
  if (ctry.length >= 2 && (city.length >= 2 || fac.length >= 2)) return true;
  if (ref.length >= MIN_REF_LEN) return true;
  if (notes.length >= MIN_NOTE_LEN) return true;
  if (cnotes.length >= MIN_NOTE_LEN) return true;

  if (hasAppt) {
    if (
      fac.length >= MIN_FACILITY_LEN ||
      st.length >= MIN_STREET_LEN ||
      (city.length >= 2 && state.length >= 2) ||
      city.length >= MIN_CITY_STANDALONE ||
      zip.length >= MIN_US_ZIP
    ) {
      return true;
    }
  }

  return false;
}

/**
 * True if a parsed stop should hydrate into the load workspace (strict gate on shells / noise).
 * @see hasUsefulStopIdentity
 */
export function isMeaningfulParsedStop(stop: LoadDocumentParseStop): boolean {
  return hasUsefulStopIdentity(stop);
}

export function filterMeaningfulParsedStops(stops: LoadDocumentParseStop[]): LoadDocumentParseStop[] {
  return stops.filter(isMeaningfulParsedStop);
}
