/**
 * Single place for mapping tenant `intake_payload` keys (PDF417 + saved draft) → applicant form fields.
 *
 * Backend (`extract_pdf417_fields`) writes e.g. driver_license_number, license_number, license_region,
 * license_state, license_expiry, license_issue_date, license_class, cdl_class, endorsements, restrictions,
 * address_postal, zip_code (US), …
 */

export type OnboardingFormState = Record<string, string>;

export type HydrateIntakeMode = "initial" | "after_dl_upload";

/** Normalize OCR / JSON values for display in text inputs. */
export function cleanIntakeText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") {
    return value
      .replace(/<LF>/g, " ")
      .replace(/<CR>/g, " ")
      .replace(/\r/g, " ")
      .replace(/\n/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value.toISOString().slice(0, 10);
  return "";
}

/**
 * Walk intake key candidates; use the first with a non-empty cleaned value.
 * (Avoids stale `license_region: ""` shadowing `license_state: "ON"` from PDF417.)
 */
export function readFirstNonEmptyIntake(intake: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(intake, key)) continue;
    const cleaned = cleanIntakeText(intake[key]);
    if (cleaned !== "") return cleaned;
  }
  return "";
}

function pickField(
  formKey: string,
  prev: OnboardingFormState,
  intake: Record<string, unknown>,
  intakeKeys: string[],
  mode: HydrateIntakeMode,
): string {
  const incoming = readFirstNonEmptyIntake(intake, intakeKeys);
  const prevVal = prev[formKey] ?? "";
  if (mode === "after_dl_upload") {
    if (prevVal.trim() !== "") return prevVal;
    return incoming || prevVal;
  }
  // initial load: prefer any non-empty intake; otherwise keep previous
  return incoming !== "" ? incoming : prevVal;
}

/**
 * Merge `intake_payload` into applicant onboarding form state.
 *
 * - `initial`: load saved draft / GET application — use intake when it has a value.
 * - `after_dl_upload`: only fill fields the user has left empty (do not stomp typed values).
 */
