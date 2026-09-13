/**
 * Single DRIVER onboarding validation + normalization catalog.
 * Used for live input, step Continue, and final Submit. Do not duplicate checks in the page.
 */

export const US_STATES: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California", CO: "Colorado",
  CT: "Connecticut", DE: "Delaware", FL: "Florida", GA: "Georgia", HI: "Hawaii", ID: "Idaho",
  IL: "Illinois", IN: "Indiana", IA: "Iowa", KS: "Kansas", KY: "Kentucky", LA: "Louisiana",
  ME: "Maine", MD: "Maryland", MA: "Massachusetts", MI: "Michigan", MN: "Minnesota",
  MS: "Mississippi", MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada",
  NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York",
  NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon",
  PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota",
  TN: "Tennessee", TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia",
  WA: "Washington", WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming",
};

export const CA_PROVINCES: Record<string, string> = {
  AB: "Alberta", BC: "British Columbia", MB: "Manitoba", NB: "New Brunswick",
  NL: "Newfoundland and Labrador", NS: "Nova Scotia", NT: "Northwest Territories",
  NU: "Nunavut", ON: "Ontario", PE: "Prince Edward Island", QC: "Quebec",
  SK: "Saskatchewan", YT: "Yukon",
};

export const REQUIRED_DOCUMENT_KEYS = ["dot_medical", "mvr", "drug_test", "psp_report"] as const;

export const MSG = {
  dlFront: "Confirm the front of your driver licence.",
  dlBack: "Confirm the back of your driver licence.",
  country: "Select a country.",
  licenceNumber: "Enter your licence number.",
  licenceRegion: "Select the province or state that issued the licence.",
  expiry: "Enter a valid expiry date.",
  issue: "Enter a valid issue date.",
  issueAfterExpiry: "Issue date must be on or before expiry.",
  licenceClass: "Enter the licence class.",
  firstName: "Enter a first name.",
  lastName: "Enter a last name.",
  dob: "Enter a valid date of birth.",
  dobAge: "You must be at least 18 years old.",
  sex: "Select sex / gender.",
  email: "Enter a valid email address.",
  phone: "Enter a valid 10-digit phone number.",
  street: "Enter a street address.",
  city: "Enter a city.",
  province: "Select a province or state.",
  postal: "Enter a valid postal code (A1A 1A1).",
  zip: "Enter a valid ZIP code.",
  medicalExpiry: "Enter a valid medical-card expiry.",
  emergencyName: "Enter the emergency contact name.",
  emergencyPhone: "Enter a valid 10-digit phone number.",
  jobCompany: "Enter the company name.",
  jobTitle: "Enter the position.",
  jobStart: "Enter a valid start date.",
  jobEnd: "End date must be on or after start date.",
  refName: "Enter the reference’s name.",
  refContact: "Enter a valid phone or email.",
  supervisorPhone: "Enter a valid phone number.",
  document: "Upload this required document.",
  agreements: "Confirm all three agreements.",
} as const;

export type FieldError = { field: string; message: string };

export type JobEntry = {
  company_name: string;
  position_title: string;
  start_date: string;
  end_date: string;
  reason_for_leaving: string;
  supervisor_name: string;
  supervisor_phone: string;
  equipment_operated: string;
  city_state: string;
  subject_to_fmcsa: string;
};

export type RefEntry = {
  full_name: string;
  relationship: string;
  company: string;
  phone: string;
  email: string;
  known_duration: string;
};

export type OnboardingForm = Record<string, string>;

