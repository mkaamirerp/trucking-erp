import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { useSearchParams } from "react-router-dom";
import {
  getPersonApplicationByOnboardingToken,
  getPersonApplicationFileThumbnail,
  buildApplicantApplicationEventsUrl,
  uploadPersonApplicationDlFile,
  uploadPersonApplicationDocument,
  submitPersonApplication,
  savePersonApplicationIntake,
  resetPersonApplicationDraft,
  type PersonApplication,
} from "../api";
import DLUploadStep from "../components/DLUploadStep";
import { Field, RequiredGlyph, controlClass, selectClass } from "../components/onboardingFields";
import { OnboardingDateField } from "../components/OnboardingDateField";
import { inp } from "../components/onboardingFieldStyles";
import {
  US_STATES,
  CA_PROVINCES,
  type JobEntry,
  type RefEntry,
  type OnboardingSnapshot,
  liveNormalize,
  blurNormalize,
  normalizeSnapshot,
  normalizeForm,
  validateOnboardingStep,
  validateSubmit,
  validateNonDriverContact,
  errorsByField,
  firstErrorMessage,
  displayPhone,
} from "../core/onboardingFieldRules";
import {
  cleanIntakeText,
  hydrateOnboardingFormFromIntake,
  mergeIntakeForSave,
} from "../core/hydrateOnboardingFormFromIntake";
import { confirmPersonApplicationDlSide } from "../lib/applicantDlConfirm";

type Step = 0 | 1 | 2 | 3;
type DlUiState = "IDLE" | "UPLOADING" | "SCANNING" | "SUCCESS" | "FAILED";
type DocType = "CDL_FRONT" | "CDL_BACK";

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
  address_city: "", address_region: "", address_postal: "", zip_code: "", address_country: "US",
  driver_license_number: "", license_region: "", license_expiry: "", license_issue_date: "",
  cdl_class: "", endorsements: "", restrictions: "", conditions: "",
  sex: "", height: "",
  years_experience: "", total_miles: "",
  equipment_types: "", accidents_last_3_years: "", violations_last_3_years: "",
  dot_medical_card_expiry: "", emergency_contact_name: "",
  emergency_contact_relationship: "", emergency_contact_phone: "",
  notes: "",
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

/** Match `uploadPersonApplicationDlFile` — which `file_id` to pass to `/application/file` for previews. */
function resolveDlThumbFileId(docType: DocType, intake: Record<string, any>): string | null {
  const files = intake.files as Record<string, any> | undefined;
  if (!files || typeof files !== "object") return null;
  const fileMeta = files[docType];
  if (!fileMeta || typeof fileMeta !== "object") return null;
  const processedMeta = files[`${docType}_PROCESSED`];
  const fileId = fileMeta.file_id ?? fileMeta.storage_key;
  const id =
    fileMeta.enh_file_id ??
    processedMeta?.enh_file_id ??
    processedMeta?.file_id ??
    processedMeta?.storage_key ??
    fileId;
  return typeof id === "string" && id.length > 0 ? id : null;
}

function hasStoredDlSide(docType: DocType, intake: Record<string, any>): boolean {
  return resolveDlThumbFileId(docType, intake) != null;
}

function dlUiStateFromIntake(intake: Record<string, any>, docType: DocType): DlUiState {
  const meta = intake.files?.[docType];
  if (meta?.dl_preprocess_status === "PROCESSED") return "SUCCESS";
  if (meta?.dl_preprocess_status === "FAILED") return "FAILED";
  if (hasStoredDlSide(docType, intake)) return "SUCCESS";
  return "IDLE";
}

function dlSideConfirmed(intake: Record<string, any>, docType: DocType): boolean {
  return intake?.files?.[docType]?.dl_user_confirmed === true;
}

function applyApplicationDlRefresh(
  data: PersonApplication,
  token: string,
  setPreviewUrl: Dispatch<SetStateAction<Record<DocType, string | null>>>,
): { intake: Record<string, any>; dlState: Record<DocType, DlUiState> } {
  const intake = (data.intake_payload as Record<string, any>) || {};
  const dlState: Record<DocType, DlUiState> = {
    CDL_FRONT: dlUiStateFromIntake(intake, "CDL_FRONT"),
    CDL_BACK: dlUiStateFromIntake(intake, "CDL_BACK"),
  };
  void (async () => {
    const updates: Partial<Record<DocType, string>> = {};
    for (const docType of ["CDL_FRONT", "CDL_BACK"] as DocType[]) {
      const fid = resolveDlThumbFileId(docType, intake);
      if (!fid) continue;
      try {
        const url = await getPersonApplicationFileThumbnail({ appId: data.id, fileId: fid, onboardingToken: token });
        updates[docType] = url;
      } catch {
        /* preview optional */
      }
    }
    if (Object.keys(updates).length > 0) {
      setPreviewUrl((prev) => {
        const next = { ...prev };
        (["CDL_FRONT", "CDL_BACK"] as DocType[]).forEach((d) => {
          const u = updates[d];
          if (u != null) {
            const old = prev[d];
            if (old?.startsWith("blob:")) URL.revokeObjectURL(old);
            next[d] = u;
          }
        });
        return next;
      });
    }
  })();
  return { intake, dlState };
}

function parseOnboardingStep(raw: unknown): Step | null {
  if (typeof raw === "number" && Number.isInteger(raw) && raw >= 0 && raw <= 3) return raw as Step;
  if (typeof raw === "string" && /^[0-3]$/.test(raw)) return Number(raw) as Step;
  return null;
}

function hasReadableValue(value: unknown): boolean {
  return cleanIntakeText(value).length > 0;
}

function shouldShowDlSource(source: unknown, edited: boolean | undefined, value: unknown): boolean {
  return Boolean(source) && !edited && hasReadableValue(value);
}

function dlSourceConfidence(source: unknown): unknown {
  if (!source || typeof source !== "object") return undefined;
  return (source as { confidence?: unknown }).confidence;
}

/** Left-edge accent for unedited DL-filled fields that need review (Low confidence only). */
function dlReviewAccent(source: unknown, edited: boolean | undefined, value: unknown): string {
  if (!shouldShowDlSource(source, edited, value)) return "";
  if (confidenceLabel(dlSourceConfidence(source)) !== "Low") return "";
  return "border-l-4 border-l-orange-500";
}

