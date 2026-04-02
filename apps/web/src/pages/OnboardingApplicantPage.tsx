import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  getPersonApplicationByOnboardingToken,
  getPersonApplicationFileThumbnail,
  uploadPersonApplicationDlFile,
  uploadPersonApplicationDocument,
  submitPersonApplication,
  savePersonApplicationIntake,
  resetPersonApplicationDraft,
  type PersonApplication,
} from "../api";
import DLUploadStep from "../components/DLUploadStep";

type Step = 0 | 1 | 2 | 3;
type DlUiState = "IDLE" | "UPLOADING" | "SCANNING" | "SUCCESS" | "FAILED";
type DocType = "CDL_FRONT" | "CDL_BACK";

type JobEntry = {
  company_name: string; position_title: string; start_date: string; end_date: string;
  reason_for_leaving: string; supervisor_name: string; supervisor_phone: string;
  equipment_operated: string; city_state: string; subject_to_fmcsa: string;
};

type RefEntry = {
  full_name: string; relationship: string; company: string;
  phone: string; email: string; known_duration: string;
};

const STEPS = ["LICENSE UPLOAD", "PERSONAL INFO", "WORK HISTORY & REFS", "DOCUMENTS"] as const;

const EMPTY_JOB: JobEntry = {
  company_name: "", position_title: "", start_date: "", end_date: "",
  reason_for_leaving: "", supervisor_name: "", supervisor_phone: "",
  equipment_operated: "", city_state: "", subject_to_fmcsa: "",
};

const EMPTY_REF: RefEntry = {
  full_name: "", relationship: "", company: "", phone: "", email: "", known_duration: "",
};

const EMPTY_FORM = {
  first_name: "", middle_name: "", last_name: "", date_of_birth: "",
  ssn: "", nationality: "", email: "", phone: "", address_street: "",
  address_city: "", address_region: "", address_postal: "", address_country: "US",
  driver_license_number: "", license_region: "", license_expiry: "", license_issue_date: "",
  cdl_class: "", endorsements: "", restrictions: "", conditions: "",
  sex: "", height: "",
  years_experience: "", total_miles: "",
  equipment_types: "", accidents_last_3_years: "", violations_last_3_years: "",
  dot_medical_card_expiry: "", emergency_contact_name: "",
  emergency_contact_relationship: "", emergency_contact_phone: "",
};

const US_STATES: Record<string, string> = {
  AL:"Alabama",AK:"Alaska",AZ:"Arizona",AR:"Arkansas",CA:"California",CO:"Colorado",
  CT:"Connecticut",DE:"Delaware",FL:"Florida",GA:"Georgia",HI:"Hawaii",ID:"Idaho",
  IL:"Illinois",IN:"Indiana",IA:"Iowa",KS:"Kansas",KY:"Kentucky",LA:"Louisiana",
  ME:"Maine",MD:"Maryland",MA:"Massachusetts",MI:"Michigan",MN:"Minnesota",
  MS:"Mississippi",MO:"Missouri",MT:"Montana",NE:"Nebraska",NV:"Nevada",
  NH:"New Hampshire",NJ:"New Jersey",NM:"New Mexico",NY:"New York",
  NC:"North Carolina",ND:"North Dakota",OH:"Ohio",OK:"Oklahoma",OR:"Oregon",
  PA:"Pennsylvania",RI:"Rhode Island",SC:"South Carolina",SD:"South Dakota",
  TN:"Tennessee",TX:"Texas",UT:"Utah",VT:"Vermont",VA:"Virginia",
  WA:"Washington",WV:"West Virginia",WI:"Wisconsin",WY:"Wyoming",
};

const CA_PROVINCES: Record<string, string> = {
  AB:"Alberta",BC:"British Columbia",MB:"Manitoba",NB:"New Brunswick",
  NL:"Newfoundland and Labrador",NS:"Nova Scotia",NT:"Northwest Territories",
  NU:"Nunavut",ON:"Ontario",PE:"Prince Edward Island",QC:"Quebec",
  SK:"Saskatchewan",YT:"Yukon",
};

function confidenceLabel(conf: unknown): "High" | "Med" | "Low" | null {
  const n = typeof conf === "number" ? conf : Number(conf);
  if (!Number.isFinite(n)) return null;
  if (n >= 0.9) return "High";
  if (n >= 0.75) return "Med";
  return "Low";
}

function getIntake(app: PersonApplication | null): Record<string, any> {
  return (app?.intake_payload as any) || {};
}

function cleanDlText(value: unknown): string {
  if (typeof value !== "string") return "";
  return value
    .replace(/<LF>/g, " ")
    .replace(/<CR>/g, " ")
    .replace(/\r/g, " ")
    .replace(/\n/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function pickCleanIntakeValue(intake: Record<string, any>, prev: string, ...keys: string[]): string {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(intake, key)) {
      const cleaned = cleanDlText(intake[key]);
      return cleaned;
    }
  }
  return prev;
}

function formatDateAsTyped(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 4) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 4)}-${digits.slice(4)}`;
  return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6, 8)}`;
}

function hasReadableValue(value: unknown): boolean {
  return cleanDlText(value).length > 0;
}

function shouldShowDlSource(source: unknown, edited: boolean | undefined, value: unknown): boolean {
  return Boolean(source) && !edited && hasReadableValue(value);
}

function mergeFormWithIntake(prev: Record<string, string>, intake: Record<string, any>) {
  return {
    ...prev,
    first_name: pickCleanIntakeValue(intake, prev.first_name, "first_name"),
    middle_name: pickCleanIntakeValue(intake, prev.middle_name, "middle_name"),
    last_name: pickCleanIntakeValue(intake, prev.last_name, "last_name"),
    email: pickCleanIntakeValue(intake, prev.email, "email"),
    phone: pickCleanIntakeValue(intake, prev.phone, "phone"),
    driver_license_number: pickCleanIntakeValue(intake, prev.driver_license_number, "license_number", "driver_license_number"),
    license_region: pickCleanIntakeValue(intake, prev.license_region, "license_region", "license_state"),
    license_expiry: pickCleanIntakeValue(intake, prev.license_expiry, "license_expiry"),
    license_issue_date: pickCleanIntakeValue(intake, prev.license_issue_date, "license_issue_date", "issue_date"),
    cdl_class: pickCleanIntakeValue(intake, prev.cdl_class, "license_class", "cdl_class"),
    endorsements: pickCleanIntakeValue(intake, prev.endorsements, "endorsements"),
    restrictions: pickCleanIntakeValue(intake, prev.restrictions, "restrictions"),
    conditions: pickCleanIntakeValue(intake, prev.conditions, "conditions"),
    sex: pickCleanIntakeValue(intake, prev.sex, "sex"),
    height: pickCleanIntakeValue(intake, prev.height, "height"),
    address_street: pickCleanIntakeValue(intake, prev.address_street, "address_line", "address_street"),
    address_city: pickCleanIntakeValue(intake, prev.address_city, "address_city"),
    address_region: pickCleanIntakeValue(intake, prev.address_region, "address_region"),
    address_postal: pickCleanIntakeValue(intake, prev.address_postal, "address_postal"),
    address_country: pickCleanIntakeValue(intake, prev.address_country, "address_country", "form_country_default"),
    date_of_birth: pickCleanIntakeValue(intake, prev.date_of_birth, "date_of_birth"),
  };
}