export type OnboardingSnapshot = {
  form: OnboardingForm;
  jobs: JobEntry[];
  refs: RefEntry[];
  dlFrontConfirmed: boolean;
  dlBackConfirmed: boolean;
  documents: Record<string, boolean | string | undefined>;
  agreeInfoAccurate: boolean;
  agreeBackgroundCheck: boolean;
  agreeDotCompliance: boolean;
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const NAME_RE = /^[\p{L}][\p{L}\p{M}\s.'’-]*$/u;
const POSTAL_CA_RE = /^[A-Z]\d[A-Z][ ]?\d[A-Z]\d$/;
const ZIP_RE = /^\d{5}(-\d{4})?$/;

export function collapseSpaces(value: string): string {
  return (value || "").replace(/\s+/g, " ").trim();
}

export function preserveName(value: string): string {
  return collapseSpaces(value);
}

export function preserveAddress(value: string): string {
  return collapseSpaces(value);
}

export function uppercaseCode(value: string): string {
  return (value || "").replace(/\s+/g, "").toUpperCase();
}

export function uppercaseLicenceNumber(value: string): string {
  return (value || "").replace(/\s+/g, "").toUpperCase();
}

export function uppercaseRestrictionCodes(value: string): string {
  const raw = collapseSpaces(value);
  if (!raw) return "";
  return raw
    .split(",")
    .map((part) => {
      const t = part.trim();
      if (/^[A-Za-z0-9]{1,4}$/.test(t)) return t.toUpperCase();
      return t;
    })
    .join(", ");
}

export function countryCode(value: string): string {
  return collapseSpaces(value).toUpperCase();
}

export function normalizeEmail(value: string): string {
  return collapseSpaces(value).toLowerCase();
}

export function isValidEmail(value: string): boolean {
  const v = normalizeEmail(value);
  if (!v || v.length > 254) return false;
  return EMAIL_RE.test(v);
}

function digitsOnly(value: string): string {
  return (value || "").replace(/\D/g, "");
}

/** NANP 10-digit national number, or null. */
export function parseNanpDigits(value: string): string | null {
  let d = digitsOnly(value);
  if (d.length === 11 && d.startsWith("1")) d = d.slice(1);
  if (d.length !== 10) return null;
  if (!/^[2-9]\d{2}[2-9]\d{6}$/.test(d)) return null;
  return d;
}

export function formatNanpDisplay(digits10: string): string {
  return `(${digits10.slice(0, 3)}) ${digits10.slice(3, 6)}-${digits10.slice(6)}`;
}

export function nanpToE164(digits10: string): string {
  return `+1${digits10}`;
}

export function normalizePhoneInput(value: string): string {
  const d = parseNanpDigits(value);
  if (!d) return (value || "").trim();
  return formatNanpDisplay(d);
}

export function normalizePhoneStored(value: string): string {
  const d = parseNanpDigits(value);
  return d ? nanpToE164(d) : collapseSpaces(value);
}

export function isValidNanpPhone(value: string): boolean {
  return parseNanpDigits(value) !== null;
}

export function formatPostalCALive(value: string): string {
  const compact = (value || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6);
  if (compact.length <= 3) return compact;
  return `${compact.slice(0, 3)} ${compact.slice(3)}`;
}

export function isValidPostalCA(value: string): boolean {
  const compact = (value || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (compact.length !== 6) return false;
  return POSTAL_CA_RE.test(`${compact.slice(0, 3)} ${compact.slice(3)}`) && /^[ABCEGHJ-NPRSTVXY]/.test(compact);
}

export function formatZipLive(value: string): string {
  const d = digitsOnly(value).slice(0, 9);
  if (d.length <= 5) return d;
  return `${d.slice(0, 5)}-${d.slice(5)}`;
}

export function isValidZipUS(value: string): boolean {
  return ZIP_RE.test(formatZipLive(value));
}

export function formatDateAsTyped(raw: string): string {
  const digits = (raw || "").replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 4) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 4)}-${digits.slice(4)}`;
  return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6, 8)}`;
}

export function parseIsoDate(value: string): { y: number; m: number; d: number } | null {
  const v = collapseSpaces(value);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) return null;
  return { y, m: mo, d };
}

export function isCompleteIsoDate(value: string): boolean {
  return parseIsoDate(value) !== null;
}

export function isAgeAtLeast18(iso: string, today: Date = new Date()): boolean {
  const p = parseIsoDate(iso);
  if (!p) return false;
  const ty = today.getFullYear();
  const tm = today.getMonth() + 1;
  const td = today.getDate();
  let age = ty - p.y;
  if (tm < p.m || (tm === p.m && td < p.d)) age -= 1;
  return age >= 18;
}