function dlReviewAccentAny(
  entries: Array<{ source: unknown; edited?: boolean; value: unknown }>,
): string {
  for (const { source, edited, value } of entries) {
    const accent = dlReviewAccent(source, edited, value);
    if (accent) return accent;
  }
  return "";
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

function buildSnapshot(args: {
  form: Record<string, string>;
  jobs: JobEntry[];
  refs: RefEntry[];
  intake: Record<string, any>;
  documents: Record<string, string>;
  agree1: boolean;
  agree2: boolean;
  agree3: boolean;
}): OnboardingSnapshot {
  return {
    form: args.form,
    jobs: args.jobs,
    refs: args.refs,
    dlFrontConfirmed: dlSideConfirmed(args.intake, "CDL_FRONT"),
    dlBackConfirmed: dlSideConfirmed(args.intake, "CDL_BACK"),
    documents: args.documents,
    agreeInfoAccurate: args.agree1,
    agreeBackgroundCheck: args.agree2,
    agreeDotCompliance: args.agree3,
  };
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
  const [documentResumeActive, setDocumentResumeActive] = useState(false);

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

  const resumeDocsOnly = documentResumeActive && submitted;

  // When Next is clicked and validation fails, show red borders on missing/wrong fields
  const [showValidationStep0, setShowValidationStep0] = useState(false);
  const [showValidationStep1, setShowValidationStep1] = useState(false);
  const [showValidationStep2, setShowValidationStep2] = useState(false);
  const [showValidationSubmit, setShowValidationSubmit] = useState(false);

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
        setForm((f) =>
          hydrateOnboardingFormFromIntake(
            {
              ...f,
              email: data.email || cleanIntakeText(intake.email) || f.email,
              phone: data.phone || cleanIntakeText(intake.phone) || f.phone,
            },
            intake,
            "initial",
          ),
        );
        setPreviewUrl((prev) => {
          (["CDL_FRONT", "CDL_BACK"] as DocType[]).forEach((docType) => {
            const old = prev[docType];
            if (old?.startsWith("blob:")) URL.revokeObjectURL(old);
          });
          return { CDL_FRONT: null, CDL_BACK: null };
        });
        setDlState({
          CDL_FRONT: dlUiStateFromIntake(intake, "CDL_FRONT"),
          CDL_BACK: dlUiStateFromIntake(intake, "CDL_BACK"),
        });
        setDlMessage({ CDL_FRONT: "", CDL_BACK: "" });
        if (typeof intake.agree_info_accurate === "boolean") setAgree1(intake.agree_info_accurate);
        if (typeof intake.agree_background_check === "boolean") setAgree2(intake.agree_background_check);
        if (typeof intake.agree_dot_compliance === "boolean") setAgree3(intake.agree_dot_compliance);
        if (intake.jobs) setJobs(intake.jobs);
        if (intake.refs) setRefs(intake.refs);
        setSubmitted(data.status === "SUBMITTED" || data.status === "APPROVED");
        const resume = !!(data as { document_resume_active?: boolean }).document_resume_active;
        setDocumentResumeActive(resume);
        // Document-resume links must open step 3 only; saved onboarding_step is often 0 and would override.
        if ((data.status === "SUBMITTED" || data.status === "APPROVED") && resume) {
          setStep(3);
        } else {
          const restoredStep = parseOnboardingStep(intake.onboarding_step);
          if (restoredStep !== null) setStep(restoredStep);
        }
        const docs = intake.documents as Record<string, { original_filename?: string }> | undefined;
        if (docs && typeof docs === "object") {
          const next: Record<string, string> = {};
          Object.keys(docs).forEach((k) => {
            const name = docs[k]?.original_filename;
            if (name) next[k] = name;
          });
          setDocUploaded((prev) => ({ ...prev, ...next }));
        }

        const appId = data.id;
        (async () => {
          const updates: Partial<Record<DocType, string>> = {};
          for (const docType of ["CDL_FRONT", "CDL_BACK"] as DocType[]) {
            const fid = resolveDlThumbFileId(docType, intake);
            if (!fid) continue;
            try {
              const url = await getPersonApplicationFileThumbnail({ appId, fileId: fid, onboardingToken: token });
              updates[docType] = url;
            } catch {
              /* keep SUCCESS + stored file; preview may stay empty if file fetch fails */
            }
          }
          if (cancelled) return;
          if (Object.keys(updates).length > 0) {
            setPreviewUrl((prev) => {
              const next = { ...prev };
              (["CDL_FRONT", "CDL_BACK"] as DocType[]).forEach((d) => {
                const u = updates[d];
                if (u != null) {
                  const old = prev[d];
                  if (old?.startsWith("blob:")) URL.revokeObjectURL(old);
                  next[d] = u;
                }
              });
              return next;
            });
          }
        })();
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

  const liveSnap = useMemo(
    () =>
      normalizeSnapshot(
        buildSnapshot({
          form,
          jobs,
          refs,
          intake,
          documents: docUploaded,
          agree1,
          agree2,
          agree3,
        }),
      ),
    [form, jobs, refs, intake, docUploaded, agree1, agree2, agree3],
  );
  const fe0 = showValidationStep0 || showValidationSubmit ? errorsByField(validateOnboardingStep(0, liveSnap)) : {};
  const fe1 = showValidationStep1 || showValidationSubmit ? errorsByField(validateOnboardingStep(1, liveSnap)) : {};
  const fe2 = showValidationStep2 || showValidationSubmit ? errorsByField(validateOnboardingStep(2, liveSnap)) : {};
  const fe3 = showValidationSubmit ? errorsByField(validateOnboardingStep(3, liveSnap)) : {};
  const feContact = showValidationStep1 ? errorsByField(validateNonDriverContact(normalizeForm(form))) : {};
  const step0Incomplete = validateOnboardingStep(0, liveSnap).length > 0;

  function handlePhoneApplicationUpdated(data: PersonApplication) {
    setApp(data);
    const { dlState: nextDlState } = applyApplicationDlRefresh(data, token, setPreviewUrl);
    setDlState(nextDlState);
    const extract = (data.intake_payload as Record<string, unknown> | undefined)?.license_extract_status;
    const backConfirmed = dlSideConfirmed((data.intake_payload as Record<string, any>) || {}, "CDL_BACK");
    setDlMessage({
      CDL_FRONT: "",
      CDL_BACK:
        backConfirmed && extract && extract !== "SUCCESS"
          ? "We could not read the barcode on this photo. The photo is saved — upload again or enter details manually."
          : "",
    });
    setForm((prev) =>
      hydrateOnboardingFormFromIntake(prev, (data.intake_payload as Record<string, unknown>) || {}, "after_dl_upload"),
    );
  }

  const refreshInFlightRef = useRef(false);
  const refreshPendingRef = useRef(false);

  const refreshApplicationOnce = useCallback(async (): Promise<void> => {
    if (!token) return;
    if (refreshInFlightRef.current) {
      refreshPendingRef.current = true;
      return;
    }
    refreshInFlightRef.current = true;
    try {
      do {
        refreshPendingRef.current = false;
        const data = await getPersonApplicationByOnboardingToken(token);
        handlePhoneApplicationUpdated(data);
      } while (refreshPendingRef.current);
    } finally {
      refreshInFlightRef.current = false;
    }
  }, [token]);

  useEffect(() => {
    if (!token || resumeDocsOnly || step !== 0 || submitted) return;
    const es = new EventSource(buildApplicantApplicationEventsUrl(token));
    es.onopen = () => {
      void refreshApplicationOnce();
    };
    es.addEventListener("application_changed", () => {
      void refreshApplicationOnce();
    });
    return () => {
      es.close();
    };
  }, [token, resumeDocsOnly, step, submitted, refreshApplicationOnce]);

  async function uploadDl(docType: DocType, file: File): Promise<boolean> {
    if (!app) return false;
    setError(null);
    setDlState(s => ({ ...s, [docType]: "UPLOADING" }));
    setDlMessage(m => ({ ...m, [docType]: docType === "CDL_FRONT" ? "Uploading front image..." : "Uploading back image..." }));
    const timer = window.setTimeout(() => {
      setDlState(s => s[docType] === "UPLOADING" ? { ...s, [docType]: "SCANNING" } : s);
      setDlMessage(m => ({
        ...m,
        [docType]: "Processing licence image...",
      }));
    }, 600);
    try {
      const resp = await uploadPersonApplicationDlFile({ appId: app.id, onboardingToken: token, docType, file });
      window.clearTimeout(timer);
      const fileMeta = (resp.intake_payload as any)?.files?.[docType];
      const ok = resp.file_id != null && fileMeta?.dl_preprocess_status === "PROCESSED";
      setDlState(s => ({ ...s, [docType]: ok ? "SUCCESS" : "FAILED" }));
      setDlMessage(m => ({
        ...m,
        [docType]: ok ? "" : "We could not process this licence image. Please try again.",
      }));
      setApp(prev => prev ? { ...prev, intake_payload: resp.intake_payload ?? prev.intake_payload } : prev);
      if (ok) {
        const files = (resp.intake_payload as any)?.files ?? {};
        const thumbFileId =
          files[docType]?.enh_file_id ??
          files[`${docType}_PROCESSED`]?.storage_key ??
          resp.sanitized_file_id ??
          resp.file_id!;
        try {
          const thumbUrl = await getPersonApplicationFileThumbnail({ appId: app.id, fileId: thumbFileId, onboardingToken: token });
          setPreviewUrl(prev => {
            const old = prev[docType];
            if (old?.startsWith("blob:")) URL.revokeObjectURL(old);
            return { ...prev, [docType]: thumbUrl };
          });
        } catch {}
      }
      return ok;
    } catch (e: any) {
      window.clearTimeout(timer);
      setDlState(s => ({ ...s, [docType]: "FAILED" }));
      setError(userFacingErrorMessage(e, "We could not upload your license right now. Please try again."));
      return false;
    }
  }

  async function handleDlUploadSide(side: "front" | "back", file: File): Promise<boolean> {
    const docType: DocType = side === "front" ? "CDL_FRONT" : "CDL_BACK";
    return uploadDl(docType, file);
  }

  async function handleDlConfirmSide(side: "front" | "back"): Promise<boolean> {
    if (!app || !token) return false;
    const docType: DocType = side === "front" ? "CDL_FRONT" : "CDL_BACK";
    setError(null);
    setDlMessage((m) => ({
      ...m,
      [docType]: docType === "CDL_BACK" ? "Reading licence barcode…" : "Saving photo…",
    }));
    try {
      const resp = await confirmPersonApplicationDlSide({ onboardingToken: token, docType });
      setApp((prev) => (prev ? { ...prev, intake_payload: resp.intake_payload ?? prev.intake_payload } : prev));
      const extract = resp.license_extract_status;
      if (docType === "CDL_BACK" && extract && extract !== "SUCCESS") {
        setDlMessage((m) => ({
          ...m,
          [docType]:
            extract === "FAILED"
              ? "We could not read the barcode on this photo. The photo is saved — upload again or enter details manually."
              : "We could not read licence details from this photo. The photo is saved — you can enter details manually.",
        }));
      } else {
        setDlMessage((m) => ({ ...m, [docType]: "" }));
      }
      setForm((prev) =>
        hydrateOnboardingFormFromIntake(prev, (resp.intake_payload as Record<string, unknown>) || {}, "after_dl_upload"),
      );
      return true;
    } catch (e: unknown) {
      setError(userFacingErrorMessage(e, "Could not confirm this photo. Please try again."));
      return false;
    }
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
      setForm(hydrateOnboardingFormFromIntake({ ...EMPTY_FORM }, intake, "initial"));
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
      setShowValidationSubmit(false);
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

  function applyNormalized(n: OnboardingSnapshot) {
    setForm((prev) => ({ ...prev, ...n.form }));
    setJobs(n.jobs.length ? n.jobs : [{ ...EMPTY_JOB }]);
    setRefs(
      n.refs.length >= 2
        ? n.refs
        : [...n.refs, ...Array.from({ length: 2 - n.refs.length }, () => ({ ...EMPTY_REF }))],
    );
  }

  async function saveAndNext(nextStep: Step) {
    if (!app) return;
    const n = normalizeSnapshot(
      buildSnapshot({
        form,
        jobs,
        refs,
        intake,
        documents: docUploaded,
        agree1,
        agree2,
        agree3,
      }),
    );
    applyNormalized(n);
    const errors = validateOnboardingStep(step, n);
    if (errors.length) {
      if (step === 0) setShowValidationStep0(true);
      if (step === 1) setShowValidationStep1(true);
      if (step === 2) setShowValidationStep2(true);
      setError(firstErrorMessage(errors));
      return;
    }
    setSaving(true);
    setError(null);
    setShowValidationStep0(false);
    setShowValidationStep1(false);
    setShowValidationStep2(false);
    try {
      const payload = mergeIntakeForSave(
        ((app.intake_payload as any) || {}) as Record<string, unknown>,
        n.form,
        {
          jobs: n.jobs,
          refs: n.refs,
          agree_info_accurate: agree1,
          agree_background_check: agree2,
          agree_dot_compliance: agree3,
          onboarding_step: nextStep,
        },
      );
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
    if (!app || (submitted && !documentResumeActive)) return;
    const n = normalizeSnapshot(
      buildSnapshot({
        form,
        jobs,
        refs,
        intake,
        documents: docUploaded,
        agree1,
        agree2,
        agree3,
      }),
    );
    applyNormalized(n);
    const errors = validateSubmit(n);
    if (errors.length) {
      setShowValidationSubmit(true);
      setShowValidationStep0(true);
      setShowValidationStep1(true);
      setShowValidationStep2(true);
      setError(firstErrorMessage(errors));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = mergeIntakeForSave(
        ((app.intake_payload as any) || {}) as Record<string, unknown>,
        n.form,
        {
          jobs: n.jobs,
          refs: n.refs,
          agree_info_accurate: n.agreeInfoAccurate,
          agree_background_check: n.agreeBackgroundCheck,
          agree_dot_compliance: n.agreeDotCompliance,
        },
      );
      const updated = await submitPersonApplication({ appId: app.id, onboardingToken: token, intakePayload: payload });
      setApp(updated);
      setSubmitted(updated.status === "SUBMITTED" || updated.status === "APPROVED");
      setDocumentResumeActive(!!(updated as { document_resume_active?: boolean }).document_resume_active);
    } catch (e: any) {
      setError(e?.message || "Submit failed");
    } finally {
      setSaving(false);
    }
  }

  function setF(key: string, val: string) {
    setForm((f) => ({ ...f, [key]: liveNormalize(key, val) }));
  }
  function blurF(key: string) {
    setForm((f) => ({ ...f, [key]: blurNormalize(key, String((f as Record<string, string>)[key] ?? "")) }));
  }
  function setJob(i: number, key: keyof JobEntry, val: string) {
    setJobs((j) => j.map((x, idx) => (idx === i ? { ...x, [key]: liveNormalize(key, val) } : x)));
  }
  function blurJob(i: number, key: keyof JobEntry) {
    setJobs((j) => j.map((x, idx) => (idx === i ? { ...x, [key]: blurNormalize(key, x[key]) } : x)));
  }
  function setRef(i: number, key: keyof RefEntry, val: string) {
    setRefs((r) => r.map((x, idx) => (idx === i ? { ...x, [key]: liveNormalize(key, val) } : x)));
  }
  function blurRef(i: number, key: keyof RefEntry) {
    setRefs((r) => r.map((x, idx) => (idx === i ? { ...x, [key]: blurNormalize(key, x[key]) } : x)));
  }

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

  if (submitted && !documentResumeActive) return (
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

  function nonDriverPayload(normalized: Record<string, string>) {
    return {
      first_name: normalized.first_name,
      last_name: normalized.last_name,
      phone: normalized.phone,
      email: normalized.email,
      address_street: normalized.address_street,
      address_city: normalized.address_city,
      address_region: normalized.address_region,
      address_postal: normalized.address_postal,
      zip_code: normalized.zip_code,
      address_country: normalized.address_country,
      notes: form.notes,
    };
  }

  async function handleMinimalSave() {
    if (!app) return;
    const normalized = normalizeForm(form);
    setForm((prev) => ({ ...prev, ...normalized }));
    const errors = validateNonDriverContact(normalized);
    if (errors.length) {
      setShowValidationStep1(true);
      setError(firstErrorMessage(errors));
      return;
    }
    setSaving(true);
    setError(null);
    setShowValidationStep1(false);
    try {
      const updated = await savePersonApplicationIntake({
        appId: app.id,
        onboardingToken: token,
        intakePayload: nonDriverPayload(normalized),
      });
      setApp(updated);
    } catch (e: any) {
      setError(e?.message || "Failed to save.");
    } finally {
      setSaving(false);
    }
  }

  async function handleMinimalSubmit() {
    if (!app) return;
    const normalized = normalizeForm(form);
    setForm((prev) => ({ ...prev, ...normalized }));
    const errors = validateNonDriverContact(normalized);
    if (errors.length) {
      setShowValidationStep1(true);
      setError(firstErrorMessage(errors));
      return;
    }
    setSaving(true);
    setError(null);
    setShowValidationStep1(false);
    try {
      const updated = await submitPersonApplication({
        appId: app.id,
        onboardingToken: token,
        intakePayload: nonDriverPayload(normalized),
      });
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
              <Field label="First Name" required invalid={!!feContact.first_name} error={feContact.first_name}>
                <input className={controlClass(true, !!feContact.first_name)} value={form.first_name} onChange={e => setF("first_name", e.target.value)} onBlur={() => blurF("first_name")} placeholder="First Name" />
              </Field>
              <Field label="Last Name" required invalid={!!feContact.last_name} error={feContact.last_name}>
                <input className={controlClass(true, !!feContact.last_name)} value={form.last_name} onChange={e => setF("last_name", e.target.value)} onBlur={() => blurF("last_name")} placeholder="Last Name" />
              </Field>
              <Field label="Email" required invalid={!!feContact.email} error={feContact.email}>
                <input className={controlClass(true, !!feContact.email)} type="email" value={form.email} onChange={e => setF("email", e.target.value)} onBlur={() => blurF("email")} placeholder="you@email.com" />
              </Field>
              <Field label="Phone" required invalid={!!feContact.phone} error={feContact.phone}>
                <input className={controlClass(true, !!feContact.phone)} type="tel" value={displayPhone(form.phone)} onChange={e => setF("phone", e.target.value)} onBlur={() => blurF("phone")} placeholder="(555) 000-0000" />
              </Field>
              <div className="col-span-2">
                <Field label="Street Address" required invalid={!!feContact.address_street} error={feContact.address_street}>
                  <input className={controlClass(true, !!feContact.address_street)} value={form.address_street} onChange={e => setF("address_street", e.target.value)} onBlur={() => blurF("address_street")} placeholder="Street Address" />
                </Field>
              </div>
              <Field label="Country" required invalid={!!feContact.address_country} error={feContact.address_country}>
                <select className={selectClass(true, !!feContact.address_country)} value={form.address_country} onChange={e => { setF("address_country", e.target.value); setF("address_region", ""); setF("zip_code", ""); setF("address_postal", ""); }}>
                  <option value="US">United States</option>
                  <option value="CA">Canada</option>
                </select>
              </Field>
              <Field label="City" required invalid={!!feContact.address_city} error={feContact.address_city}>
                <input className={controlClass(true, !!feContact.address_city)} value={form.address_city} onChange={e => setF("address_city", e.target.value)} onBlur={() => blurF("address_city")} placeholder="City" />
              </Field>
              <Field label={form.address_country === "CA" ? "Province" : "State"} required invalid={!!feContact.address_region} error={feContact.address_region}>
                <select className={selectClass(true, !!feContact.address_region)} value={form.address_region} onChange={e => setF("address_region", e.target.value)}>
                  <option value="">{form.address_country === "CA" ? "Select Province" : "Select State"}</option>
                  {form.address_country === "CA"
                    ? Object.entries(CA_PROVINCES).map(([code, name]) => <option key={code} value={code}>{name}</option>)
                    : Object.entries(US_STATES).map(([code, name]) => <option key={code} value={code}>{name}</option>)
                  }
                </select>
              </Field>
              <Field
                label={form.address_country === "CA" ? "Postal Code" : "ZIP Code"}
                required
                invalid={!!(form.address_country === "CA" ? feContact.address_postal : feContact.zip_code)}
                error={form.address_country === "CA" ? feContact.address_postal : feContact.zip_code}
              >
                {form.address_country === "CA" ? (
                  <input className={controlClass(true, !!feContact.address_postal)} value={form.address_postal} onChange={e => setF("address_postal", e.target.value)} onBlur={() => blurF("address_postal")} placeholder="A1A 1A1" />
                ) : (
                  <input className={controlClass(true, !!feContact.zip_code)} value={form.zip_code} onChange={e => setF("zip_code", e.target.value)} onBlur={() => blurF("zip_code")} placeholder="00000" />
                )}
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
          <p className="text-gray-500 text-sm mt-1">
            {resumeDocsOnly ? "Upload requested documents and resubmit" : "Complete all steps to submit your application"}
          </p>
        </div>

        {!resumeDocsOnly && <ProgressBar step={step} />}

        {resumeDocsOnly && (
          <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            Your application is on file. Use this secure link to upload the documents we requested, then resubmit when finished.
          </div>
        )}

        {error && <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-400">{error}</div>}

        {/* ── STEP 1: LICENSE UPLOAD ── */}
        {!resumeDocsOnly && step === 0 && (
          <div className="space-y-6">
            <DLUploadStep
              frontPreviewUrl={previewUrl.CDL_FRONT}
              backPreviewUrl={previewUrl.CDL_BACK}
              frontState={dlState.CDL_FRONT}
              backState={dlState.CDL_BACK}
              frontMessage={dlMessage.CDL_FRONT}
              backMessage={dlMessage.CDL_BACK}
              onUploadSide={handleDlUploadSide}
              onConfirmSide={handleDlConfirmSide}
              onNormalizeError={(message) => setError(message)}
              onboardingToken={token || undefined}
              intake={intake}
              disabled={saving || !app}
              onRefreshApplication={refreshApplicationOnce}
              onClearSavedData={() => void resetSavedDraft()}
              saving={saving}
            />
            {(fe0.CDL_FRONT || fe0.CDL_BACK) && (
              <p className="text-xs text-rose-400">{[fe0.CDL_FRONT, fe0.CDL_BACK].filter(Boolean).join(" ")}</p>
            )}
            <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-6 space-y-6 mt-4">
              <SectionTitle>License Details</SectionTitle>
              <div className="grid grid-cols-2 gap-4">

                {/* Country selector — always shown first */}
                <div className="col-span-2">
                  <Field label="Country" required invalid={!!fe0.address_country} error={fe0.address_country}>
                    <select className={selectClass(true, !!fe0.address_country)} value={form.address_country}
                      onChange={e => { setF("address_country", e.target.value); setF("address_region", ""); setF("license_region", ""); setF("zip_code", ""); setF("address_postal", ""); }}>
                      <option value="US">🇺🇸 United States</option>
                      <option value="CA">🇨🇦 Canada</option>
                    </select>
                  </Field>
                </div>

                {/* License Number */}
                <Field label="License Number" required invalid={!!fe0.driver_license_number} error={fe0.driver_license_number}>
                  <input className={controlClass(true, !!fe0.driver_license_number, dlReviewAccent(sources.license_number, edited.license_number, form.driver_license_number))} value={form.driver_license_number}
                    onChange={e => setF("driver_license_number", e.target.value)}
                    onBlur={() => blurF("driver_license_number")}
                    placeholder={form.address_country === "CA" ? "e.g. K35587-56016-90112" : "e.g. DL12345678"} />
                </Field>

                {/* Province/State Issued */}
                <Field label={form.address_country === "CA" ? "Province Issued" : "State Issued"} required invalid={!!fe0.license_region} error={fe0.license_region}>
                  <select className={selectClass(true, !!fe0.license_region, dlReviewAccent(sources.license_state, edited.license_state, form.license_region))} value={form.license_region}
                    onChange={e => setF("license_region", e.target.value)}>
                    <option value="">{form.address_country === "CA" ? "Select Province" : "Select State"}</option>
                    {form.address_country === "CA"
                      ? Object.entries(CA_PROVINCES).map(([code, name]) => <option key={code} value={code}>{name}</option>)
                      : Object.entries(US_STATES).map(([code, name]) => <option key={code} value={code}>{name}</option>)
                    }
                  </select>
                </Field>

                {/* Expiry Date */}
                <Field label="Expiry Date" required skipShell>
                  <OnboardingDateField
                    required
                    invalid={!!fe0.license_expiry}
                    error={fe0.license_expiry}
                    showError
                    extraClass={dlReviewAccent(sources.license_expiry, edited.license_expiry, form.license_expiry)}
                    value={form.license_expiry}
                    onChange={value => setF("license_expiry", value)}
                  />
                </Field>

                {/* Issue Date */}
                <Field label="Issue Date" skipShell>
                  <OnboardingDateField
                    invalid={!!fe0.license_issue_date}
                    error={fe0.license_issue_date}
                    showError
                    extraClass={dlReviewAccent(sources.license_issue_date, edited.license_issue_date, form.license_issue_date)}
                    value={form.license_issue_date}
                    onChange={value => setF("license_issue_date", value)}
                  />
                </Field>

                {/* Class — free text, prepopulated from extraction, applicant can correct */}
                <Field label={form.address_country === "CA" ? "Licence Class (e.g. A, AC)" : "CDL Class (e.g. A, B, C)"} required invalid={!!fe0.cdl_class} error={fe0.cdl_class}>
                  <input className={controlClass(true, !!fe0.cdl_class, dlReviewAccent(sources.license_class, edited.license_class, form.cdl_class))} value={form.cdl_class}
                    onChange={e => setF("cdl_class", e.target.value)}
                    onBlur={() => blurF("cdl_class")}
                    placeholder={form.address_country === "CA" ? "e.g. A, AC, G" : "e.g. A, B, C"} />
                </Field>

                {/* Endorsements */}
                <Field label={form.address_country === "CA" ? "Endorsements / Conditions Code" : "Endorsements"}>
                  <input className={controlClass(false, false, dlReviewAccent(sources.endorsements, edited.endorsements, form.endorsements))} value={form.endorsements}
                    onChange={e => setF("endorsements", e.target.value)}
                    onBlur={() => blurF("endorsements")}
                    placeholder={form.address_country === "CA" ? "e.g. Z (Air Brakes)" : "e.g. H, N, T, X"} />
                </Field>

                {/* Restrictions */}
                <Field label="Restrictions">
                  <input className={controlClass(false, false, dlReviewAccent(sources.restrictions, edited.restrictions, form.restrictions))} value={form.restrictions || ""}
                    onChange={e => setF("restrictions", e.target.value)}
                    onBlur={() => blurF("restrictions")}
                    placeholder="e.g. B, Corrective Lenses" />
                </Field>

                {/* Conditions — Canadian only */}
                {form.address_country === "CA" && (
                  <Field label="Conditions (Canadian licences only)">
                    <input className={controlClass(false, false, dlReviewAccent(sources.conditions, edited.conditions, form.conditions))} value={form.conditions}
                      onChange={e => setF("conditions", e.target.value)}
                      onBlur={() => blurF("conditions")}
                      placeholder="e.g. COND" />
                  </Field>
                )}

              </div>
            </div>

            <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-6 space-y-6 mt-4">
              <SectionTitle>Applicant Details From DL</SectionTitle>
              <div className="grid grid-cols-2 gap-4">
                <Field label="First Name">
                  <input className={controlClass(false, false, dlReviewAccent(sources.first_name, edited.first_name, form.first_name))} value={form.first_name} onChange={e => setF("first_name", e.target.value)} onBlur={() => blurF("first_name")} placeholder="First Name" />
                </Field>
                <Field label="Last Name">
                  <input className={controlClass(false, false, dlReviewAccent(sources.last_name, edited.last_name, form.last_name))} value={form.last_name} onChange={e => setF("last_name", e.target.value)} onBlur={() => blurF("last_name")} placeholder="Last Name" />
                </Field>
                <Field label="Date of Birth" skipShell>
                  <OnboardingDateField
                    extraClass={dlReviewAccent(sources.date_of_birth, edited.date_of_birth, form.date_of_birth)}
                    value={form.date_of_birth}
                    onChange={value => setF("date_of_birth", value)}
                  />
                </Field>
                <Field label="Sex">
                  <select className={selectClass(false, false, dlReviewAccent(sources.sex, edited.sex, form.sex))} value={form.sex} onChange={e => setF("sex", e.target.value)}>
                    <option value="">Select</option>
                    <option value="M">Male</option>
                    <option value="F">Female</option>
                    <option value="X">Other / Unspecified</option>
                  </select>
                </Field>
                <Field label="Height">
                  <input className={controlClass(false, false, dlReviewAccent(sources.height, edited.height, form.height))} value={form.height} onChange={e => setF("height", e.target.value)} placeholder="e.g. 180 cm or 5-11" />
                </Field>
                <Field label="Street Address">
                  <input className={controlClass(false, false, dlReviewAccentAny([
                    { source: sources.address_line, edited: edited.address_street, value: form.address_street },
                    { source: sources.address_street, edited: edited.address_street, value: form.address_street },
                  ]))} value={form.address_street} onChange={e => setF("address_street", e.target.value)} onBlur={() => blurF("address_street")} placeholder="Street Address" />
                </Field>
                <Field label="City">
                  <input className={controlClass(false, false, dlReviewAccent(sources.address_city, edited.address_city, form.address_city))} value={form.address_city} onChange={e => setF("address_city", e.target.value)} onBlur={() => blurF("address_city")} placeholder="City" />
                </Field>
                <Field label={form.address_country === "CA" ? "Province / Postal Code" : "State / ZIP Code"} skipShell>
                  <div className="grid grid-cols-2 gap-3">
                    <input className={controlClass(false, false, dlReviewAccent(sources.address_region, edited.address_region, form.address_region))} value={form.address_region} onChange={e => setF("address_region", e.target.value)} placeholder={form.address_country === "CA" ? "Province" : "State"} />
                    {form.address_country === "CA" ? (
                      <input className={controlClass(false, false, dlReviewAccent(sources.address_postal, edited.address_postal, form.address_postal))} value={form.address_postal} onChange={e => setF("address_postal", e.target.value)} onBlur={() => blurF("address_postal")} placeholder="Postal Code" />
                    ) : (
                      <input className={controlClass(false, false, dlReviewAccent(sources.zip_code, edited.zip_code, form.zip_code))} value={form.zip_code} onChange={e => setF("zip_code", e.target.value)} onBlur={() => blurF("zip_code")} placeholder="ZIP Code" />
                    )}
                  </div>
                </Field>
              </div>
            </div>

            {step0Incomplete && (
              <p className="text-amber-400 text-sm">
                Upload both license sides and fill all license details above to continue.
              </p>
            )}

            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => void saveAndNext(1)}
                disabled={
                  saving ||
                  dlState.CDL_FRONT === "UPLOADING" ||
                  dlState.CDL_FRONT === "SCANNING" ||
                  dlState.CDL_BACK === "UPLOADING" ||
                  dlState.CDL_BACK === "SCANNING"
                }
                className="rounded-xl bg-orange-500 px-6 py-3 text-sm font-bold uppercase tracking-widest text-black hover:bg-orange-400 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Continue"}
              </button>
            </div>
          </div>
        )}

        {/* ── STEP 2: PERSONAL INFO ── */}
        {!resumeDocsOnly && step === 1 && (
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
                <Field label="First Name" required invalid={!!fe1.first_name} error={fe1.first_name}>
                  <input className={controlClass(true, !!fe1.first_name, dlReviewAccent(sources.first_name, edited.first_name, form.first_name))} value={form.first_name} onChange={e => setF("first_name", e.target.value)} onBlur={() => blurF("first_name")} placeholder="First Name" />
                </Field>
                <Field label="Middle Name" invalid={!!fe1.middle_name} error={fe1.middle_name}>
                  <input className={controlClass(false, !!fe1.middle_name)} value={form.middle_name} onChange={e => setF("middle_name", e.target.value)} onBlur={() => blurF("middle_name")} placeholder="Middle (optional)" />
                </Field>
                <Field label="Last Name" required invalid={!!fe1.last_name} error={fe1.last_name}>
                  <input className={controlClass(true, !!fe1.last_name, dlReviewAccent(sources.last_name, edited.last_name, form.last_name))} value={form.last_name} onChange={e => setF("last_name", e.target.value)} onBlur={() => blurF("last_name")} placeholder="Last Name" />
                </Field>
                <Field label="Date of Birth" required skipShell>
                  <OnboardingDateField
                    required
                    invalid={!!fe1.date_of_birth}
                    error={fe1.date_of_birth}
                    showError
                    extraClass={dlReviewAccent(sources.date_of_birth, edited.date_of_birth, form.date_of_birth)}
                    value={form.date_of_birth}
                    onChange={value => setF("date_of_birth", value)}
                  />
                </Field>
                <Field label="SSN (last 4 optional)" invalid={!!fe1.ssn} error={fe1.ssn}>
                  <input className={controlClass(false, !!fe1.ssn)} value={form.ssn} onChange={e => setF("ssn", e.target.value)} placeholder="XXX-XX-XXXX" />
                </Field>
                <Field label="Nationality">
                  <input className={controlClass(false, false)} value={form.nationality} onChange={e => setF("nationality", e.target.value)} placeholder="e.g. US Citizen" />
                </Field>

                {/* Sex / Gender */}
                <Field label="Sex / Gender" required invalid={!!fe1.sex} error={fe1.sex}>
                  <select className={selectClass(true, !!fe1.sex, dlReviewAccent(sources.sex, edited.sex, form.sex))} value={form.sex} onChange={e => setF("sex", e.target.value)}>
                    <option value="">Select</option>
                    <option value="M">Male</option>
                    <option value="F">Female</option>
                    <option value="X">Other / Unspecified</option>
                  </select>
                </Field>

                {/* Height */}
                <Field label={form.address_country === "CA" ? "Height (cm)" : "Height (ft/in)"}>
                  <input className={controlClass(false, false, dlReviewAccent(sources.height, edited.height, form.height))} value={form.height}
                    onChange={e => setF("height", e.target.value)}
                    placeholder={form.address_country === "CA" ? "e.g. 160 cm" : "e.g. 5'11\""} />
                </Field>
              </div>

              <SectionTitle>Contact Information</SectionTitle>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Email" required invalid={!!fe1.email} error={fe1.email}>
                  <input className={controlClass(true, !!fe1.email)} type="email" value={form.email} onChange={e => setF("email", e.target.value)} onBlur={() => blurF("email")} placeholder="you@email.com" />
                </Field>
                <Field label="Phone" required invalid={!!fe1.phone} error={fe1.phone}>
                  <input className={controlClass(true, !!fe1.phone)} type="tel" value={displayPhone(form.phone)} onChange={e => setF("phone", e.target.value)} onBlur={() => blurF("phone")} placeholder="(555) 000-0000" />
                </Field>
                <div className="col-span-2">
                  <Field label="Street Address" required invalid={!!fe1.address_street} error={fe1.address_street}>
                    <input className={controlClass(true, !!fe1.address_street)} value={form.address_street} onChange={e => setF("address_street", e.target.value)} onBlur={() => blurF("address_street")} placeholder="Street Address" />
                  </Field>
                </div>
                <Field label="Country" required invalid={!!fe1.address_country} error={fe1.address_country}>
                  <select className={selectClass(true, !!fe1.address_country)} value={form.address_country} onChange={e => { setF("address_country", e.target.value); setF("address_region", ""); setF("zip_code", ""); setF("address_postal", ""); }}>
                    <option value="US">🇺🇸 United States</option>
                    <option value="CA">🇨🇦 Canada</option>
                  </select>
                </Field>
                <Field label="City" required invalid={!!fe1.address_city} error={fe1.address_city}>
                  <input className={controlClass(true, !!fe1.address_city)} value={form.address_city} onChange={e => setF("address_city", e.target.value)} onBlur={() => blurF("address_city")} placeholder="City" />
                </Field>
                <Field label={form.address_country === "CA" ? "Province" : "State"} required invalid={!!fe1.address_region} error={fe1.address_region}>
                  <select className={selectClass(true, !!fe1.address_region)} value={form.address_region} onChange={e => setF("address_region", e.target.value)}>
                    <option value="">{form.address_country === "CA" ? "Select Province" : "Select State"}</option>
                    {form.address_country === "CA"
                      ? Object.entries(CA_PROVINCES).map(([code, name]) => <option key={code} value={code}>{name}</option>)
                      : Object.entries(US_STATES).map(([code, name]) => <option key={code} value={code}>{name}</option>)
                    }
                  </select>
                </Field>
                <Field
                  label={form.address_country === "CA" ? "Postal Code" : "ZIP Code"}
                  required
                  invalid={!!(form.address_country === "CA" ? fe1.address_postal : fe1.zip_code)}
                  error={form.address_country === "CA" ? fe1.address_postal : fe1.zip_code}
                >
                  {form.address_country === "CA" ? (
                    <input className={controlClass(true, !!fe1.address_postal)} value={form.address_postal} onChange={e => setF("address_postal", e.target.value)} onBlur={() => blurF("address_postal")} placeholder="A1A 1A1" />
                  ) : (
                    <input className={controlClass(true, !!fe1.zip_code)} value={form.zip_code} onChange={e => setF("zip_code", e.target.value)} onBlur={() => blurF("zip_code")} placeholder="00000" />
                  )}
                </Field>
              </div>

              <SectionTitle>Driving Experience</SectionTitle>
              <div className="grid grid-cols-2 gap-4">
                <Field label="DOT Medical Card Expiry" skipShell>
                  <OnboardingDateField
                    invalid={!!fe1.dot_medical_card_expiry}
                    error={fe1.dot_medical_card_expiry}
                    showError
                    value={form.dot_medical_card_expiry}
                    onChange={value => setF("dot_medical_card_expiry", value)}
                  />
                </Field>
                <Field label="Years of CDL Experience">
                  <select className={selectClass(false, false)} value={form.years_experience} onChange={e => setF("years_experience", e.target.value)}>
                    <option value="">Select</option>
                    <option>Less than 1 year</option>
                    <option>1–2 years</option>
                    <option>2–5 years</option>
                    <option>5–10 years</option>
                    <option>10+ years</option>
                  </select>
                </Field>
                <Field label="Total Miles Driven (approx)">
                  <input className={controlClass(false, false)} value={form.total_miles} onChange={e => setF("total_miles", e.target.value)} placeholder="e.g. 500,000" />
                </Field>
                <Field label="Equipment Types">
                  <input className={controlClass(false, false)} value={form.equipment_types} onChange={e => setF("equipment_types", e.target.value)} placeholder="e.g. Dry Van, Flatbed" />
                </Field>
                <Field label="Accidents in Last 3 Years?">
                  <select className={selectClass(false, false)} value={form.accidents_last_3_years} onChange={e => setF("accidents_last_3_years", e.target.value)}>
                    <option value="">Select</option>
                    <option value="no">No</option>
                    <option value="yes">Yes</option>
                  </select>
                </Field>
                <Field label="Moving Violations in Last 3 Years?">
                  <select className={selectClass(false, false)} value={form.violations_last_3_years} onChange={e => setF("violations_last_3_years", e.target.value)}>
                    <option value="">Select</option>
                    <option value="no">No</option>
                    <option value="yes">Yes</option>
                  </select>
                </Field>
              </div>

              <SectionTitle>Emergency Contact</SectionTitle>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Contact Name" invalid={!!fe1.emergency_contact_name} error={fe1.emergency_contact_name}>
                  <input className={controlClass(false, !!fe1.emergency_contact_name)} value={form.emergency_contact_name} onChange={e => setF("emergency_contact_name", e.target.value)} onBlur={() => blurF("emergency_contact_name")} placeholder="Full Name" />
                </Field>
                <Field label="Relationship">
                  <input className={controlClass(false, false)} value={form.emergency_contact_relationship} onChange={e => setF("emergency_contact_relationship", e.target.value)} placeholder="e.g. Spouse" />
                </Field>
                <Field label="Phone" invalid={!!fe1.emergency_contact_phone} error={fe1.emergency_contact_phone}>
                  <input className={controlClass(false, !!fe1.emergency_contact_phone)} value={displayPhone(form.emergency_contact_phone)} onChange={e => setF("emergency_contact_phone", e.target.value)} onBlur={() => blurF("emergency_contact_phone")} placeholder="(555) 000-0000" />
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
        {!resumeDocsOnly && step === 2 && (
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
                const jobKey = (k: string) => `jobs.${i}.${k}`;
                const started = Boolean((job.company_name || "").trim() || (job.position_title || "").trim() || (job.start_date || "").trim());
                const jobRequired = i === 0 || started;
                const jobErr = Boolean(fe2[jobKey("company_name")] || fe2[jobKey("position_title")] || fe2[jobKey("start_date")] || fe2[jobKey("end_date")] || fe2[jobKey("supervisor_phone")]);
                return (
                <div key={i} className={`rounded-2xl border p-5 relative transition-colors ${jobErr ? "border-rose-500/60 bg-rose-500/5" : "border-gray-700 bg-gray-800/60"}`}>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-xs font-bold uppercase tracking-widest text-orange-400">Employer {i + 1}</span>
                    {jobs.length > 1 && <button onClick={() => setJobs(j => j.filter((_, idx) => idx !== i))} className="text-xs text-rose-400 hover:text-rose-300 border border-rose-500/30 rounded px-2 py-1">Remove</button>}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Company Name" required={jobRequired} invalid={!!fe2[jobKey("company_name")]} error={fe2[jobKey("company_name")]}>
                      <input className={controlClass(jobRequired, !!fe2[jobKey("company_name")])} value={job.company_name} onChange={e => setJob(i, "company_name", e.target.value)} onBlur={() => blurJob(i, "company_name")} placeholder="Company Name" />
                    </Field>
                    <Field label="Position / Title" required={jobRequired} invalid={!!fe2[jobKey("position_title")]} error={fe2[jobKey("position_title")]}>
                      <input className={controlClass(jobRequired, !!fe2[jobKey("position_title")])} value={job.position_title} onChange={e => setJob(i, "position_title", e.target.value)} onBlur={() => blurJob(i, "position_title")} placeholder="e.g. OTR Driver" />
                    </Field>
                    <Field label="Start Date" required={jobRequired} skipShell>
                      <OnboardingDateField
                        required={jobRequired}
                        invalid={!!fe2[jobKey("start_date")]}
                        error={fe2[jobKey("start_date")]}
                        showError
                        value={job.start_date}
                        onChange={value => setJob(i, "start_date", value)}
                      />
                    </Field>
                    <Field label="End Date" skipShell>
                      <OnboardingDateField
                        invalid={!!fe2[jobKey("end_date")]}
                        error={fe2[jobKey("end_date")]}
                        showError
                        value={job.end_date}
                        onChange={value => setJob(i, "end_date", value)}
                      />
                    </Field>
                    <Field label="Reason for Leaving">
                      <input className={controlClass(false, false)} value={job.reason_for_leaving} onChange={e => setJob(i, "reason_for_leaving", e.target.value)} placeholder="e.g. Better opportunity" />
                    </Field>
                    <Field label="Supervisor Name">
                      <input className={controlClass(false, false)} value={job.supervisor_name} onChange={e => setJob(i, "supervisor_name", e.target.value)} onBlur={() => blurJob(i, "supervisor_name")} placeholder="Supervisor" />
                    </Field>
                    <Field label="Supervisor Phone" invalid={!!fe2[jobKey("supervisor_phone")]} error={fe2[jobKey("supervisor_phone")]}>
                      <input className={controlClass(false, !!fe2[jobKey("supervisor_phone")])} value={displayPhone(job.supervisor_phone)} onChange={e => setJob(i, "supervisor_phone", e.target.value)} onBlur={() => blurJob(i, "supervisor_phone")} placeholder="(555) 000-0000" />
                    </Field>
                    <Field label="Equipment Operated">
                      <input className={controlClass(false, false)} value={job.equipment_operated} onChange={e => setJob(i, "equipment_operated", e.target.value)} placeholder="e.g. Dry Van 53ft" />
                    </Field>
                    <Field label="City, State">
                      <input className={controlClass(false, false)} value={job.city_state} onChange={e => setJob(i, "city_state", e.target.value)} placeholder="City, State" />
                    </Field>
                    <Field label="Subject to FMCSA?">
                      <select className={selectClass(false, false)} value={job.subject_to_fmcsa} onChange={e => setJob(i, "subject_to_fmcsa", e.target.value)}>
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
                const refErr = Boolean(fe2[`refs.${i}.full_name`] || fe2[`refs.${i}.phone`] || fe2[`refs.${i}.email`]);
                return (
                <div key={i} className={`rounded-2xl border p-5 transition-colors ${refErr ? "border-rose-500/60 bg-rose-500/5" : "border-gray-700 bg-gray-800/60"}`}>
                  <span className="text-xs font-bold uppercase tracking-widest text-orange-400 block mb-4">Reference {i + 1}</span>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Full Name" required invalid={!!fe2[`refs.${i}.full_name`]} error={fe2[`refs.${i}.full_name`]}>
                      <input className={controlClass(true, !!fe2[`refs.${i}.full_name`])} value={ref.full_name} onChange={e => setRef(i, "full_name", e.target.value)} onBlur={() => blurRef(i, "full_name")} placeholder="Full Name" />
                    </Field>
                    <Field label="Relationship">
                      <input className={controlClass(false, false)} value={ref.relationship} onChange={e => setRef(i, "relationship", e.target.value)} placeholder="e.g. Former Supervisor" />
                    </Field>
                    <Field label="Company">
                      <input className={controlClass(false, false)} value={ref.company} onChange={e => setRef(i, "company", e.target.value)} placeholder="Company Name" />
                    </Field>
                    <Field label="Phone" invalid={!!fe2[`refs.${i}.phone`]} error={fe2[`refs.${i}.phone`]}>
                      <input className={controlClass(false, !!fe2[`refs.${i}.phone`])} value={displayPhone(ref.phone)} onChange={e => setRef(i, "phone", e.target.value)} onBlur={() => blurRef(i, "phone")} placeholder="(555) 000-0000" />
                    </Field>
                    <Field label="Email" invalid={!!fe2[`refs.${i}.email`]} error={fe2[`refs.${i}.email`]}>
                      <input className={controlClass(false, !!fe2[`refs.${i}.email`])} type="email" value={ref.email} onChange={e => setRef(i, "email", e.target.value)} onBlur={() => blurRef(i, "email")} placeholder="email@company.com" />
                    </Field>
                    <Field label="How long known?">
                      <input className={controlClass(false, false)} value={ref.known_duration} onChange={e => setRef(i, "known_duration", e.target.value)} placeholder="e.g. 5 years" />
                    </Field>
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
        {(resumeDocsOnly || step === 3) && (
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
              ].map(doc => {
                const docErr = fe3[`documents.${doc.key}`];
                return (
                <div key={doc.key} className={`rounded-xl border p-4 relative transition-all ${docUploaded[doc.key] ? "border-green-500/40 bg-green-500/5" : docErr ? "border-rose-500/60 bg-rose-500/5" : "border-gray-700 bg-gray-800/60 hover:border-gray-500"}`}>
                  {doc.required && !docUploaded[doc.key] && <span className="absolute top-3 right-3 text-xs font-bold text-rose-400 bg-rose-500/10 border border-rose-500/20 px-2 py-0.5 rounded">REQUIRED</span>}
                  {!doc.required && <span className="absolute top-3 right-3 text-xs font-bold text-gray-500 bg-gray-700/50 border border-gray-600 px-2 py-0.5 rounded">OPTIONAL</span>}
                  <div className="text-3xl mb-2">{doc.icon}</div>
                  <div className="font-semibold text-white text-sm mb-1">{doc.label}</div>
                  <div className="text-xs text-gray-400 mb-3">{doc.desc}</div>
                  <label className={`relative flex items-center gap-2 rounded-lg border px-3 py-2 pr-9 text-xs font-medium cursor-pointer transition-all ${docUploaded[doc.key] ? "border-green-500/40 text-green-400" : docErr ? "border-rose-500 text-rose-400" : "border-gray-600 text-gray-400 hover:border-orange-500 hover:text-orange-400"} ${docUploading === doc.key ? "opacity-70 pointer-events-none" : ""}`}>
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
                    {doc.required ? <RequiredGlyph /> : null}
                  </label>
                  {docErr ? <p className="mt-1 text-xs text-rose-400">{docErr}</p> : null}
                </div>
                );
              })}
            </div>

            <div className={`rounded-2xl border p-5 space-y-4 ${fe3.agreements ? "border-rose-500/60 bg-rose-500/5" : "border-gray-700 bg-gray-800/60"}`}>
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
              {fe3.agreements ? <p className="text-xs text-rose-400">{fe3.agreements}</p> : null}
            </div>

            <div className="flex gap-3">
              {!resumeDocsOnly && (
                <button type="button" onClick={() => setStep(2)} className="rounded-xl border border-gray-600 px-4 py-3 text-sm text-gray-400 hover:bg-gray-800">← Back</button>
              )}
              <button onClick={handleSubmit} disabled={saving}
                className="rounded-xl bg-green-500 px-8 py-3 text-sm font-bold uppercase tracking-widest text-black hover:bg-green-400 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-lg shadow-green-500/20">
                {saving ? "Submitting…" : resumeDocsOnly ? "Resubmit documents ✓" : "Submit Application ✓"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