function userFacingErrorMessage(error: unknown, fallback: string): string {
  const raw = typeof error === "string" ? error : (error as any)?.message;
  const status = Number((error as any)?.status);
  const message = typeof raw === "string" ? raw.trim() : "";
  if (status === 413) {
    return "This image file is too large. Please upload a smaller image.";
  }
  if (!message) return fallback;

  const lower = message.toLowerCase();
  if (
    lower.includes("413") ||
    lower.includes("request entity too large") ||
    lower.includes("payload too large") ||
    lower.includes("too large body")
  ) {
    return "This image file is too large. Please upload a smaller image.";
  }
  if (
    lower.includes("<html") ||
    lower.includes("<!doctype") ||
    lower.includes("504") ||
    lower.includes("gateway time-out") ||
    lower.includes("gateway timeout") ||
    lower.includes("timed out")
  ) {
    return "This upload is taking longer than expected. Please wait a moment and try again.";
  }
  if (lower.includes("failed to fetch") || lower.includes("networkerror")) {
    return "We could not reach the server. Please check your connection and try again.";
  }
  if (lower.includes("invalid or expired invite")) {
    return "This onboarding link has expired. Please request a new one.";
  }
  if (lower.includes("application already submitted")) {
    return "This application has already been submitted.";
  }
  if (
    lower.includes("could not read license") ||
    lower.includes("cannot read") ||
    lower.includes("license_extract_error") ||
    lower.includes("traceback") ||
    message.startsWith("{") ||
    message.startsWith("<")
  ) {
    return fallback;
  }
  return message.length > 180 ? fallback : message;
}