export function isoDateCompare(a: string, b: string): number | null {
  if (!isCompleteIsoDate(a) || !isCompleteIsoDate(b)) return null;
  return a === b ? 0 : a < b ? -1 : 1;
}

export function isValidName(value: string): boolean {
  const v = preserveName(value);
  if (!v || v.length > 100) return false;
  return NAME_RE.test(v);
}

export function isValidLicenceClass(value: string): boolean {
  const v = uppercaseCode(value);
  return /^[A-Z0-9]{1,8}$/.test(v);
}

export function regionListForCountry(cc: string): Record<string, string> {
  return countryCode(cc) === "CA" ? CA_PROVINCES : US_STATES;
}

export function isValidRegion(country: string, region: string): boolean {
  const cc = countryCode(country);
  const code = countryCode(region);
  if (cc === "CA") return Object.prototype.hasOwnProperty.call(CA_PROVINCES, code);
  if (cc === "US") return Object.prototype.hasOwnProperty.call(US_STATES, code);
  return false;
}

export function errorsByField(errors: FieldError[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const e of errors) {
    if (!out[e.field]) out[e.field] = e.message;
  }
  return out;
}

export function firstErrorMessage(errors: FieldError[]): string {
  return errors[0]?.message || "";
}

export function displayPhone(value: string): string {
  const v = value || "";
  if (/^\+1\d{10}$/.test(v.replace(/\s/g, ""))) {
    const d = parseNanpDigits(v);
    return d ? formatNanpDisplay(d) : v;
  }
  return v;
}

function push(errors: FieldError[], field: string, message: string) {
  errors.push({ field, message });
}

function requireName(errors: FieldError[], field: string, value: string, emptyMsg: string) {
  const v = preserveName(value);
  if (!v) push(errors, field, emptyMsg);
  else if (!isValidName(v)) push(errors, field, emptyMsg);
}

export function normalizeForm(form: OnboardingForm): OnboardingForm {
  const cc = countryCode(form.address_country || "US") || "US";
  const next: OnboardingForm = { ...form };
  next.address_country = cc === "CA" ? "CA" : "US";
  next.first_name = preserveName(form.first_name || "");
  next.middle_name = preserveName(form.middle_name || "");
  next.last_name = preserveName(form.last_name || "");
  next.email = normalizeEmail(form.email || "");
  next.phone = normalizePhoneStored(form.phone || "");
  next.address_street = preserveAddress(form.address_street || "");
  next.address_city = preserveAddress(form.address_city || "");
  next.address_region = countryCode(form.address_region || "");
  next.license_region = countryCode(form.license_region || "");
  next.driver_license_number = uppercaseLicenceNumber(form.driver_license_number || "");
  next.cdl_class = uppercaseCode(form.cdl_class || "");
  next.endorsements = uppercaseCode(form.endorsements || "");
  next.conditions = uppercaseCode(form.conditions || "");
  next.restrictions = uppercaseRestrictionCodes(form.restrictions || "");
  next.date_of_birth = formatDateAsTyped(form.date_of_birth || "");
  next.license_expiry = formatDateAsTyped(form.license_expiry || "");
  next.license_issue_date = formatDateAsTyped(form.license_issue_date || "");
  next.dot_medical_card_expiry = formatDateAsTyped(form.dot_medical_card_expiry || "");
  next.emergency_contact_name = preserveName(form.emergency_contact_name || "");
  next.emergency_contact_relationship = collapseSpaces(form.emergency_contact_relationship || "");
  next.emergency_contact_phone = normalizePhoneStored(form.emergency_contact_phone || "");
  next.nationality = collapseSpaces(form.nationality || "");
  next.height = collapseSpaces(form.height || "");
  next.ssn = digitsOnly(form.ssn || "");
  next.sex = (form.sex || "").trim().toUpperCase();
  if (next.address_country === "CA") {
    next.address_postal = formatPostalCALive(form.address_postal || form.zip_code || "");
    next.zip_code = "";
  } else {
    next.zip_code = formatZipLive(form.zip_code || form.address_postal || "");
    next.address_postal = next.zip_code;
  }
  return next;
}