export function hydrateOnboardingFormFromIntake(
  prev: OnboardingFormState,
  intake: Record<string, unknown> | null | undefined,
  mode: HydrateIntakeMode,
): OnboardingFormState {
  const i = (intake || {}) as Record<string, unknown>;
  const base = {
    ...prev,
    first_name: pickField("first_name", prev, i, ["first_name"], mode),
    middle_name: pickField("middle_name", prev, i, ["middle_name"], mode),
    last_name: pickField("last_name", prev, i, ["last_name"], mode),
    date_of_birth: pickField("date_of_birth", prev, i, ["date_of_birth"], mode),
    email: pickField("email", prev, i, ["email"], mode),
    phone: pickField("phone", prev, i, ["phone"], mode),
    driver_license_number: pickField("driver_license_number", prev, i, ["license_number", "driver_license_number"], mode),
    license_region: pickField("license_region", prev, i, ["license_region", "license_state"], mode),
    license_expiry: pickField("license_expiry", prev, i, ["license_expiry"], mode),
    license_issue_date: pickField("license_issue_date", prev, i, ["license_issue_date", "issue_date"], mode),
    cdl_class: pickField("cdl_class", prev, i, ["license_class", "cdl_class"], mode),
    endorsements: pickField("endorsements", prev, i, ["endorsements"], mode),
    restrictions: pickField("restrictions", prev, i, ["restrictions"], mode),
    conditions: pickField("conditions", prev, i, ["conditions"], mode),
    sex: pickField("sex", prev, i, ["sex"], mode),
    height: pickField("height", prev, i, ["height"], mode),
    address_street: pickField("address_street", prev, i, ["address_line", "address_street"], mode),
    address_city: pickField("address_city", prev, i, ["address_city"], mode),
    address_region: pickField("address_region", prev, i, ["address_region"], mode),
    address_postal: pickField("address_postal", prev, i, ["address_postal"], mode),
    zip_code: pickField("zip_code", prev, i, ["zip_code"], mode),
    address_country: pickField("address_country", prev, i, ["address_country", "form_country_default"], mode),
    // Non-PDF417 fields: still honor intake on initial load; after_dl_upload only fills if empty
    ssn: pickField("ssn", prev, i, ["ssn"], mode),
    nationality: pickField("nationality", prev, i, ["nationality"], mode),
    years_experience: pickField("years_experience", prev, i, ["years_experience"], mode),
    total_miles: pickField("total_miles", prev, i, ["total_miles"], mode),
    equipment_types: pickField("equipment_types", prev, i, ["equipment_types"], mode),
    accidents_last_3_years: pickField("accidents_last_3_years", prev, i, ["accidents_last_3_years"], mode),
    violations_last_3_years: pickField("violations_last_3_years", prev, i, ["violations_last_3_years"], mode),
    dot_medical_card_expiry: pickField("dot_medical_card_expiry", prev, i, ["dot_medical_card_expiry"], mode),
    emergency_contact_name: pickField("emergency_contact_name", prev, i, ["emergency_contact_name"], mode),
    emergency_contact_relationship: pickField("emergency_contact_relationship", prev, i, ["emergency_contact_relationship"], mode),
    emergency_contact_phone: pickField("emergency_contact_phone", prev, i, ["emergency_contact_phone"], mode),
  };

  const country = cleanIntakeText(
    readFirstNonEmptyIntake(i, ["address_country", "form_country_default"]),
  ).toUpperCase();
  let address_postal = String(base.address_postal ?? "");
  let zip_code = String(base.zip_code ?? "");
  if (country === "US" && !zip_code.trim() && address_postal.trim()) {
    zip_code = address_postal;
  }
  if (country === "CA" && !address_postal.trim() && zip_code.trim()) {
    address_postal = zip_code;
  }
  return { ...base, address_postal, zip_code };
}

/**
 * Only non-empty trimmed form values — avoids wiping PDF417 / saved `intake_payload` when the UI still has "".
 * (Spreading full `form` over intake was clearing `driver_license_number`, `license_expiry`, etc.)
 */
export function formToIntakeNonEmptyOverlay(form: OnboardingFormState): Record<string, unknown> {
  const o: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(form)) {
    if (typeof v === "string" && v.trim() !== "") {
      o[k] = v.trim();
    }
  }
  return o;
}

function intakeWithLicenseAliases(p: Record<string, unknown>): Record<string, unknown> {
  const o = { ...p };
  if (typeof o.driver_license_number === "string" && o.driver_license_number.trim()) {
    o.license_number = o.driver_license_number.trim();
  }
  if (typeof o.license_region === "string" && o.license_region.trim()) {
    o.license_state = o.license_region.trim();
  }
  if (typeof o.cdl_class === "string" && o.cdl_class.trim()) {
    o.license_class = o.cdl_class.trim();
  }
  return o;
}

/** Merge saved intake with form + extras for POST `/application/intake` or submit. */
export function mergeIntakeForSave(
  baseIntake: Record<string, unknown>,
  form: OnboardingFormState,
  extras: Record<string, unknown>,
): Record<string, unknown> {
  const overlay = formToIntakeNonEmptyOverlay(form);
  const cc = String(overlay.address_country ?? "").trim().toUpperCase();
  if (cc === "US") {
    const z = typeof overlay.zip_code === "string" ? overlay.zip_code.trim() : "";
    const p = typeof overlay.address_postal === "string" ? overlay.address_postal.trim() : "";
    if (z && !p) {
      overlay.address_postal = z;
    }
  }
  const merged = intakeWithLicenseAliases({
    ...baseIntake,
    ...overlay,
    ...extras,
  });
  const finalCountry = String(merged.address_country ?? "").trim().toUpperCase();
  if (finalCountry === "CA") {
    delete merged.zip_code;
  }
  return merged;
}