function ProgressBar({ step }: { step: Step }) {
  return (
    <div className="flex items-start gap-0 mb-10 relative">
      <div className="absolute top-5 left-5 right-5 h-0.5 bg-gray-700 z-0" />
      <div
        className="absolute top-5 left-5 h-0.5 bg-gradient-to-r from-orange-500 to-red-600 z-10 transition-all duration-500"
        style={{ width: step === 0 ? "0%" : step === 1 ? "33%" : step === 2 ? "66%" : "99%" }}
      />
      {STEPS.map((label, i) => (
        <div key={i} className="flex-1 flex flex-col items-center gap-2 relative z-20">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold transition-all duration-300 ${
            i < step ? "bg-green-500 text-black" : i === step ? "bg-orange-500 text-black shadow-lg shadow-orange-500/40" : "bg-gray-800 border border-gray-600 text-gray-400"
          }`}>
            {i < step ? "✓" : i + 1}
          </div>
          <span className={`text-center text-xs font-semibold tracking-wide uppercase ${
            i === step ? "text-orange-400" : i < step ? "text-green-400" : "text-gray-500"
          }`} style={{ fontSize: 10 }}>{label}</span>
        </div>
      ))}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 mb-4">
      <div className="w-1 h-5 bg-orange-500 rounded" />
      <h3 className="text-orange-400 font-bold uppercase tracking-widest text-sm">{children}</h3>
    </div>
  );
}

function Field({ label, children, half }: { label: string; children: React.ReactNode; half?: boolean }) {
  return (
    <div className={half ? "col-span-1" : "col-span-2 sm:col-span-1"}>
      <label className="block text-xs font-semibold uppercase tracking-widest text-gray-400 mb-1">{label}</label>
      {children}
    </div>
  );
}

const inp = "w-full rounded-lg border border-gray-600 bg-gray-700/50 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500";
const inpErr = "border-rose-500 ring-2 ring-rose-500/50 focus:ring-rose-500 focus:border-rose-500";
const sel = inp + " appearance-none";

function FromDlTag({ confidence }: { confidence: unknown }) {
  const label = confidenceLabel(confidence);
  const dot = label === "High" ? "bg-emerald-500" : label === "Med" ? "bg-yellow-500" : "bg-orange-500";
  return (
    <span className="inline-flex min-h-6 items-center gap-1 rounded-full border border-gray-600 bg-gray-700/50 px-2 py-0.5 text-xs text-gray-300 mb-1">
      <span className={`h-2 w-2 rounded-full ${dot}`} /> From DL{label ? ` (${label})` : ""}
    </span>
  );
}

function DlSourceSlot({
  visible,
  confidence,
}: {
  visible: boolean;
  confidence: unknown;
}) {
  return (
    <div className="mb-1 min-h-6">
      {visible ? <FromDlTag confidence={confidence} /> : null}
    </div>
  );
}

function TypedDateInput({
  value,
  onChange,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  className: string;
}) {
  return (
    <input
      className={className}
      type="text"
      inputMode="numeric"
      maxLength={10}
      placeholder="YYYY-MM-DD"
      value={value}
      onChange={(e) => onChange(formatDateAsTyped(e.target.value))}
    />
  );
}

export default function OnboardingApplicantPage() {
  const [searchParams] = useSearchParams();
  const token = (searchParams.get("token") || "").trim();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [app, setApp] = useState<PersonApplication | null>(null);
  const [step, setStep] = useState<Step>(0);
  const [saving, setSaving] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const [dlState, setDlState] = useState<Record<DocType, DlUiState>>({ CDL_FRONT: "IDLE", CDL_BACK: "IDLE" });
  const [dlMessage, setDlMessage] = useState<Record<DocType, string>>({ CDL_FRONT: "", CDL_BACK: "" });
  const [previewUrl, setPreviewUrl] = useState<Record<DocType, string | null>>({ CDL_FRONT: null, CDL_BACK: null });
  const previewRef = useRef(previewUrl);
  previewRef.current = previewUrl;

  // Step 2 local state
  const [form, setForm] = useState({ ...EMPTY_FORM });

  // Step 3 local state
  const [jobs, setJobs] = useState<JobEntry[]>([{ ...EMPTY_JOB }]);
  const [refs, setRefs] = useState<RefEntry[]>([{ ...EMPTY_REF }, { ...EMPTY_REF }]);

  // Step 4 local state
  const [docUploaded, setDocUploaded] = useState<Record<string, string>>({});
  const [docUploading, setDocUploading] = useState<string | null>(null);
  const [agree1, setAgree1] = useState(false);
  const [agree2, setAgree2] = useState(false);
  const [agree3, setAgree3] = useState(false);

  // When Next is clicked and validation fails, show red borders on missing/wrong fields
  const [showValidationStep0, setShowValidationStep0] = useState(false);
  const [showValidationStep1, setShowValidationStep1] = useState(false);
  const [showValidationStep2, setShowValidationStep2] = useState(false);

  useEffect(() => {
    return () => {
      (["CDL_FRONT", "CDL_BACK"] as DocType[]).forEach((d) => {
        const u = previewRef.current[d];
        if (u?.startsWith("blob:")) URL.revokeObjectURL(u);
      });
    };
  }, []);

  useEffect(() => {
    if (!token) { setLoading(false); setError("No token in URL. Use the link from your invite."); return; }
    let cancelled = false;
    (async () => {
      try {
        const data = await getPersonApplicationByOnboardingToken(token);
        if (cancelled) return;
        setApp(data);
        const intake = (data.intake_payload as any) || {};
        setForm((f) => mergeFormWithIntake({
          ...f,
          email: data.email || intake.email || f.email,
          phone: data.phone || intake.phone || f.phone,
        }, intake));
        setPreviewUrl((prev) => {
          (["CDL_FRONT", "CDL_BACK"] as DocType[]).forEach((docType) => {
            const old = prev[docType];
            if (old?.startsWith("blob:")) URL.revokeObjectURL(old);
          });
          return { CDL_FRONT: null, CDL_BACK: null };
        });
        setDlState({ CDL_FRONT: "IDLE", CDL_BACK: "IDLE" });
        setDlMessage({ CDL_FRONT: "", CDL_BACK: "" });
        if (intake.jobs) setJobs(intake.jobs);
        if (intake.refs) setRefs(intake.refs);
        setSubmitted(data.status === "SUBMITTED");
        const docs = intake.documents as Record<string, { original_filename?: string }> | undefined;
        if (docs && typeof docs === "object") {
          const next: Record<string, string> = {};
          Object.keys(docs).forEach((k) => {
            const name = docs[k]?.original_filename;
            if (name) next[k] = name;
          });
          setDocUploaded((prev) => ({ ...prev, ...next }));
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "Could not load onboarding link");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  const intake = useMemo(() => getIntake(app), [app]);
  const sources = useMemo(() => (intake.field_sources || {}) as Record<string, any>, [intake]);
  const edited = useMemo(() => (intake.user_edited_fields || {}) as Record<string, boolean>, [intake]);

  async function uploadDl(docType: DocType, file: File): Promise<boolean> {
    if (!app) return false;
    setError(null);
    setDlState(s => ({ ...s, [docType]: "UPLOADING" }));
    setDlMessage(m => ({ ...m, [docType]: docType === "CDL_FRONT" ? "Uploading front image..." : "Uploading back image..." }));
    const timer = window.setTimeout(() => {
      setDlState(s => s[docType] === "UPLOADING" ? { ...s, [docType]: "SCANNING" } : s);
      setDlMessage(m => ({
        ...m,
        [docType]: docType === "CDL_BACK" ? "Reading PDF417 barcode..." : "Saving your licence...",
      }));
    }, 600);
    try {
      const resp = await uploadPersonApplicationDlFile({ appId: app.id, onboardingToken: token, docType, file });
      window.clearTimeout(timer);
      const ok = resp.file_id != null;
      setDlState(s => ({ ...s, [docType]: ok ? "SUCCESS" : "FAILED" }));
      setDlMessage(m => ({
        ...m,
        [docType]: ok ? "" : "We could not save this corrected image. Please try again.",
      }));
      setApp(prev => prev ? { ...prev, intake_payload: resp.intake_payload ?? prev.intake_payload } : prev);
      if (ok) {
        const thumbFileId = resp.sanitized_file_id ?? (resp.intake_payload as any)?.files?.[docType]?.enh_file_id ?? resp.file_id!;
        try {
          const thumbUrl = await getPersonApplicationFileThumbnail({ appId: app.id, fileId: thumbFileId, onboardingToken: token });
          setPreviewUrl(prev => {
            const old = prev[docType];
            if (old?.startsWith("blob:")) URL.revokeObjectURL(old);
            return { ...prev, [docType]: thumbUrl };
          });
        } catch {}
        setForm((prev) => mergeFormWithIntake(prev, (resp.intake_payload as Record<string, any>) || {}));
      }
      return ok;
    } catch (e: any) {
      window.clearTimeout(timer);
      setDlState(s => ({ ...s, [docType]: "FAILED" }));
      setError(userFacingErrorMessage(e, "We could not upload your license right now. Please try again."));
      return false;
    }
  }

  async function handleCorrectedDl(side: "front" | "back", blob: Blob, originalName: string): Promise<boolean> {
    const docType: DocType = side === "front" ? "CDL_FRONT" : "CDL_BACK";
    const stem = originalName.replace(/\.[^.]+$/, "") || side;
    const file = new File([blob], `${stem}_corrected.jpg`, { type: "image/jpeg" });
    return uploadDl(docType, file);
  }

  async function resetSavedDraft() {
    if (!app) return;
    const confirmed = window.confirm("Clear all saved onboarding data for this draft and start over?");
    if (!confirmed) return;

    setSaving(true);
    setError(null);
    try {
      const resetApp = await resetPersonApplicationDraft({ appId: app.id, onboardingToken: token });
      const intake = (resetApp.intake_payload as Record<string, any>) || {};
      setApp(resetApp);
      setForm(mergeFormWithIntake({ ...EMPTY_FORM }, intake));
      setJobs([{ ...EMPTY_JOB }]);
      setRefs([{ ...EMPTY_REF }, { ...EMPTY_REF }]);
      setDocUploaded({});
      setDocUploading(null);
      setAgree1(false);
      setAgree2(false);
      setAgree3(false);
      setStep(0);
      setShowValidationStep0(false);
      setShowValidationStep1(false);
      setShowValidationStep2(false);
      setDlState({ CDL_FRONT: "IDLE", CDL_BACK: "IDLE" });
      setDlMessage({ CDL_FRONT: "", CDL_BACK: "" });
      setPreviewUrl((prev) => {
        (["CDL_FRONT", "CDL_BACK"] as DocType[]).forEach((docType) => {
          const old = prev[docType];
          if (old?.startsWith("blob:")) URL.revokeObjectURL(old);
        });
        return { CDL_FRONT: null, CDL_BACK: null };
      });
    } catch (e: any) {
      setError(userFacingErrorMessage(e, "We could not clear the saved onboarding data right now."));
    } finally {
      setSaving(false);
    }
  }

  function canProceedStep0(): boolean {
    const hasFront = dlState.CDL_FRONT === "SUCCESS";
    const hasBack = dlState.CDL_BACK === "SUCCESS";
    const hasLicenseNumber = (form.driver_license_number || "").trim().length > 0;
    const hasRegion = (form.license_region || "").trim().length > 0;
    const hasExpiry = (form.license_expiry || "").trim().length > 0;
    const hasClass = (form.cdl_class || "").trim().length > 0;
    const allFieldsFilled = hasLicenseNumber && hasRegion && hasExpiry && hasClass;
    return hasFront && hasBack && allFieldsFilled;
  }

  function step0ValidationMessage(): string {
    const missing: string[] = [];
    if (dlState.CDL_FRONT !== "SUCCESS") missing.push("front of driver license");
    if (dlState.CDL_BACK !== "SUCCESS") missing.push("back of driver license");
    if (!(form.driver_license_number || "").trim()) missing.push("License Number");
    if (!(form.license_region || "").trim()) missing.push("State/Province Issued");
    if (!(form.license_expiry || "").trim()) missing.push("Expiry Date");
    if (!(form.cdl_class || "").trim()) missing.push("CDL Class");
    return `Please upload both sides of your driver license and complete all license detail fields before continuing. Missing: ${missing.join(", ")}.`;
  }

  function canProceedStep1(): boolean {
    const trim = (s: string) => (s || "").trim();
    return (
      trim(form.first_name).length > 0 &&
      trim(form.last_name).length > 0 &&
      trim(form.email).length > 0 &&
      trim(form.phone).length > 0 &&
      trim(form.address_street).length > 0 &&
      trim(form.address_city).length > 0 &&
      (trim(form.address_region).length > 0 || trim(form.address_postal).length > 0) &&
      trim(form.address_country).length > 0
    );
  }

  function step1ValidationMessage(): string {
    const missing: string[] = [];
    if (!(form.first_name || "").trim()) missing.push("First Name");
    if (!(form.last_name || "").trim()) missing.push("Last Name");
    if (!(form.email || "").trim()) missing.push("Email");
    if (!(form.phone || "").trim()) missing.push("Phone");
    if (!(form.address_street || "").trim()) missing.push("Street Address");
    if (!(form.address_city || "").trim()) missing.push("City");
    if (!(form.address_region || "").trim() && !(form.address_postal || "").trim()) missing.push("State/Region or Postal Code");
    if (!(form.address_country || "").trim()) missing.push("Country");
    return `Please complete all required personal information fields before continuing. Missing: ${missing.join(", ")}.`;
  }

  function canProceedStep2(): boolean {
    const atLeastOneJob = jobs.some(
      (j) =>
        (j.company_name || "").trim() &&
        (j.position_title || "").trim() &&
        (j.start_date || "").trim()
    );
    const twoRefs = refs.length >= 2 && refs.every((r) => (r.full_name || "").trim() && ((r.phone || "").trim() || (r.email || "").trim()));
    return atLeastOneJob && twoRefs;
  }

  function step2ValidationMessage(): string {
    const missing: string[] = [];
    if (!jobs.some((j) => (j.company_name || "").trim() && (j.position_title || "").trim() && (j.start_date || "").trim())) {
      missing.push("at least one employer with Company, Position, and Start Date");
    }
    if (refs.length < 2 || !refs.every((r) => (r.full_name || "").trim() && ((r.phone || "").trim() || (r.email || "").trim()))) {
      missing.push("two professional references with name and contact (phone or email)");
    }
    return `Please complete work history and references before continuing. Missing: ${missing.join("; ")}.`;
  }

  async function saveAndNext(nextStep: Step) {
    if (!app) return;
    if (step === 0 && !canProceedStep0()) {
      setShowValidationStep0(true);
      setError(step0ValidationMessage());
      return;
    }
    if (step === 1 && !canProceedStep1()) {
      setShowValidationStep1(true);
      setError(step1ValidationMessage());
      return;
    }
    if (step === 2 && !canProceedStep2()) {
      setShowValidationStep2(true);
      setError(step2ValidationMessage());
      return;
    }
    setSaving(true);
    setError(null);
    setShowValidationStep0(false);
    setShowValidationStep1(false);
    setShowValidationStep2(false);
    try {
      const payload: Record<string, unknown> = {
        ...((app.intake_payload as any) || {}),
        ...form,
        // Sync form field names to intake keys so load and backend see all license fields
        license_number: form.driver_license_number,
        license_state: form.license_region,
        license_expiry: form.license_expiry,
        license_issue_date: form.license_issue_date,
        license_class: form.cdl_class,
        jobs,
        refs,
        agree_info_accurate: agree1,
        agree_background_check: agree2,
        agree_dot_compliance: agree3,
      };
      const updated = await savePersonApplicationIntake({ appId: app.id, onboardingToken: token, intakePayload: payload });
      setApp(updated);
      setStep(nextStep);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e: any) {
      setError(e?.message || "Failed to save. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit() {
    if (!app || submitted) return;
    if (!agree1 || !agree2 || !agree3) { setError("Please check all agreement boxes before submitting."); return; }
    setSaving(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        ...((app.intake_payload as any) || {}),
        ...form,
        license_number: form.driver_license_number,
        license_state: form.license_region,
        license_expiry: form.license_expiry,
        license_issue_date: form.license_issue_date,
        license_class: form.cdl_class,
        jobs, refs,
        agree_info_accurate: agree1,
        agree_background_check: agree2,
        agree_dot_compliance: agree3,
      };
      const updated = await submitPersonApplication({ appId: app.id, onboardingToken: token, intakePayload: payload });
      setApp(updated);
      setSubmitted(true);
    } catch (e: any) {
      setError(e?.message || "Submit failed");
    } finally {
      setSaving(false);
    }
  }

  function setF(key: string, val: string) { setForm(f => ({ ...f, [key]: val })); }
  function setJob(i: number, key: keyof JobEntry, val: string) { setJobs(j => j.map((x, idx) => idx === i ? { ...x, [key]: val } : x)); }
  function setRef(i: number, key: keyof RefEntry, val: string) { setRefs(r => r.map((x, idx) => idx === i ? { ...x, [key]: val } : x)); }

  if (loading) return <div className="min-h-screen bg-gray-900 flex items-center justify-center text-gray-400">Loading…</div>;

  const isDriver = (app?.application_type || "DRIVER") === "DRIVER";
  const appTitle = isDriver ? "Driver Onboarding" : `${app?.application_type || "Application"} Application`;

  if (error && !app) return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-6">
      <div className="max-w-md w-full rounded-xl border border-gray-600 bg-gray-800 p-6">
        <h1 className="text-lg font-semibold text-white">Application</h1>
        <p className="mt-2 text-sm text-rose-400">{error}</p>
      </div>
    </div>
  );

  if (submitted) return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-6">
      <div className="text-center max-w-md">
        <div className="text-7xl mb-6">{isDriver ? "🚛" : "✓"}</div>
        <h2 className="text-4xl font-black text-green-400 uppercase tracking-widest mb-4">Application Submitted!</h2>
        <p className="text-gray-400 text-sm leading-relaxed">Your application has been received. Our team will review it and be in touch within 2–3 business days.</p>
        <div className="mt-6 inline-block bg-green-500/10 border border-green-500/30 rounded-xl px-6 py-3 text-green-400 font-mono font-bold tracking-widest text-lg">
          ID: {app?.id}
        </div>
      </div>
    </div>
  );

  async function handleMinimalSave() {
    if (!app) return;
    if (!canProceedStep1()) {
      setShowValidationStep1(true);
      setError(step1ValidationMessage());
      return;
    }
    setSaving(true);
    setError(null);
    setShowValidationStep1(false);
    try {
      const payload = {
        first_name: form.first_name,
        last_name: form.last_name,
        phone: form.phone,
        email: form.email,
        address_street: form.address_street,
        address_city: form.address_city,
        address_region: form.address_region,
        address_postal: form.address_postal,
        address_country: form.address_country,
        notes: form.notes,
      };
      const updated = await savePersonApplicationIntake({ appId: app.id, onboardingToken: token, intakePayload: payload });
      setApp(updated);
    } catch (e: any) {
      setError(e?.message || "Failed to save.");
    } finally {
      setSaving(false);
    }
  }

  async function handleMinimalSubmit() {
    if (!app) return;
    if (!canProceedStep1()) {
      setShowValidationStep1(true);
      setError(step1ValidationMessage());
      return;
    }
    setSaving(true);
    setError(null);
    setShowValidationStep1(false);
    try {
      const payload = {
        first_name: form.first_name,
        last_name: form.last_name,
        phone: form.phone,
        email: form.email,
        address_street: form.address_street,
        address_city: form.address_city,
        address_region: form.address_region,
        address_postal: form.address_postal,
        address_country: form.address_country,
        notes: form.notes,
      };
      const updated = await submitPersonApplication({ appId: app.id, onboardingToken: token, intakePayload: payload });
      setApp(updated);
      setSubmitted(true);
    } catch (e: any) {
      setError(e?.message || "Submit failed");
    } finally {
      setSaving(false);
    }
  }

  if (!isDriver) {
    return (
      <div className="min-h-screen bg-gray-900 bg-[linear-gradient(rgba(255,255,255,.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.02)_1px,transparent_1px)] bg-[size:24px_24px] p-4 sm:p-8">
        <div className="mx-auto max-w-2xl">
          <div className="mb-8">
            <h1 className="text-3xl font-black uppercase tracking-widest text-white">
              <span className="text-orange-400">{app?.application_type || "Application"}</span> Application
            </h1>
            <p className="text-gray-500 text-sm mt-1">Complete your application details</p>
          </div>
          {error && <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-400">{error}</div>}
          <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-6 space-y-6">
            <SectionTitle>Contact &amp; Address</SectionTitle>
            <div className="grid grid-cols-2 gap-4">
              <Field label="First Name">
                <input className={`${inp} ${showValidationStep1 && !(form.first_name || "").trim() ? inpErr : ""}`} value={form.first_name} onChange={e => setF("first_name", e.target.value)} placeholder="First Name" />
              </Field>
              <Field label="Last Name">
                <input className={`${inp} ${showValidationStep1 && !(form.last_name || "").trim() ? inpErr : ""}`} value={form.last_name} onChange={e => setF("last_name", e.target.value)} placeholder="Last Name" />
              </Field>
              <Field label="Email">
                <input className={`${inp} ${showValidationStep1 && !(form.email || "").trim() ? inpErr : ""}`} type="email" value={form.email} onChange={e => setF("email", e.target.value)} placeholder="you@email.com" />
              </Field>
              <Field label="Phone">
                <input className={`${inp} ${showValidationStep1 && !(form.phone || "").trim() ? inpErr : ""}`} type="tel" value={form.phone} onChange={e => setF("phone", e.target.value)} placeholder="(555) 000-0000" />
              </Field>
              <div className="col-span-2">
                <Field label="Street Address">
                  <input className={`${inp} ${showValidationStep1 && !(form.address_street || "").trim() ? inpErr : ""}`} value={form.address_street} onChange={e => setF("address_street", e.target.value)} placeholder="Street Address" />
                </Field>
              </div>
              <Field label="City">
                <input className={`${inp} ${showValidationStep1 && !(form.address_city || "").trim() ? inpErr : ""}`} value={form.address_city} onChange={e => setF("address_city", e.target.value)} placeholder="City" />
              </Field>
              <Field label="Region / State">
                <input className={inp} value={form.address_region} onChange={e => setF("address_region", e.target.value)} placeholder="State or Province" />
              </Field>
              <Field label="Postal / ZIP">
                <input className={inp} value={form.address_postal} onChange={e => setF("address_postal", e.target.value)} placeholder="Postal Code" />
              </Field>
              <Field label="Country">
                <input className={`${inp} ${showValidationStep1 && !(form.address_country || "").trim() ? inpErr : ""}`} value={form.address_country} onChange={e => setF("address_country", e.target.value)} placeholder="e.g. US" />
              </Field>
              <div className="col-span-2">
                <Field label="Notes (optional)">
                  <textarea className={inp} rows={2} value={form.notes} onChange={e => setF("notes", e.target.value)} placeholder="Any additional notes" />
                </Field>
              </div>
            </div>
            <div className="flex gap-3 pt-4">
              <button onClick={handleMinimalSave} disabled={saving} className="rounded-xl border border-gray-600 px-4 py-3 text-sm font-medium text-gray-400 hover:bg-gray-800 disabled:opacity-50">
                {saving ? "Saving…" : "Save draft"}
              </button>
              <button onClick={handleMinimalSubmit} disabled={saving} className="rounded-xl bg-orange-500 px-6 py-3 text-sm font-bold uppercase tracking-widest text-black hover:bg-orange-400 disabled:opacity-50">
                {saving ? "Submitting…" : "Submit application"}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 bg-[linear-gradient(rgba(255,255,255,.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.02)_1px,transparent_1px)] bg-[size:24px_24px] p-4 sm:p-8">
      <div className="mx-auto max-w-3xl">
        <div className="mb-8">
          <h1 className="text-3xl font-black uppercase tracking-widest text-white">Driver <span className="text-orange-400">Onboarding</span></h1>
          <p className="text-gray-500 text-sm mt-1">Complete all steps to submit your application</p>
        </div>

        <ProgressBar step={step} />

        {error && <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-400">{error}</div>}

        {/* ── STEP 1: LICENSE UPLOAD ── */}
        {step === 0 && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-2xl font-black text-white uppercase tracking-wide">Driver's <span className="text-orange-400">License</span></h2>
                <p className="text-gray-400 text-sm mt-1">Upload both sides of your current valid commercial driver's license</p>
                <p className="text-amber-300 text-xs mt-2">Each file must not exceed 10 MB.</p>
              </div>
              <button
                type="button"
                onClick={() => void resetSavedDraft()}
                disabled={saving}
                className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-xs font-bold uppercase tracking-widest text-rose-300 transition-all hover:bg-rose-500/20 disabled:opacity-50"
              >
                {saving ? "Clearing..." : "Clear Saved Data"}
              </button>
            </div>
            <DLUploadStep
              frontPreviewUrl={previewUrl.CDL_FRONT}
              backPreviewUrl={previewUrl.CDL_BACK}
              frontState={dlState.CDL_FRONT}
              backState={dlState.CDL_BACK}
              frontMessage={dlMessage.CDL_FRONT}
              backMessage={dlMessage.CDL_BACK}
              onConfirmSide={handleCorrectedDl}
            />
            <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-6 space-y-6 mt-4">
              <SectionTitle>License Details</SectionTitle>
              <div className="grid grid-cols-2 gap-4">

                {/* Country selector — always shown first */}
                <div className="col-span-2">
                  <Field label="Country">
                    <select className={sel} value={form.address_country}
                      onChange={e => { setF("address_country", e.target.value); setF("address_region", ""); setF("license_region", ""); }}>
                      <option value="US">🇺🇸 United States</option>
                      <option value="CA">🇨🇦 Canada</option>
                    </select>
                  </Field>
                </div>

                {/* License Number */}
                <Field label="License Number">
                  <DlSourceSlot visible={shouldShowDlSource(sources.license_number, edited.license_number, form.driver_license_number)} confidence={sources.license_number?.confidence} />
                  <input className={`${inp} ${showValidationStep0 && !(form.driver_license_number || "").trim() ? inpErr : ""}`} value={form.driver_license_number}
                    onChange={e => setF("driver_license_number", e.target.value)}
                    placeholder={form.address_country === "CA" ? "e.g. K35587-56016-90112" : "e.g. DL12345678"} />
                </Field>

                {/* Province/State Issued */}
                <Field label={form.address_country === "CA" ? "Province Issued" : "State Issued"}>
                  <DlSourceSlot visible={shouldShowDlSource(sources.license_state, edited.license_state, form.license_region)} confidence={sources.license_state?.confidence} />
                  <select className={`${sel} ${showValidationStep0 && !(form.license_region || "").trim() ? inpErr : ""}`} value={form.license_region}
                    onChange={e => setF("license_region", e.target.value)}>
                    <option value="">{form.address_country === "CA" ? "Select Province" : "Select State"}</option>
                    {form.address_country === "CA"
                      ? Object.entries(CA_PROVINCES).map(([code, name]) => <option key={code} value={code}>{name}</option>)
                      : Object.entries(US_STATES).map(([code, name]) => <option key={code} value={code}>{name}</option>)
                    }
                  </select>
                </Field>

                {/* Expiry Date */}
                <Field label="Expiry Date">
                  <DlSourceSlot visible={shouldShowDlSource(sources.license_expiry, edited.license_expiry, form.license_expiry)} confidence={sources.license_expiry?.confidence} />
                  <TypedDateInput className={`${inp} ${showValidationStep0 && !(form.license_expiry || "").trim() ? inpErr : ""}`} value={form.license_expiry}
                    onChange={value => setF("license_expiry", value)} />
                </Field>

                {/* Issue Date */}
                <Field label="Issue Date">
                  <DlSourceSlot visible={shouldShowDlSource(sources.license_issue_date, edited.license_issue_date, form.license_issue_date)} confidence={sources.license_issue_date?.confidence} />
                  <TypedDateInput className={inp} value={form.license_issue_date}
                    onChange={value => setF("license_issue_date", value)} />
                </Field>

                {/* Class — free text, prepopulated from extraction, applicant can correct */}
                <Field label={form.address_country === "CA" ? "Licence Class (e.g. A, AC)" : "CDL Class (e.g. A, B, C)"}>
                  <DlSourceSlot visible={shouldShowDlSource(sources.license_class, edited.license_class, form.cdl_class)} confidence={sources.license_class?.confidence} />
                  <input className={`${inp} ${showValidationStep0 && !(form.cdl_class || "").trim() ? inpErr : ""}`} value={form.cdl_class}
                    onChange={e => setF("cdl_class", e.target.value)}
                    placeholder={form.address_country === "CA" ? "e.g. A, AC, G" : "e.g. A, B, C"} />
                </Field>

                {/* Endorsements */}
                <Field label={form.address_country === "CA" ? "Endorsements / Conditions Code" : "Endorsements"}>
                  <DlSourceSlot visible={shouldShowDlSource(sources.endorsements, edited.endorsements, form.endorsements)} confidence={sources.endorsements?.confidence} />
                  <input className={inp} value={form.endorsements}
                    onChange={e => setF("endorsements", e.target.value)}
                    placeholder={form.address_country === "CA" ? "e.g. Z (Air Brakes)" : "e.g. H, N, T, X"} />
                </Field>

                {/* Restrictions */}
                <Field label="Restrictions">
                  <DlSourceSlot visible={shouldShowDlSource(sources.restrictions, edited.restrictions, form.restrictions)} confidence={sources.restrictions?.confidence} />
                  <input className={inp} value={form.restrictions || ""}
                    onChange={e => setF("restrictions", e.target.value)}
                    placeholder="e.g. B, Corrective Lenses" />
                </Field>

                {/* Conditions — Canadian only */}
                {form.address_country === "CA" && (
                  <Field label="Conditions (Canadian licences only)">
                    <DlSourceSlot visible={shouldShowDlSource(sources.conditions, edited.conditions, form.conditions)} confidence={sources.conditions?.confidence} />
                    <input className={inp} value={form.conditions}
                      onChange={e => setF("conditions", e.target.value)}
                      placeholder="e.g. COND" />
                  </Field>
                )}

              </div>
            </div>

            <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-6 space-y-6 mt-4">
              <SectionTitle>Applicant Details From DL</SectionTitle>
              <div className="grid grid-cols-2 gap-4">
                <Field label="First Name">
                  <DlSourceSlot visible={shouldShowDlSource(sources.first_name, edited.first_name, form.first_name)} confidence={sources.first_name?.confidence} />
                  <input className={inp} value={form.first_name} onChange={e => setF("first_name", e.target.value)} placeholder="First Name" />
                </Field>
                <Field label="Last Name">
                  <DlSourceSlot visible={shouldShowDlSource(sources.last_name, edited.last_name, form.last_name)} confidence={sources.last_name?.confidence} />
                  <input className={inp} value={form.last_name} onChange={e => setF("last_name", e.target.value)} placeholder="Last Name" />
                </Field>
                <Field label="Date of Birth">
                  <DlSourceSlot visible={shouldShowDlSource(sources.date_of_birth, edited.date_of_birth, form.date_of_birth)} confidence={sources.date_of_birth?.confidence} />
                  <TypedDateInput className={inp} value={form.date_of_birth} onChange={value => setF("date_of_birth", value)} />
                </Field>
                <Field label="Sex">
                  <DlSourceSlot visible={shouldShowDlSource(sources.sex, edited.sex, form.sex)} confidence={sources.sex?.confidence} />
                  <select className={sel} value={form.sex} onChange={e => setF("sex", e.target.value)}>
                    <option value="">Select</option>
                    <option value="M">Male</option>
                    <option value="F">Female</option>
                    <option value="X">Other / Unspecified</option>
                  </select>
                </Field>
                <Field label="Height">
                  <DlSourceSlot visible={shouldShowDlSource(sources.height, edited.height, form.height)} confidence={sources.height?.confidence} />
                  <input className={inp} value={form.height} onChange={e => setF("height", e.target.value)} placeholder="e.g. 180 cm or 5-11" />
                </Field>
                <Field label="Street Address">
                  <DlSourceSlot visible={shouldShowDlSource(sources.address_line, edited.address_street, form.address_street) || shouldShowDlSource(sources.address_street, edited.address_street, form.address_street)} confidence={sources.address_line?.confidence ?? sources.address_street?.confidence} />
                  <input className={inp} value={form.address_street} onChange={e => setF("address_street", e.target.value)} placeholder="Street Address" />
                </Field>
                <Field label="City">
                  <DlSourceSlot visible={shouldShowDlSource(sources.address_city, edited.address_city, form.address_city)} confidence={sources.address_city?.confidence} />
                  <input className={inp} value={form.address_city} onChange={e => setF("address_city", e.target.value)} placeholder="City" />
                </Field>
                <Field label={form.address_country === "CA" ? "Province / Postal Code" : "State / ZIP Code"}>
                  <DlSourceSlot visible={shouldShowDlSource(sources.address_region, edited.address_region, form.address_region) || shouldShowDlSource(sources.address_postal, edited.address_postal, form.address_postal)} confidence={sources.address_region?.confidence ?? sources.address_postal?.confidence} />
                  <div className="grid grid-cols-2 gap-3">
                    <input className={inp} value={form.address_region} onChange={e => setF("address_region", e.target.value)} placeholder={form.address_country === "CA" ? "Province" : "State"} />
                    <input className={inp} value={form.address_postal} onChange={e => setF("address_postal", e.target.value)} placeholder={form.address_country === "CA" ? "Postal Code" : "ZIP Code"} />
                  </div>
                </Field>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 pt-2">
              {(() => {
                const canGo = canProceedStep0();
                return (
                  <button
                    onClick={() => saveAndNext(1)}
                    disabled={saving}
                    className="flex items-center gap-2 rounded-xl bg-orange-500 px-6 py-3 text-sm font-bold uppercase tracking-widest text-black hover:bg-orange-400 disabled:opacity-50 transition-all"
                  >
                    {saving ? "Saving…" : "Next: Personal Info →"}
                  </button>
                );
              })()}
              {!canProceedStep0() && (
                <span className="text-amber-400 text-sm">Upload both license sides and fill all license details above to continue.</span>
              )}
            </div>
          </div>
        )}

        {/* ── STEP 2: PERSONAL INFO ── */}
        {step === 1 && (
          <div className="space-y-8">
            <div>
              <h2 className="text-2xl font-black text-white uppercase tracking-wide">Personal <span className="text-orange-400">Information</span></h2>
              <p className="text-gray-400 text-sm mt-1">Complete all fields accurately</p>
            </div>
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              All required fields (name, email, phone, full address) must be filled before you can continue to the next step.
            </div>

            <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-6 space-y-6">
              <SectionTitle>Basic Information</SectionTitle>
              <div className="grid grid-cols-2 gap-4">
                <Field label="First Name">
                  {sources.first_name && !edited.first_name && <FromDlTag confidence={sources.first_name?.confidence} />}
                  <input className={`${inp} ${showValidationStep1 && !(form.first_name || "").trim() ? inpErr : ""}`} value={form.first_name} onChange={e => setF("first_name", e.target.value)} placeholder="First Name" />
                </Field>
                <Field label="Middle Name">
                  <input className={inp} value={form.middle_name} onChange={e => setF("middle_name", e.target.value)} placeholder="Middle (optional)" />
                </Field>
                <Field label="Last Name">
                  {sources.last_name && !edited.last_name && <FromDlTag confidence={sources.last_name?.confidence} />}
                  <input className={`${inp} ${showValidationStep1 && !(form.last_name || "").trim() ? inpErr : ""}`} value={form.last_name} onChange={e => setF("last_name", e.target.value)} placeholder="Last Name" />
                </Field>
                <Field label="Date of Birth">
                  {sources.date_of_birth && !edited.date_of_birth && <FromDlTag confidence={sources.date_of_birth?.confidence} />}
                  <input className={inp} type="date" value={form.date_of_birth} onChange={e => setF("date_of_birth", e.target.value)} />
                </Field>
                <Field label="SSN (last 4 optional)">
                  <input className={inp} value={form.ssn} onChange={e => setF("ssn", e.target.value)} placeholder="XXX-XX-XXXX" />
                </Field>
                <Field label="Nationality">
                  <input className={inp} value={form.nationality} onChange={e => setF("nationality", e.target.value)} placeholder="e.g. US Citizen" />
                </Field>

                {/* Sex / Gender */}
                <Field label="Sex / Gender">
                  {sources.sex && !edited.sex && <FromDlTag confidence={sources.sex?.confidence} />}
                  <select className={sel} value={form.sex} onChange={e => setF("sex", e.target.value)}>
                    <option value="">Select</option>
                    <option value="M">Male</option>
                    <option value="F">Female</option>
                    <option value="X">Non-binary / X</option>
                  </select>
                </Field>

                {/* Height */}
                <Field label={form.address_country === "CA" ? "Height (cm)" : "Height (ft/in)"}>
                  {sources.height && !edited.height && <FromDlTag confidence={sources.height?.confidence} />}
                  <input className={inp} value={form.height}
                    onChange={e => setF("height", e.target.value)}
                    placeholder={form.address_country === "CA" ? "e.g. 160 cm" : "e.g. 5'11\""} />
                </Field>
              </div>

              <SectionTitle>Contact Information</SectionTitle>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Email">
                  <input className={`${inp} ${showValidationStep1 && !(form.email || "").trim() ? inpErr : ""}`} type="email" value={form.email} onChange={e => setF("email", e.target.value)} placeholder="you@email.com" />
                </Field>
                <Field label="Phone">
                  <input className={`${inp} ${showValidationStep1 && !(form.phone || "").trim() ? inpErr : ""}`} type="tel" value={form.phone} onChange={e => setF("phone", e.target.value)} placeholder="(555) 000-0000" />
                </Field>
                <div className="col-span-2">
                  <Field label="Street Address">
                    <input className={`${inp} ${showValidationStep1 && !(form.address_street || "").trim() ? inpErr : ""}`} value={form.address_street} onChange={e => setF("address_street", e.target.value)} placeholder="Street Address" />
                  </Field>
                </div>
                <Field label="Country">
                  <select className={`${sel} ${showValidationStep1 && !(form.address_country || "").trim() ? inpErr : ""}`} value={form.address_country} onChange={e => { setF("address_country", e.target.value); setF("address_region", ""); }}>
                    <option value="US">🇺🇸 United States</option>
                    <option value="CA">🇨🇦 Canada</option>
                  </select>
                </Field>
                <Field label="City">
                  <input className={`${inp} ${showValidationStep1 && !(form.address_city || "").trim() ? inpErr : ""}`} value={form.address_city} onChange={e => setF("address_city", e.target.value)} placeholder="City" />
                </Field>
                <Field label={form.address_country === "CA" ? "Province" : "State"}>
                  <select className={`${sel} ${showValidationStep1 && !(form.address_region || "").trim() && !(form.address_postal || "").trim() ? inpErr : ""}`} value={form.address_region} onChange={e => setF("address_region", e.target.value)}>
                    <option value="">{form.address_country === "CA" ? "Select Province" : "Select State"}</option>
                    {form.address_country === "CA"
                      ? Object.entries(CA_PROVINCES).map(([code, name]) => <option key={code} value={code}>{name}</option>)
                      : Object.entries(US_STATES).map(([code, name]) => <option key={code} value={code}>{name}</option>)
                    }
                  </select>
                </Field>
                <Field label={form.address_country === "CA" ? "Postal Code" : "ZIP Code"}>
                  <input className={`${inp} ${showValidationStep1 && !(form.address_region || "").trim() && !(form.address_postal || "").trim() ? inpErr : ""}`} value={form.address_postal} onChange={e => setF("address_postal", e.target.value)} placeholder={form.address_country === "CA" ? "A1A 1A1" : "00000"} />
                </Field>
              </div>

              <SectionTitle>Driving Experience</SectionTitle>
              <div className="grid grid-cols-2 gap-4">
                <Field label="DOT Medical Card Expiry">
                  <input className={inp} type="date" value={form.dot_medical_card_expiry} onChange={e => setF("dot_medical_card_expiry", e.target.value)} />
                </Field>
                <Field label="Years of CDL Experience">
                  <select className={sel} value={form.years_experience} onChange={e => setF("years_experience", e.target.value)}>
                    <option value="">Select</option>
                    <option>Less than 1 year</option>
                    <option>1–2 years</option>
                    <option>2–5 years</option>
                    <option>5–10 years</option>
                    <option>10+ years</option>
                  </select>
                </Field>
                <Field label="Total Miles Driven (approx)">
                  <input className={inp} value={form.total_miles} onChange={e => setF("total_miles", e.target.value)} placeholder="e.g. 500,000" />
                </Field>
                <Field label="Equipment Types">
                  <input className={inp} value={form.equipment_types} onChange={e => setF("equipment_types", e.target.value)} placeholder="e.g. Dry Van, Flatbed" />
                </Field>
                <Field label="Accidents in Last 3 Years?">
                  <select className={sel} value={form.accidents_last_3_years} onChange={e => setF("accidents_last_3_years", e.target.value)}>
                    <option value="">Select</option>
                    <option value="no">No</option>
                    <option value="yes">Yes</option>
                  </select>
                </Field>
                <Field label="Moving Violations in Last 3 Years?">
                  <select className={sel} value={form.violations_last_3_years} onChange={e => setF("violations_last_3_years", e.target.value)}>
                    <option value="">Select</option>
                    <option value="no">No</option>
                    <option value="yes">Yes</option>
                  </select>
                </Field>
              </div>

              <SectionTitle>Emergency Contact</SectionTitle>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Contact Name">
                  <input className={inp} value={form.emergency_contact_name} onChange={e => setF("emergency_contact_name", e.target.value)} placeholder="Full Name" />
                </Field>
                <Field label="Relationship">
                  <input className={inp} value={form.emergency_contact_relationship} onChange={e => setF("emergency_contact_relationship", e.target.value)} placeholder="e.g. Spouse" />
                </Field>
                <Field label="Phone">
                  <input className={inp} value={form.emergency_contact_phone} onChange={e => setF("emergency_contact_phone", e.target.value)} placeholder="(555) 000-0000" />
                </Field>
              </div>
            </div>

            <div className="flex gap-3">
              <button onClick={() => { setStep(0); setShowValidationStep1(false); }} className="rounded-xl border border-gray-600 px-4 py-3 text-sm text-gray-400 hover:bg-gray-800">← Back</button>
              <button onClick={() => saveAndNext(2)} disabled={saving}
                className="rounded-xl bg-orange-500 px-6 py-3 text-sm font-bold uppercase tracking-widest text-black hover:bg-orange-400 disabled:opacity-50">
                {saving ? "Saving…" : "Next: Work History →"}
              </button>
            </div>
          </div>
        )}

        {/* ── STEP 3: WORK HISTORY & REFERENCES ── */}
        {step === 2 && (
          <div className="space-y-8">
            <div>
              <h2 className="text-2xl font-black text-white uppercase tracking-wide">Work History & <span className="text-orange-400">References</span></h2>
              <p className="text-gray-400 text-sm mt-1">List your last 3 employers and 2 professional references</p>
            </div>
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              Add at least one employer (with company, position, start date) and two professional references (with name and contact) before continuing.
            </div>

            <div className="space-y-4">
              <SectionTitle>Employment History</SectionTitle>
              {jobs.map((job, i) => {
                const hasValidJob = jobs.some(j => (j.company_name || "").trim() && (j.position_title || "").trim() && (j.start_date || "").trim());
                const showJobErr = showValidationStep2 && !hasValidJob && (i === 0 || (job.company_name || "").trim() || (job.position_title || "").trim() || (job.start_date || "").trim());
                const err = (key: keyof JobEntry) => showJobErr && !(job[key] || "").trim() ? inpErr : "";
                return (
                <div key={i} className={`rounded-2xl border p-5 relative transition-colors ${showJobErr ? "border-rose-500/60 bg-rose-500/5" : "border-gray-700 bg-gray-800/60"}`}>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-xs font-bold uppercase tracking-widest text-orange-400">Employer {i + 1}</span>
                    {jobs.length > 1 && <button onClick={() => setJobs(j => j.filter((_, idx) => idx !== i))} className="text-xs text-rose-400 hover:text-rose-300 border border-rose-500/30 rounded px-2 py-1">Remove</button>}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Company Name"><input className={`${inp} ${err("company_name")}`} value={job.company_name} onChange={e => setJob(i, "company_name", e.target.value)} placeholder="Company Name" /></Field>
                    <Field label="Position / Title"><input className={`${inp} ${err("position_title")}`} value={job.position_title} onChange={e => setJob(i, "position_title", e.target.value)} placeholder="e.g. OTR Driver" /></Field>
                    <Field label="Start Date"><input className={`${inp} ${err("start_date")}`} type="date" value={job.start_date} onChange={e => setJob(i, "start_date", e.target.value)} /></Field>
                    <Field label="End Date"><input className={inp} type="date" value={job.end_date} onChange={e => setJob(i, "end_date", e.target.value)} /></Field>
                    <Field label="Reason for Leaving"><input className={inp} value={job.reason_for_leaving} onChange={e => setJob(i, "reason_for_leaving", e.target.value)} placeholder="e.g. Better opportunity" /></Field>
                    <Field label="Supervisor Name"><input className={inp} value={job.supervisor_name} onChange={e => setJob(i, "supervisor_name", e.target.value)} placeholder="Supervisor" /></Field>
                    <Field label="Supervisor Phone"><input className={inp} value={job.supervisor_phone} onChange={e => setJob(i, "supervisor_phone", e.target.value)} placeholder="(555) 000-0000" /></Field>
                    <Field label="Equipment Operated"><input className={inp} value={job.equipment_operated} onChange={e => setJob(i, "equipment_operated", e.target.value)} placeholder="e.g. Dry Van 53ft" /></Field>
                    <Field label="City, State"><input className={inp} value={job.city_state} onChange={e => setJob(i, "city_state", e.target.value)} placeholder="City, State" /></Field>
                    <Field label="Subject to FMCSA?">
                      <select className={sel} value={job.subject_to_fmcsa} onChange={e => setJob(i, "subject_to_fmcsa", e.target.value)}>
                        <option value="">Select</option>
                        <option value="yes">Yes</option>
                        <option value="no">No</option>
                      </select>
                    </Field>
                  </div>
                </div>
              );
              })}
              {jobs.length < 5 && (
                <button onClick={() => setJobs(j => [...j, { ...EMPTY_JOB }])}
                  className="w-full rounded-xl border-2 border-dashed border-gray-600 py-3 text-sm text-gray-400 hover:border-orange-500 hover:text-orange-400 transition-all">
                  + Add Another Employer
                </button>
              )}
            </div>

            <div className="space-y-4">
              <SectionTitle>Professional References</SectionTitle>
              {refs.map((ref, i) => {
                const refInvalid = !(ref.full_name || "").trim() || (!(ref.phone || "").trim() && !(ref.email || "").trim());
                const showRefErr = showValidationStep2 && refInvalid;
                const refNameErr = showRefErr && !(ref.full_name || "").trim() ? inpErr : "";
                const refContactErr = showRefErr && !(ref.phone || "").trim() && !(ref.email || "").trim() ? inpErr : "";
                return (
                <div key={i} className={`rounded-2xl border p-5 transition-colors ${showRefErr ? "border-rose-500/60 bg-rose-500/5" : "border-gray-700 bg-gray-800/60"}`}>
                  <span className="text-xs font-bold uppercase tracking-widest text-orange-400 block mb-4">Reference {i + 1}</span>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Full Name"><input className={`${inp} ${refNameErr}`} value={ref.full_name} onChange={e => setRef(i, "full_name", e.target.value)} placeholder="Full Name" /></Field>
                    <Field label="Relationship"><input className={inp} value={ref.relationship} onChange={e => setRef(i, "relationship", e.target.value)} placeholder="e.g. Former Supervisor" /></Field>
                    <Field label="Company"><input className={inp} value={ref.company} onChange={e => setRef(i, "company", e.target.value)} placeholder="Company Name" /></Field>
                    <Field label="Phone"><input className={`${inp} ${refContactErr}`} value={ref.phone} onChange={e => setRef(i, "phone", e.target.value)} placeholder="(555) 000-0000" /></Field>
                    <Field label="Email"><input className={`${inp} ${refContactErr}`} type="email" value={ref.email} onChange={e => setRef(i, "email", e.target.value)} placeholder="email@company.com" /></Field>
                    <Field label="How long known?"><input className={inp} value={ref.known_duration} onChange={e => setRef(i, "known_duration", e.target.value)} placeholder="e.g. 5 years" /></Field>
                  </div>
                </div>
              );
              })}
            </div>

            <div className="flex gap-3">
              <button onClick={() => { setStep(1); setShowValidationStep2(false); }} className="rounded-xl border border-gray-600 px-4 py-3 text-sm text-gray-400 hover:bg-gray-800">← Back</button>
              <button onClick={() => saveAndNext(3)} disabled={saving}
                className="rounded-xl bg-orange-500 px-6 py-3 text-sm font-bold uppercase tracking-widest text-black hover:bg-orange-400 disabled:opacity-50">
                {saving ? "Saving…" : "Next: Documents →"}
              </button>
            </div>
          </div>
        )}

        {/* ── STEP 4: DOCUMENTS & SUBMIT ── */}
        {step === 3 && (
          <div className="space-y-8">
            <div>
              <h2 className="text-2xl font-black text-white uppercase tracking-wide">Required <span className="text-orange-400">Documents</span></h2>
              <p className="text-gray-400 text-sm mt-1">Upload required documents. Optional ones can be added later.</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {[
                { key: "dot_medical", label: "DOT Medical Certificate", desc: "Current DOT physical exam card", required: true, icon: "🏥" },
                { key: "mvr", label: "MVR (Motor Vehicle Record)", desc: "From your state DMV, within 30 days", required: true, icon: "🚛" },
                { key: "drug_test", label: "Drug & Alcohol Test", desc: "Pre-employment test results", required: true, icon: "🧪" },
                { key: "psp_report", label: "PSP Report", desc: "Pre-Employment Screening from FMCSA", required: true, icon: "🔍" },
                { key: "ss_card", label: "Social Security Card", desc: "For I-9 verification", required: false, icon: "🪪" },
                { key: "employment_verification", label: "Employment Verification", desc: "W-2s or verification letters", required: false, icon: "📋" },
                { key: "certificates", label: "Certificates & Training", desc: "HAZMAT, tanker, safety certs", required: false, icon: "🏆" },
                { key: "void_cheque", label: "Void Cheque / Direct Deposit", desc: "For payroll setup", required: false, icon: "📜" },
              ].map(doc => (
                <div key={doc.key} className={`rounded-xl border p-4 relative transition-all ${docUploaded[doc.key] ? "border-green-500/40 bg-green-500/5" : "border-gray-700 bg-gray-800/60 hover:border-gray-500"}`}>
                  {doc.required && !docUploaded[doc.key] && <span className="absolute top-3 right-3 text-xs font-bold text-rose-400 bg-rose-500/10 border border-rose-500/20 px-2 py-0.5 rounded">REQUIRED</span>}
                  {!doc.required && <span className="absolute top-3 right-3 text-xs font-bold text-gray-500 bg-gray-700/50 border border-gray-600 px-2 py-0.5 rounded">OPTIONAL</span>}
                  <div className="text-3xl mb-2">{doc.icon}</div>
                  <div className="font-semibold text-white text-sm mb-1">{doc.label}</div>
                  <div className="text-xs text-gray-400 mb-3">{doc.desc}</div>
                  <label className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium cursor-pointer transition-all ${docUploaded[doc.key] ? "border-green-500/40 text-green-400" : "border-gray-600 text-gray-400 hover:border-orange-500 hover:text-orange-400"} ${docUploading === doc.key ? "opacity-70 pointer-events-none" : ""}`}>
                    <input type="file" accept=".pdf,image/*" className="sr-only"
                      onChange={async (e) => {
                        const f = e.target.files?.[0];
                        if (!f || !app) return;
                        setDocUploading(doc.key);
                        setError(null);
                        try {
                          const updated = await uploadPersonApplicationDocument({ appId: app.id, onboardingToken: token, docType: doc.key, file: f });
                          setApp(updated);
                          setDocUploaded(d => ({ ...d, [doc.key]: f.name }));
                        } catch (err: any) {
                          setError(err?.message || "Upload failed");
                        } finally {
                          setDocUploading(null);
                        }
                      }} />
                    {docUploading === doc.key ? "Uploading…" : docUploaded[doc.key] ? `✓ ${docUploaded[doc.key].substring(0, 24)}` : "📎 Choose File"}
                  </label>
                </div>
              ))}
            </div>

            <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-5 space-y-4">
              <SectionTitle>Agreements & Certification</SectionTitle>
              {[
                { val: agree1, set: setAgree1, text: "I certify that all information provided is true and complete. Any falsification may result in rejection or termination." },
                { val: agree2, set: setAgree2, text: "I authorize the company to contact previous employers, references, and conduct background checks including MVR and PSP reports." },
                { val: agree3, set: setAgree3, text: "I agree to comply with all DOT regulations, company policies, and safety requirements as a condition of employment." },
              ].map((a, i) => (
                <label key={i} className="flex items-start gap-3 cursor-pointer group">
                  <div className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border-2 transition-all ${a.val ? "border-orange-500 bg-orange-500" : "border-gray-500 group-hover:border-gray-400"}`}>
                    {a.val && <svg className="h-3 w-3 text-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                  </div>
                  <input type="checkbox" className="sr-only" checked={a.val} onChange={e => a.set(e.target.checked)} />
                  <span className="text-sm text-gray-300 leading-relaxed">{a.text}</span>
                </label>
              ))}
            </div>

            <div className="flex gap-3">
              <button onClick={() => setStep(2)} className="rounded-xl border border-gray-600 px-4 py-3 text-sm text-gray-400 hover:bg-gray-800">← Back</button>
              <button onClick={handleSubmit} disabled={saving || !agree1 || !agree2 || !agree3}
                className="rounded-xl bg-green-500 px-8 py-3 text-sm font-bold uppercase tracking-widest text-black hover:bg-green-400 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-lg shadow-green-500/20">
                {saving ? "Submitting…" : "Submit Application ✓"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