export function normalizeJob(job: JobEntry): JobEntry {
  return {
    ...job,
    company_name: preserveName(job.company_name),
    position_title: collapseSpaces(job.position_title),
    start_date: formatDateAsTyped(job.start_date),
    end_date: formatDateAsTyped(job.end_date),
    reason_for_leaving: collapseSpaces(job.reason_for_leaving),
    supervisor_name: preserveName(job.supervisor_name),
    supervisor_phone: job.supervisor_phone.trim() ? normalizePhoneStored(job.supervisor_phone) : "",
    equipment_operated: collapseSpaces(job.equipment_operated),
    city_state: collapseSpaces(job.city_state),
    subject_to_fmcsa: (job.subject_to_fmcsa || "").trim().toLowerCase(),
  };
}

export function normalizeRef(ref: RefEntry): RefEntry {
  return {
    ...ref,
    full_name: preserveName(ref.full_name),
    relationship: collapseSpaces(ref.relationship),
    company: collapseSpaces(ref.company),
    phone: ref.phone.trim() ? normalizePhoneStored(ref.phone) : "",
    email: normalizeEmail(ref.email),
    known_duration: collapseSpaces(ref.known_duration),
  };
}

export function normalizeSnapshot(snap: OnboardingSnapshot): OnboardingSnapshot {
  return {
    ...snap,
    form: normalizeForm(snap.form),
    jobs: snap.jobs.map(normalizeJob),
    refs: snap.refs.map(normalizeRef),
  };
}

export function validateStep0(snap: OnboardingSnapshot): FieldError[] {
  const errors: FieldError[] = [];
  const f = snap.form;
  const cc = countryCode(f.address_country);
  if (!snap.dlFrontConfirmed) push(errors, "CDL_FRONT", MSG.dlFront);
  if (!snap.dlBackConfirmed) push(errors, "CDL_BACK", MSG.dlBack);
  if (cc !== "US" && cc !== "CA") push(errors, "address_country", MSG.country);
  if (!uppercaseLicenceNumber(f.driver_license_number)) push(errors, "driver_license_number", MSG.licenceNumber);
  if (!isValidRegion(cc, f.license_region)) push(errors, "license_region", MSG.licenceRegion);
  if (!isCompleteIsoDate(f.license_expiry)) push(errors, "license_expiry", MSG.expiry);
  if (collapseSpaces(f.license_issue_date)) {
    if (!isCompleteIsoDate(f.license_issue_date)) push(errors, "license_issue_date", MSG.issue);
    else if (isCompleteIsoDate(f.license_expiry)) {
      const cmp = isoDateCompare(f.license_issue_date, f.license_expiry);
      if (cmp != null && cmp > 0) push(errors, "license_issue_date", MSG.issueAfterExpiry);
    }
  }
  if (!isValidLicenceClass(f.cdl_class)) push(errors, "cdl_class", MSG.licenceClass);
  return errors;
}

export function validateStep1(snap: OnboardingSnapshot, today?: Date): FieldError[] {
  const errors: FieldError[] = [];
  const f = snap.form;
  const cc = countryCode(f.address_country);
  requireName(errors, "first_name", f.first_name, MSG.firstName);
  if (preserveName(f.middle_name) && !isValidName(f.middle_name)) {
    push(errors, "middle_name", "Use letters only.");
  }
  requireName(errors, "last_name", f.last_name, MSG.lastName);
  if (!isCompleteIsoDate(f.date_of_birth)) push(errors, "date_of_birth", MSG.dob);
  else if (!isAgeAtLeast18(f.date_of_birth, today)) push(errors, "date_of_birth", MSG.dobAge);
  const sex = (f.sex || "").trim().toUpperCase();
  if (sex !== "M" && sex !== "F" && sex !== "X") push(errors, "sex", MSG.sex);
  if (!isValidEmail(f.email)) push(errors, "email", MSG.email);
  if (!isValidNanpPhone(f.phone)) push(errors, "phone", MSG.phone);
  if (!preserveAddress(f.address_street)) push(errors, "address_street", MSG.street);
  if (cc !== "US" && cc !== "CA") push(errors, "address_country", MSG.country);
  if (!preserveAddress(f.address_city)) push(errors, "address_city", MSG.city);
  if (!isValidRegion(cc, f.address_region)) push(errors, "address_region", MSG.province);
  if (cc === "CA") {
    if (!isValidPostalCA(f.address_postal)) push(errors, "address_postal", MSG.postal);
  } else if (cc === "US") {
    if (!isValidZipUS(f.zip_code || f.address_postal)) push(errors, "zip_code", MSG.zip);
  }
  if (collapseSpaces(f.dot_medical_card_expiry) && !isCompleteIsoDate(f.dot_medical_card_expiry)) {
    push(errors, "dot_medical_card_expiry", MSG.medicalExpiry);
  }
  const emName = preserveName(f.emergency_contact_name);
  const emRel = collapseSpaces(f.emergency_contact_relationship);
  const emPhone = collapseSpaces(f.emergency_contact_phone);
  if (emName || emRel || emPhone) {
    if (!emName) push(errors, "emergency_contact_name", MSG.emergencyName);
    if (!isValidNanpPhone(emPhone)) push(errors, "emergency_contact_phone", MSG.emergencyPhone);
  }
  const ssn = digitsOnly(f.ssn || "");
  if (ssn && ssn.length !== 4 && ssn.length !== 9) {
    push(errors, "ssn", "Enter 4 digits or a full SSN.");
  }
  return errors;
}

export function validateStep2(snap: OnboardingSnapshot): FieldError[] {
  const errors: FieldError[] = [];
  const jobs = snap.jobs || [];
  const validJobIndexes = jobs
    .map((j, i) => ({ j, i }))
    .filter(({ j }) => preserveName(j.company_name) && collapseSpaces(j.position_title) && isCompleteIsoDate(j.start_date));
  if (validJobIndexes.length === 0) {
    const j0 = jobs[0] || ({
      company_name: "", position_title: "", start_date: "", end_date: "",
      reason_for_leaving: "", supervisor_name: "", supervisor_phone: "",
      equipment_operated: "", city_state: "", subject_to_fmcsa: "",
    } as JobEntry);
    if (!preserveName(j0.company_name)) push(errors, "jobs.0.company_name", MSG.jobCompany);
    if (!collapseSpaces(j0.position_title)) push(errors, "jobs.0.position_title", MSG.jobTitle);
    if (!isCompleteIsoDate(j0.start_date)) push(errors, "jobs.0.start_date", MSG.jobStart);
  }
  jobs.forEach((j, i) => {
    const started = preserveName(j.company_name) || collapseSpaces(j.position_title) || collapseSpaces(j.start_date);
    if (!started) return;
    if (!preserveName(j.company_name)) push(errors, `jobs.${i}.company_name`, MSG.jobCompany);
    if (!collapseSpaces(j.position_title)) push(errors, `jobs.${i}.position_title`, MSG.jobTitle);
    if (!isCompleteIsoDate(j.start_date)) push(errors, `jobs.${i}.start_date`, MSG.jobStart);
    if (collapseSpaces(j.end_date)) {
      if (!isCompleteIsoDate(j.end_date)) push(errors, `jobs.${i}.end_date`, MSG.jobEnd);
      else if (isCompleteIsoDate(j.start_date) && (isoDateCompare(j.end_date, j.start_date) ?? 0) < 0) {
        push(errors, `jobs.${i}.end_date`, MSG.jobEnd);
      }
    }
    if (collapseSpaces(j.supervisor_phone) && !isValidNanpPhone(j.supervisor_phone)) {
      push(errors, `jobs.${i}.supervisor_phone`, MSG.supervisorPhone);
    }
  });

  const refs = snap.refs || [];
  if (refs.length < 2) {
    push(errors, "refs", MSG.refName);
  }
  for (let i = 0; i < Math.max(2, refs.length); i++) {
    const r = refs[i] || { full_name: "", relationship: "", company: "", phone: "", email: "", known_duration: "" };
    if (!preserveName(r.full_name)) push(errors, `refs.${i}.full_name`, MSG.refName);
    const phoneOk = isValidNanpPhone(r.phone);
    const emailOk = isValidEmail(r.email);
    if (!phoneOk && !emailOk) {
      if (collapseSpaces(r.phone)) push(errors, `refs.${i}.phone`, MSG.phone);
      if (collapseSpaces(r.email)) push(errors, `refs.${i}.email`, MSG.email);
      if (!collapseSpaces(r.phone) && !collapseSpaces(r.email)) {
        push(errors, `refs.${i}.phone`, MSG.refContact);
        push(errors, `refs.${i}.email`, MSG.refContact);
      }
    }
  }
  return errors;
}

export function validateStep3(snap: OnboardingSnapshot): FieldError[] {
  const errors: FieldError[] = [];
  for (const key of REQUIRED_DOCUMENT_KEYS) {
    const v = snap.documents?.[key];
    const present = typeof v === "string" ? v.trim().length > 0 : Boolean(v);
    if (!present) push(errors, `documents.${key}`, MSG.document);
  }
  if (!snap.agreeInfoAccurate || !snap.agreeBackgroundCheck || !snap.agreeDotCompliance) {
    push(errors, "agreements", MSG.agreements);
  }
  return errors;
}

/** Full DRIVER catalog — used by final Submit so stale step-1 data cannot sneak through. */
export function validateSubmit(snap: OnboardingSnapshot, today?: Date): FieldError[] {
  return [
    ...validateStep0(snap),
    ...validateStep1(snap, today),
    ...validateStep2(snap),
    ...validateStep3(snap),
  ];
}

export function validateOnboardingStep(step: 0 | 1 | 2 | 3, snap: OnboardingSnapshot, today?: Date): FieldError[] {
  if (step === 0) return validateStep0(snap);
  if (step === 1) return validateStep1(snap, today);
  if (step === 2) return validateStep2(snap);
  return validateStep3(snap);
}

/** Non-driver contact form: same email/phone/address rules, no DL/docs. */
export function validateNonDriverContact(form: OnboardingForm): FieldError[] {
  return validateStep1(
    {
      form,
      jobs: [],
      refs: [],
      dlFrontConfirmed: true,
      dlBackConfirmed: true,
      documents: Object.fromEntries(REQUIRED_DOCUMENT_KEYS.map((k) => [k, true])),
      agreeInfoAccurate: true,
      agreeBackgroundCheck: true,
      agreeDotCompliance: true,
    },
    new Date("2000-01-01"),
  ).filter((e) =>
    [
      "first_name",
      "last_name",
      "email",
      "phone",
      "address_street",
      "address_city",
      "address_country",
      "address_region",
      "address_postal",
      "zip_code",
    ].includes(e.field),
  );
}

export function liveNormalize(field: string, value: string): string {
  switch (field) {
    case "email":
      return value;
    case "driver_license_number":
      return uppercaseLicenceNumber(value);
    case "cdl_class":
    case "endorsements":
    case "conditions":
      return uppercaseCode(value);
    case "restrictions":
      return uppercaseRestrictionCodes(value);
    case "license_region":
    case "address_region":
    case "address_country":
    case "sex":
      return countryCode(value);
    case "address_postal":
      return formatPostalCALive(value);
    case "zip_code":
      return formatZipLive(value);
    case "date_of_birth":
    case "license_expiry":
    case "license_issue_date":
    case "dot_medical_card_expiry":
    case "start_date":
    case "end_date":
      return formatDateAsTyped(value);
    default:
      return value;
  }
}

export function blurNormalize(field: string, value: string): string {
  switch (field) {
    case "first_name":
    case "middle_name":
    case "last_name":
    case "emergency_contact_name":
    case "full_name":
    case "supervisor_name":
    case "company_name":
      return preserveName(value);
    case "address_street":
    case "address_city":
      return preserveAddress(value);
    case "email":
      return normalizeEmail(value);
    case "phone":
    case "emergency_contact_phone":
    case "supervisor_phone":
      return normalizePhoneInput(value);
    default:
      return liveNormalize(field, value);
  }
}
