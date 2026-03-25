import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  checkSlugAvailability,
  checkSignupEmailAvailability,
  checkSignupPhoneAvailability,
  signup,
  verifyOtp,
  resendOtp,
  getSignupStatus,
  resumeSignup,
  changeSignupSlug,
  retryProvisioning,
  cancelSignup,
} from "../api";
import { COUNTRIES } from "../data/countries";
import { useAuth } from "../contexts/AuthContext";
import { getTenantSlugFromHost } from "../tenant";
import {
  getPasswordValidation,
  checkHaveIBeenPwned,
  PASSWORD_MIN_LENGTH,
  PASSWORD_MAX_LENGTH,
} from "../utils/passwordValidation";

type SlugState =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "ok"; suggestions?: string[] }
  | { status: "bad"; message: string; suggestions?: string[] };

type FieldAvailabilityState =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "ok" }
  | { status: "bad"; message: string }
  /** Email already in platform_users — public signup cannot create a second account; use sign-in + Create workspace. */
  | { status: "taken"; message: string };

function slugify(raw: string) {
  return raw
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+/, "")
    .replace(/-+$/, "")
    .slice(0, 63);
}

function isValidEmailFormat(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((value || "").trim());
}

function isValidPhone(value: string): boolean {
  const digits = (value || "").replace(/\D/g, "");
  return digits.length >= 7 && digits.length <= 15;
}

function makeSuggestions(slug: string) {
  const base = slugify(slug);
  if (!base) return [];
  const tail = ["logistics", "transport", "trucking", "carrier", "inc", "llc"];
  return tail.map((t) => `${base}-${t}`).slice(0, 5);
}

type Step = "signup" | "otp";

function baseDomainFromHost(hostname: string) {
  const parts = hostname.split(".");
  if (parts.length <= 2) return hostname;
  return parts.slice(-2).join(".");
}

function sanitizeProvisionError(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const lower = raw.toLowerCase();
  if (lower.includes("company_profile") && lower.includes("does not exist")) {
    return "Setup failed because a required table is missing. Please retry.";
  }
  if (lower.includes("alembic failed") || lower.includes("migration")) {
    return "Setup failed during database provisioning. Please retry.";
  }
  return "Setup failed. Please retry.";
}

export default function SignupPage() {
  const nav = useNavigate();
  const { authReady, isAuthenticated, session } = useAuth();

  // Step 1 (basic)
  const [workspaceSlug, setWorkspaceSlug] = useState("");
  const [email, setEmail] = useState("");
  const [confirmEmail, setConfirmEmail] = useState("");

  // Step 2 (details required by backend)
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [street, setStreet] = useState("");
  const [city, setCity] = useState("");
  const [region, setRegion] = useState("");
  const [postal, setPostal] = useState("");
  const [country, setCountry] = useState<string>("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [isOwnerOrAdmin, setIsOwnerOrAdmin] = useState(true);
  const [plan, setPlan] = useState("trial");

  // OTP
  const [otp, setOtp] = useState("");
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [newSlug, setNewSlug] = useState("");
  const [resumeBusy, setResumeBusy] = useState(false);
  const [changeSlugBusy, setChangeSlugBusy] = useState(false);
  const [retryBusy, setRetryBusy] = useState(false);
  const [showResume, setShowResume] = useState(false);
  const [resumePrompt, setResumePrompt] = useState<string | null>(null);
  const [resumeCtaLabel, setResumeCtaLabel] = useState("Continue previous signup");
  const [resumeCandidate, setResumeCandidate] = useState<any | null>(null);
  const [hasStoredDraftOnLoad, setHasStoredDraftOnLoad] = useState(false);

  const [slugState, setSlugState] = useState<SlugState>({ status: "idle" });
  const [emailAvailState, setEmailAvailState] = useState<FieldAvailabilityState>({ status: "idle" });
  const [phoneAvailState, setPhoneAvailState] = useState<FieldAvailabilityState>({ status: "idle" });
  const [busy, setBusy] = useState(false);
  const [resendBusy, setResendBusy] = useState(false);
  const [step, setStep] = useState<Step>("signup");

  const [serverMsg, setServerMsg] = useState<string | null>(null);
  const [workspaceUrl, setWorkspaceUrl] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const [reservationExpiresAt, setReservationExpiresAt] = useState<string | null>(null);
  const [provisionError, setProvisionError] = useState<string | null>(null);
  const [attemptState, setAttemptState] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [breachCheckStatus, setBreachCheckStatus] = useState<"idle" | "checking" | "breached" | "ok">("idle");

  const normalizedSlug = useMemo(() => slugify(workspaceSlug), [workspaceSlug]);
  const isOtpEntryAllowed = !attemptState || attemptState === "OTP_SENT";
  const passwordValidation = useMemo(() => getPasswordValidation(password), [password]);
  const passwordsMatch = passwordValidation.trimmed === confirmPassword.trim();
  const slugAvailabilityBlocksSignup =
    slugState.status === "checking" || slugState.status === "bad";
  const emailAvailabilityBlocksSignup =
    !isAuthenticated &&
    (emailAvailState.status === "checking" ||
      emailAvailState.status === "bad" ||
      emailAvailState.status === "taken");
  const phoneAvailabilityBlocksSignup =
    !isAuthenticated && (phoneAvailState.status === "checking" || phoneAvailState.status === "bad");

  const sendOtpDisabled =
    busy ||
    !passwordValidation.valid ||
    !passwordsMatch ||
    breachCheckStatus === "checking" ||
    breachCheckStatus === "breached" ||
    slugAvailabilityBlocksSignup ||
    emailAvailabilityBlocksSignup ||
    phoneAvailabilityBlocksSignup;

  // Have I Been Pwned check when sync validation passes (debounced)
  const currentPasswordTrimmedRef = useRef<string>("");
  useEffect(() => {
    currentPasswordTrimmedRef.current = passwordValidation.trimmed;
    if (!passwordValidation.valid || passwordValidation.trimmed.length < PASSWORD_MIN_LENGTH) {
      setBreachCheckStatus("idle");
      return;
    }
    const trimmed = passwordValidation.trimmed;
    const t = setTimeout(async () => {
      setBreachCheckStatus("checking");
      try {
        const breached = await checkHaveIBeenPwned(trimmed);
        if (currentPasswordTrimmedRef.current === trimmed) {
          setBreachCheckStatus(breached ? "breached" : "ok");
        }
      } catch {
        if (currentPasswordTrimmedRef.current === trimmed) {
          setBreachCheckStatus("idle");
        }
      }
    }, 500);
    return () => clearTimeout(t);
  }, [passwordValidation.valid, passwordValidation.trimmed]);

  const inputClass = (hasError: boolean) =>
    `w-full rounded-lg bg-slate-950 border px-3 py-2 text-sm outline-none focus:border-indigo-500 ${
      hasError ? "border-rose-500" : "border-slate-800"
    }`;
  const selectClass = (hasError: boolean) =>
    `w-full rounded-lg bg-slate-950 border px-3 py-2 text-sm outline-none focus:border-indigo-500 ${
      hasError ? "border-rose-500" : "border-slate-800"
    }`;

  useEffect(() => {
    const tenantSlug = getTenantSlugFromHost();
    if (!tenantSlug) return;
    const target = new URL("https://truckerp.me/signup");
    const current = new URL(window.location.href);
    current.searchParams.forEach((value, key) => {
      target.searchParams.set(key, value);
    });
    target.searchParams.set("from", current.hostname);
    if (target.toString() !== current.toString()) {
      window.location.replace(target.toString());
    }
  }, []);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("signupDraft");
      if (!raw) return;
      const draft = JSON.parse(raw);
      const hasDraftData =
        draft?.attemptId ||
        draft?.email ||
        draft?.workspaceSlug ||
        draft?.firstName ||
        draft?.lastName ||
        draft?.companyName;
      if (hasDraftData) {
        setHasStoredDraftOnLoad(true);
        if (draft?.step === "signup" || !draft?.step) {
          setShowResume(true);
          setResumePrompt("Continue previous signup.");
          setResumeCtaLabel("Continue previous signup");
        }
      }
      if (draft?.workspaceSlug) setWorkspaceSlug(draft.workspaceSlug);
      if (draft?.email) setEmail(draft.email);
      if (draft?.confirmEmail) setConfirmEmail(draft.confirmEmail);
      if (draft?.firstName) setFirstName(draft.firstName);
      if (draft?.lastName) setLastName(draft.lastName);
      if (draft?.companyName) setCompanyName(draft.companyName);
      if (draft?.country) setCountry(draft.country);
      if (draft?.street) setStreet(draft.street);
      if (draft?.city) setCity(draft.city);
      if (draft?.region) setRegion(draft.region);
      if (draft?.postal) setPostal(draft.postal);
      if (draft?.phone) setPhone(draft.phone);
      if (draft?.acceptTerms != null) setAcceptTerms(draft.acceptTerms);
      if (draft?.isOwnerOrAdmin != null) setIsOwnerOrAdmin(draft.isOwnerOrAdmin);
      if (draft?.plan) setPlan(draft.plan);
      if (draft?.attemptId) setAttemptId(draft.attemptId);
      if (draft?.idempotencyKey) setIdempotencyKey(draft.idempotencyKey);
      if (draft?.reservationExpiresAt) setReservationExpiresAt(draft.reservationExpiresAt);
      if (draft?.step) setStep(draft.step);
    } catch {
      // ignore draft parse issues
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    if (session?.requires_account_setup) {
      nav("/company-setup");
      return;
    }
    nav("/dashboard");
  }, [isAuthenticated, session, nav]);

  useEffect(() => {
    const draft = {
      workspaceSlug,
      email,
      confirmEmail,
      firstName,
      lastName,
      companyName,
      street,
      city,
      region,
      postal,
      country,
      phone,
      acceptTerms,
      isOwnerOrAdmin,
      plan,
      attemptId,
      idempotencyKey,
      reservationExpiresAt,
      step,
      updatedAt: Date.now(),
    };
    try {
      localStorage.setItem("signupDraft", JSON.stringify(draft));
    } catch {
      // ignore storage failures
    }
  }, [
    workspaceSlug,
    email,
    confirmEmail,
    firstName,
    lastName,
    companyName,
    country,
    street,
    city,
    region,
    postal,
    phone,
    acceptTerms,
    isOwnerOrAdmin,
    plan,
    attemptId,
    idempotencyKey,
    reservationExpiresAt,
    step,
  ]);

  useEffect(() => {
    if (!attemptId) return;
    getSignupStatus(attemptId)
      .then((status) => {
        if (status?.state) {
          setAttemptState(status.state);
        }
        if (status?.state === "OTP_SENT") {
          setStep("otp");
        }
        if (status?.state === "OTP_VERIFIED" || status?.state === "PROVISIONED") {
          setStep("otp");
        }
        if (status?.state === "OTP_VERIFIED" || status?.state === "PROVISIONING") {
          if (status?.db_status === "READY" && normalizedSlug) {
            const baseDomain = baseDomainFromHost(window.location.hostname);
            window.location.href = `https://${normalizedSlug}.${baseDomain}/company-setup`;
          } else {
            setPolling(true);
          }
        }
        if (status?.reservation_expires_at) {
          setReservationExpiresAt(status.reservation_expires_at);
        }
        if (status?.db_status === "ERROR") {
          setPolling(false);
          setProvisionError(sanitizeProvisionError(status?.provision_error));
          setServerMsg("We couldn’t finish setting up your workspace. Please try again.");
        }
      })
      .catch(() => {
        // ignore status failures
      });
  }, [attemptId, normalizedSlug]);

  useEffect(() => {
    if (!polling || !attemptId) return;
    let cancelled = false;

    const tick = async () => {
      try {
        const status = await getSignupStatus(attemptId);
        if (status?.db_status === "ERROR") {
          setPolling(false);
          setProvisionError(sanitizeProvisionError(status?.provision_error));
          setServerMsg("We couldn’t finish setting up your workspace. Please try again.");
          return;
        }
        if (status?.db_status === "READY") {
          const baseDomain = baseDomainFromHost(window.location.hostname);
          const url = `https://${normalizedSlug}.${baseDomain}/company-setup`;
          window.location.href = url;
          return;
        }
      } catch {
        // ignore polling errors
      }
      if (!cancelled) {
        setTimeout(tick, 5000);
      }
    };

    tick();
    return () => {
      cancelled = true;
    };
  }, [attemptId, normalizedSlug, polling]);

  useEffect(() => {
    if (step !== "signup") return;
    if (hasStoredDraftOnLoad) return;
    const trimmedEmail = email.trim();
    if (!trimmedEmail || !normalizedSlug) {
      setShowResume(false);
      setResumePrompt(null);
      setResumeCandidate(null);
      return;
    }
    const t = setTimeout(async () => {
      try {
        const res: any = await resumeSignup({ email: trimmedEmail, slug: normalizedSlug });
        const state = res?.state;
        const cta =
          state === "PROVISIONED"
            ? "Go to workspace"
            : state === "PROVISIONING"
            ? "Finish setup"
            : state === "OTP_VERIFIED"
            ? "Continue setup"
            : "Continue previous signup";
        setResumeCandidate(res);
        setResumePrompt("Resume signup found — continue where you left off.");
        setResumeCtaLabel(cta);
        setShowResume(true);
      } catch {
        setShowResume(false);
        setResumePrompt(null);
        setResumeCandidate(null);
      }
    }, 500);
    return () => clearTimeout(t);
  }, [email, normalizedSlug, step, hasStoredDraftOnLoad]);

  // Debounced slug availability check (only when slug is long enough to be valid)
  useEffect(() => {
    setServerMsg(null);
    setWorkspaceUrl(null);

    if (!normalizedSlug) {
      setSlugState({ status: "idle" });
      return;
    }
    // Backend requires min 3 chars; avoid "checking" for partial input
    if (normalizedSlug.length < 3) {
      setSlugState({ status: "idle" });
      return;
    }

    setSlugState({ status: "checking" });
    const t = setTimeout(async () => {
      try {
        const res: any = await checkSlugAvailability(normalizedSlug);
        if (res?.available) {
          setSlugState({ status: "ok", suggestions: res?.suggestions });
        } else {
          setSlugState({
            status: "bad",
            message: "Slug is not available",
            suggestions: res?.suggestions?.length ? res.suggestions : makeSuggestions(normalizedSlug),
          });
        }
      } catch (e: any) {
        setSlugState({
          status: "bad",
          message: e?.message?.slice(0, 200) || "Invalid slug",
          suggestions: makeSuggestions(normalizedSlug),
        });
      }
    }, 450);

    return () => clearTimeout(t);
  }, [normalizedSlug]);

  // Debounced email check vs platform signup (UX only). Per-tenant auth allows the same email in different tenant DBs; login is always workspace-scoped.
  useEffect(() => {
    if (step !== "signup") {
      setEmailAvailState({ status: "idle" });
      return;
    }
    if (isAuthenticated) {
      setEmailAvailState({ status: "ok" });
      return;
    }
    const trimmed = email.trim();
    if (!trimmed || !isValidEmailFormat(trimmed)) {
      setEmailAvailState({ status: "idle" });
      return;
    }

    setEmailAvailState({ status: "checking" });
    const t = setTimeout(async () => {
      try {
        const res = await checkSignupEmailAvailability(trimmed);
        if (res.available) {
          setEmailAvailState({ status: "ok" });
        } else {
          setEmailAvailState({
            status: "taken",
            message:
              "This email already has a TruckERP account. Sign in, then use Create workspace to add another company.",
          });
        }
      } catch {
        setEmailAvailState({
          status: "bad",
          message: "Could not verify email. Try again.",
        });
      }
    }, 450);
    return () => clearTimeout(t);
  }, [email, step, isAuthenticated]);

  // Debounced phone uniqueness (digits compared to platform_users.phone)
  useEffect(() => {
    if (step !== "signup") {
      setPhoneAvailState({ status: "idle" });
      return;
    }
    if (isAuthenticated) {
      setPhoneAvailState({ status: "ok" });
      return;
    }
    if (!isValidPhone(phone)) {
      setPhoneAvailState({ status: "idle" });
      return;
    }

    setPhoneAvailState({ status: "checking" });
    const t = setTimeout(async () => {
      try {
        const res = await checkSignupPhoneAvailability(phone.trim());
        if (res.available) {
          setPhoneAvailState({ status: "ok" });
        } else {
          setPhoneAvailState({
            status: "bad",
            message: "This phone number is already being used.",
          });
        }
      } catch {
        setPhoneAvailState({
          status: "bad",
          message: "Could not verify phone. Try again.",
        });
      }
    }, 450);
    return () => clearTimeout(t);
  }, [phone, step, isAuthenticated]);

  const browserRegion = useMemo(() => {
    if (typeof navigator === "undefined") return "";
    const languages =
      navigator.languages && navigator.languages.length > 0
        ? navigator.languages
        : [navigator.language];
    for (const lang of languages) {
      const region = lang.split("-")[1];
      if (region) return region.toUpperCase();
    }
    return "";
  }, []);

  // Auto-select country based on browser region + IP (fallback)
  useEffect(() => {
    if (!country && browserRegion === "CA") {
      setCountry("CA");
    }
    if (country) return;
    let cancelled = false;
    fetch("https://ipapi.co/json/")
      .then((res) => res.json())
      .then((data) => {
        if (cancelled) return;
        const code = String(data?.country_code || "").toUpperCase();
        if (code) {
          const preferred = code === "US" && browserRegion === "CA" ? "CA" : code;
          setCountry((prev) => prev || preferred);
        }
      })
      .catch(() => {
        // ignore geo failures
      });
    return () => {
      cancelled = true;
    };
  }, [browserRegion, country]);

  function resetMessages() {
    setServerMsg(null);
    setWorkspaceUrl(null);
    setFieldErrors({});
  }

  function clearFieldError(field: string) {
    setFieldErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }

  function validateBasic(): string | null {
    const errors: Record<string, string> = {};
    if (!normalizedSlug) errors.workspaceSlug = "Please choose a workspace slug.";
    if (!email.trim()) errors.email = "Please enter your email.";
    else if (!isValidEmailFormat(email)) errors.email = "Enter a valid email (e.g. you@company.com).";
    if (!confirmEmail.trim()) errors.confirmEmail = "Please confirm your email.";
    if (email.trim() && confirmEmail.trim() && email.trim() !== confirmEmail.trim()) {
      errors.email = "Emails do not match.";
      errors.confirmEmail = "Emails do not match.";
    }
    setFieldErrors(errors);
    return errors.workspaceSlug || errors.email || errors.confirmEmail || null;
  }

  function validateDetails(): string | null {
    const errors: Record<string, string> = {};
    if (!firstName.trim()) errors.firstName = "First name is required.";
    if (!lastName.trim()) errors.lastName = "Last name is required.";
    if (!companyName.trim()) errors.companyName = "Company name is required.";
    if (!country.trim()) errors.country = "Country is required.";
    if (!street.trim()) errors.street = "Street address is required.";
    if (!city.trim()) errors.city = "City is required.";
    if (!region.trim()) errors.region = "State / Province is required.";
    if (!postal.trim()) errors.postal = "Postal / ZIP code is required.";
    if (!phone.trim()) errors.phone = "Phone is required.";
    else if (!isValidPhone(phone)) errors.phone = "Phone must have 7–15 digits (e.g. +1 555 123 4567).";
    const pwdValidation = getPasswordValidation(password);
    if (!pwdValidation.valid && pwdValidation.message) errors.password = pwdValidation.message;
    if (confirmPassword.trim() !== pwdValidation.trimmed) errors.confirmPassword = "Passwords do not match.";
    if (!acceptTerms) errors.acceptTerms = "You must accept the terms.";
    if (!isOwnerOrAdmin) errors.isOwnerOrAdmin = "You must confirm you are authorized.";
    setFieldErrors(errors);
    return (
      errors.firstName ||
      errors.lastName ||
      errors.companyName ||
      errors.country ||
      errors.street ||
      errors.city ||
      errors.region ||
      errors.postal ||
      errors.phone ||
      errors.password ||
      errors.confirmPassword ||
      errors.acceptTerms ||
      errors.isOwnerOrAdmin ||
      null
    );
  }

  async function onSignup(e: React.FormEvent) {
    e.preventDefault();
    resetMessages();

    if (authReady && isAuthenticated) {
      nav("/create-workspace");
      return;
    }

    if (breachCheckStatus === "breached") {
      setServerMsg("This password has been exposed in a data breach. Choose a different one.");
      return;
    }
    const err1 = validateBasic();
    if (err1) {
      setServerMsg(err1);
      return;
    }
    const err2 = validateDetails();
    if (err2) {
      setServerMsg(err2);
      return;
    }
    if (slugState.status === "checking") {
      setServerMsg("Checking slug availability…");
      return;
    }
    if (slugState.status === "bad") {
      setServerMsg("Choose an available workspace slug.");
      return;
    }
    if (emailAvailState.status === "checking") {
      setServerMsg("Checking email…");
      return;
    }
    if (emailAvailState.status === "bad") {
      setServerMsg(emailAvailState.message);
      return;
    }
    if (emailAvailState.status === "taken") {
      setServerMsg(emailAvailState.message);
      return;
    }
    if (phoneAvailState.status === "checking") {
      setServerMsg("Checking phone…");
      return;
    }
    if (phoneAvailState.status === "bad") {
      setServerMsg(phoneAvailState.message);
      return;
    }

    setBusy(true);
    try {
      const currentKey = idempotencyKey || (crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`);
      setIdempotencyKey(currentKey);
      const res: any = await signup(
        {
          attempt_id: attemptId || undefined,
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          email: email.trim(),
          confirm_email: confirmEmail.trim(),
          phone: phone.trim(),
          company_name: companyName.trim(),
          slug: normalizedSlug,
          address: {
            street: street.trim(),
            city: city.trim(),
            region: region.trim(),
            postal: postal.trim(),
            country: country.trim().toUpperCase(),
          },
          password: passwordValidation.trimmed,
          confirm_password: confirmPassword.trim(),
          plan,
          accept_terms: acceptTerms,
          is_owner_or_admin: isOwnerOrAdmin,
        } as any,
        currentKey
      );
      if ((res as any)?.code === "ACCOUNT_EXISTS" || (res as any)?.next_step === "SIGN_IN") {
        setServerMsg(
          "You already have an account with this email. Sign in, then use “Create workspace” on the login page to start a new company.",
        );
        return;
      }
      // Single-step signup: backend creates workspace and returns redirect_url; go there
      if ((res as any)?.redirect_url) {
        window.location.href = (res as any).redirect_url;
        return;
      }
      if ((res as any)?.requires_otp && (res as any)?.signup_id) {
        setAttemptId(String((res as any).signup_id));
        setAttemptState("OTP_SENT");
        setStep("otp");
        setServerMsg("OTP sent. Please check your email.");
        return;
      }
      // Legacy OTP flow (if backend ever returns attempt_id without redirect_url)
      if (res?.attempt_id ?? res?.tenant_id != null) setAttemptId(String(res?.attempt_id ?? res?.tenant_id));
      setAttemptState("OTP_SENT");
      setStep("otp");
      setServerMsg(res?.message || "OTP sent. Please check your email.");
    } catch (e: any) {
      setServerMsg(e?.message?.slice(0, 400) || "Signup failed");
    } finally {
      setBusy(false);
    }
  }

  async function onVerifyOtp(e: React.FormEvent) {
    e.preventDefault();
    resetMessages();

    if (!isOtpEntryAllowed) {
      setServerMsg("This signup is already verified. Continue setup.");
      return;
    }

    if (!otp.trim()) {
      setFieldErrors({ otp: "Enter the OTP code." });
      setServerMsg("Enter the OTP code.");
      return;
    }

    setBusy(true);
    try {
      const res: any = await verifyOtp({
        signup_id: attemptId || undefined,
        email: email.trim(),
        otp: otp.trim(),
      });

      if (res?.success) {
        setServerMsg(res?.message || "Verified.");
        if (res?.tenant_status === "READY") {
          setAttemptState("PROVISIONED");
        } else if (res?.poll_url) {
          setAttemptState("PROVISIONING");
        } else {
          setAttemptState("OTP_VERIFIED");
        }

        // Store for setup flow (prevents default tenant=1 issues)
        if (res?.tenant_id != null) localStorage.setItem("setup_tenant_id", String(res.tenant_id));
        if (res?.slug) localStorage.setItem("setup_slug", String(res.slug));

        const redirectUrl = res?.company_setup_url ?? res?.workspace_url;
        if (redirectUrl) {
          setWorkspaceUrl(redirectUrl);
          setPolling(false);
          window.location.href = redirectUrl;
          return;
        }
        if (res?.poll_url) {
          setServerMsg("Setting up your workspace. Please wait...");
          setPolling(true);
        }
      } else {
        setServerMsg(res?.message || "OTP verification failed");
      }
    } catch (e: any) {
      setServerMsg(e?.message?.slice(0, 400) || "OTP verification failed");
    } finally {
      setBusy(false);
    }
  }

  async function onResendOtp() {
    resetMessages();
    if (!email.trim()) {
      setServerMsg("Enter your email above first.");
      return;
    }
    setResendBusy(true);
    try {
      const res: any = await resendOtp({
        signup_id: attemptId || undefined,
        email: email.trim(),
        slug: normalizedSlug,
      });
      if (res?.status === "already_verified") {
        setServerMsg("Already verified. Continue to login or setup.");
        if (res?.setup_url) {
          window.location.href = res.setup_url;
        }
        return;
      }
      if (res?.reservation_expires_at) {
        setReservationExpiresAt(res.reservation_expires_at);
      }
      setServerMsg(res?.message || "OTP resent. Please check your email.");
    } catch (e: any) {
      setServerMsg(e?.message?.slice(0, 300) || "Resend failed");
    } finally {
      setResendBusy(false);
    }
  }

  async function onResumeSignup() {
    resetMessages();
    if (!email.trim() || !normalizedSlug) {
      setServerMsg("Enter your email and slug to resume.");
      return;
    }
    setResumeBusy(true);
    try {
      const res: any = await resumeSignup({ email: email.trim(), slug: normalizedSlug });
      if (res?.attempt_id) setAttemptId(res.attempt_id);
      if (res?.slug) setWorkspaceSlug(res.slug);
      if (res?.first_name) setFirstName(res.first_name);
      if (res?.last_name) setLastName(res.last_name);
      if (res?.company_name) setCompanyName(res.company_name);
      if (res?.phone) setPhone(res.phone);
      if (res?.country) setCountry(res.country);
      if (res?.plan) setPlan(res.plan);
      if (res?.reservation_expires_at) setReservationExpiresAt(res.reservation_expires_at);
      if (res?.state) {
        setStep("otp");
        setAttemptState(res.state);
      }
      const baseDomain = baseDomainFromHost(window.location.hostname);
      if (res?.state === "PROVISIONED" && res?.slug) {
        setWorkspaceUrl(`https://${res.slug}.${baseDomain}`);
        setServerMsg("Workspace is ready. Go to workspace.");
        return;
      }
      if (res?.state === "PROVISIONING" && res?.slug) {
        setServerMsg("Workspace provisioning in progress. Finish setup when ready.");
        setPolling(true);
        return;
      }
      if (res?.state === "OTP_VERIFIED" && res?.slug) {
        setWorkspaceUrl(`https://${res.slug}.${baseDomain}/company-setup`);
        setServerMsg("Email verified. Continue setup.");
        return;
      }
      setServerMsg("Signup resumed. Enter your OTP.");
    } catch (e: any) {
      setServerMsg(e?.message?.slice(0, 300) || "Resume failed");
    } finally {
      setResumeBusy(false);
    }
  }

  function onContinueAfterVerify() {
    resetMessages();
    const baseDomain = baseDomainFromHost(window.location.hostname);
    if (attemptState === "PROVISIONED" && normalizedSlug) {
      window.location.href = `https://${normalizedSlug}.${baseDomain}/company-setup`;
      return;
    }
    setServerMsg("Setting up your workspace. Please wait...");
    setPolling(true);
  }

  async function onChangeSlug() {
    resetMessages();
    if (!attemptId) {
      setServerMsg("Missing signup attempt.");
      return;
    }
    if (!newSlug.trim()) {
      setFieldErrors({ newSlug: "Enter a new slug." });
      setServerMsg("Enter a new slug.");
      return;
    }
    setChangeSlugBusy(true);
    try {
      const res: any = await changeSignupSlug({ attempt_id: attemptId, new_slug: newSlug.trim() });
      if (res?.slug) {
        setWorkspaceSlug(res.slug);
        if (res?.reservation_expires_at) setReservationExpiresAt(res.reservation_expires_at);
        setNewSlug("");
        setServerMsg("Slug updated. Continue with OTP.");
      }
    } catch (e: any) {
      setServerMsg(e?.message?.slice(0, 300) || "Change slug failed");
    } finally {
      setChangeSlugBusy(false);
    }
  }

  async function onRetryProvisioning() {
    resetMessages();
    if (!attemptId) {
      setServerMsg("Missing signup attempt.");
      return;
    }
    setRetryBusy(true);
    setProvisionError(null);
    try {
      const res: any = await retryProvisioning({ attempt_id: attemptId });
      if (res?.company_setup_url) {
        window.location.href = res.company_setup_url;
        return;
      }
      setServerMsg("Provisioning restarted. Please wait...");
      setPolling(true);
    } catch (e: any) {
      setServerMsg(e?.message?.slice(0, 300) || "Retry provisioning failed");
    } finally {
      setRetryBusy(false);
    }
  }

  async function onCancelSignup() {
    resetMessages();
    if (!attemptId) {
      setServerMsg("Missing signup attempt.");
      return;
    }
    try {
      await cancelSignup({ signup_id: attemptId });
      setAttemptId(null);
      setReservationExpiresAt(null);
      setAttemptState(null);
      setOtp("");
      setStep("signup");
      setServerMsg("Signup cancelled. You can start again.");
    } catch (e: any) {
      setServerMsg(e?.message?.slice(0, 300) || "Cancel failed");
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-900/40 p-8">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-sm font-semibold text-slate-400">TruckERP</div>
            <h1 className="text-2xl font-bold tracking-tight">Create your workspace</h1>
          </div>
          <button className="text-sm text-slate-400 hover:text-slate-200" onClick={() => nav("/")} type="button">
            Back to home
          </button>
        </div>

        <p className="mt-2 text-sm text-slate-400">Choose a workspace slug (your subdomain) and verify your email.</p>

        {authReady && isAuthenticated && step === "signup" ? (
          <div className="mt-4 rounded-xl border border-sky-800/60 bg-sky-950/30 p-3 text-sm text-sky-200">
            You’re already signed in. To add another company, open{" "}
            <Link to="/create-workspace" className="font-medium text-sky-100 underline">
              Create workspace
            </Link>
            . This form is for brand-new accounts only.
          </div>
        ) : null}

        {serverMsg ? (
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-200">
            {polling ? (
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-indigo-400" />
                  <div>{serverMsg}</div>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                  <div className="h-full w-1/2 animate-pulse rounded-full bg-indigo-500/70" />
                </div>
                <div className="text-xs text-slate-400">Provisioning database and workspace…</div>
              </div>
            ) : (
              <>
                <div>{serverMsg}</div>
                {serverMsg && serverMsg.toLowerCase().includes("already exists") ? (
                  <div className="mt-2">
                    <button
                      type="button"
                      className="text-indigo-400 hover:underline font-medium"
                      onClick={() => nav("/login")}
                    >
                      Sign in to your workspace
                    </button>
                  </div>
                ) : null}
              </>
            )}
            {provisionError && !polling ? (
              <div className="mt-2 text-xs text-rose-300">{provisionError}</div>
            ) : null}
            {workspaceUrl ? (
              <div className="mt-2">
                <a className="text-indigo-400 hover:underline" href={workspaceUrl}>
                  Open workspace
                </a>
              </div>
            ) : null}
          </div>
        ) : null}

        {step === "signup" && showResume ? (
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">
            <div className="text-slate-400">{resumePrompt || "Continue previous signup."}</div>
            <button
              type="button"
              className="mt-2 text-sm text-indigo-400 hover:underline disabled:opacity-60"
              onClick={onResumeSignup}
              disabled={resumeBusy}
            >
              {resumeBusy ? "Checking…" : resumeCtaLabel}
            </button>
          </div>
        ) : null}

        {step === "signup" ? (
          <form onSubmit={onSignup} className="mt-6 space-y-4">
            <div>
              <label className="block text-base text-slate-400 mb-1">Workspace slug</label>
              <input
                value={workspaceSlug}
                onChange={(e) => {
                  setWorkspaceSlug(e.target.value);
                  clearFieldError("workspaceSlug");
                }}
                className={inputClass(Boolean(fieldErrors.workspaceSlug))}
                placeholder="e.g. amir-logistics"
                autoComplete="off"
              />
              <div className="mt-2 text-xs text-slate-500">
                Your URL will be:{" "}
                <span className="text-slate-300">{normalizedSlug || "your-slug"}.truckerp.me</span>
              </div>

              <div className="mt-2 text-xs">
                {slugState.status === "idle" ? null : slugState.status === "checking" ? (
                  <span className="text-slate-400">Checking availability…</span>
                ) : slugState.status === "ok" ? (
                  <span className="text-emerald-400">Available</span>
                ) : (
                  <span className="text-amber-300">{slugState.message}</span>
                )}
              </div>

              {slugState.status === "bad" && slugState.suggestions?.length ? (
                <div className="mt-3">
                  <div className="text-xs text-slate-500 mb-2">Try one of these:</div>
                  <div className="flex flex-wrap gap-2">
                    {slugState.suggestions.map((s) => (
                      <button
                        key={s}
                        type="button"
                        className="rounded-full border border-slate-800 bg-slate-950/40 px-3 py-1 text-xs text-slate-200 hover:bg-slate-900"
                        onClick={() => setWorkspaceSlug(s)}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                  <div className="mt-2 text-xs text-slate-400">
                    If you already started signup with this slug and email, we can resend the OTP.
                  </div>
                </div>
              ) : null}
            </div>

            <div>
              <label className="block text-base text-slate-400 mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  clearFieldError("email");
                }}
                className={inputClass(
                  Boolean(fieldErrors.email) ||
                    emailAvailState.status === "bad" ||
                    emailAvailState.status === "taken",
                )}
                placeholder="you@company.com"
                autoComplete="email"
              />
              {fieldErrors.email ? (
                <p className="mt-1 text-xs text-rose-200" role="alert">
                  {fieldErrors.email}
                </p>
              ) : null}
              {!fieldErrors.email && emailAvailState.status === "checking" ? (
                <p className="mt-1 text-xs text-slate-400" role="status">
                  Checking email…
                </p>
              ) : null}
              {!fieldErrors.email && emailAvailState.status === "ok" ? (
                <p className="mt-1 text-xs text-emerald-400" role="status">
                  Email is available.
                </p>
              ) : null}
              {!fieldErrors.email && emailAvailState.status === "bad" ? (
                <p className="mt-1 text-xs text-rose-200" role="alert">
                  {emailAvailState.message}
                </p>
              ) : null}
              {!fieldErrors.email && emailAvailState.status === "taken" ? (
                <p className="mt-1 text-xs text-amber-200" role="alert">
                  {emailAvailState.message}{" "}
                  <Link to="/login" state={{ from: "/create-workspace" }} className="underline font-medium text-amber-100">
                    Sign in
                  </Link>
                  , then open{" "}
                  <Link to="/create-workspace" className="underline font-medium text-amber-100">
                    Create workspace
                  </Link>
                  .
                </p>
              ) : null}
            </div>
            <div>
              <label className="block text-base text-slate-400 mb-1">Confirm email</label>
              <input
                type="email"
                value={confirmEmail}
                onChange={(e) => {
                  setConfirmEmail(e.target.value);
                  clearFieldError("confirmEmail");
                }}
                className={inputClass(Boolean(fieldErrors.confirmEmail))}
                placeholder="you@company.com"
                autoComplete="email"
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-base text-slate-400 mb-1">First name</label>
                <input
                  value={firstName}
                  onChange={(e) => {
                    setFirstName(e.target.value);
                    clearFieldError("firstName");
                  }}
                  className={inputClass(Boolean(fieldErrors.firstName))}
                  placeholder="First name"
                  autoComplete="given-name"
                />
              </div>

              <div>
                <label className="block text-base text-slate-400 mb-1">Last name</label>
                <input
                  value={lastName}
                  onChange={(e) => {
                    setLastName(e.target.value);
                    clearFieldError("lastName");
                  }}
                  className={inputClass(Boolean(fieldErrors.lastName))}
                  placeholder="Last name"
                  autoComplete="family-name"
                />
              </div>
            </div>

            <div>
              <label className="block text-base text-slate-400 mb-1">Company name</label>
              <input
                value={companyName}
                onChange={(e) => {
                  setCompanyName(e.target.value);
                  clearFieldError("companyName");
                }}
                className={inputClass(Boolean(fieldErrors.companyName))}
                placeholder="e.g. Amir Logistics Inc"
                autoComplete="organization"
              />
            </div>

            <div>
              <label className="block text-base text-slate-400 mb-1">Street address</label>
              <input
                value={street}
                onChange={(e) => {
                  setStreet(e.target.value);
                  clearFieldError("street");
                }}
                className={inputClass(Boolean(fieldErrors.street))}
                placeholder="123 Main St"
                autoComplete="street-address"
              />
              {fieldErrors.street ? (
                <p className="mt-1 text-xs text-rose-200" role="alert">
                  {fieldErrors.street}
                </p>
              ) : null}
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div>
                <label className="block text-base text-slate-400 mb-1">City</label>
                <input
                  value={city}
                  onChange={(e) => {
                    setCity(e.target.value);
                    clearFieldError("city");
                  }}
                  className={inputClass(Boolean(fieldErrors.city))}
                  placeholder="City"
                  autoComplete="address-level2"
                />
                {fieldErrors.city ? (
                  <p className="mt-1 text-xs text-rose-200" role="alert">
                    {fieldErrors.city}
                  </p>
                ) : null}
              </div>
              <div>
                <label className="block text-base text-slate-400 mb-1">State / Province</label>
                <input
                  value={region}
                  onChange={(e) => {
                    setRegion(e.target.value);
                    clearFieldError("region");
                  }}
                  className={inputClass(Boolean(fieldErrors.region))}
                  placeholder="ON"
                  autoComplete="address-level1"
                />
                {fieldErrors.region ? (
                  <p className="mt-1 text-xs text-rose-200" role="alert">
                    {fieldErrors.region}
                  </p>
                ) : null}
              </div>
              <div>
                <label className="block text-base text-slate-400 mb-1">Postal / ZIP</label>
                <input
                  value={postal}
                  onChange={(e) => {
                    setPostal(e.target.value);
                    clearFieldError("postal");
                  }}
                  className={inputClass(Boolean(fieldErrors.postal))}
                  placeholder="M5V 1A1"
                  autoComplete="postal-code"
                />
                {fieldErrors.postal ? (
                  <p className="mt-1 text-xs text-rose-200" role="alert">
                    {fieldErrors.postal}
                  </p>
                ) : null}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-base text-slate-400 mb-1">Country</label>
                <select
                  value={country}
                  onChange={(e) => {
                    setCountry(e.target.value || "US");
                    clearFieldError("country");
                  }}
                  className={selectClass(Boolean(fieldErrors.country))}
                >
                  <option value="US">United States</option>
                  <option value="CA">Canada</option>
                  {COUNTRIES.filter((c) => c.code !== "US" && c.code !== "CA").map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-base text-slate-400 mb-1">Phone</label>
                <input
                  value={phone}
                onChange={(e) => {
                  setPhone(e.target.value);
                  clearFieldError("phone");
                }}
                className={inputClass(Boolean(fieldErrors.phone) || phoneAvailState.status === "bad")}
                placeholder="+1 555 123 4567"
                autoComplete="tel"
              />
                {fieldErrors.phone ? (
                  <p className="mt-1 text-xs text-rose-200" role="alert">
                    {fieldErrors.phone}
                  </p>
                ) : phoneAvailState.status === "checking" ? (
                  <p className="mt-1 text-xs text-slate-400" role="status">
                    Checking phone…
                  </p>
                ) : phoneAvailState.status === "ok" ? (
                  <p className="mt-1 text-xs text-emerald-400" role="status">
                    Phone is available.
                  </p>
                ) : phoneAvailState.status === "bad" ? (
                  <p className="mt-1 text-xs text-rose-200" role="alert">
                    {phoneAvailState.message}
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-slate-500">7–15 digits (E.164)</p>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-base text-slate-400 mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    clearFieldError("password");
                  }}
                  className={inputClass(
                    Boolean(fieldErrors.password) ||
                      (password.length > 0 && !passwordValidation.valid) ||
                      breachCheckStatus === "breached"
                  )}
                  placeholder="••••••••"
                  autoComplete="new-password"
                  aria-invalid={
                    (password.length > 0 && !passwordValidation.valid) || breachCheckStatus === "breached"
                  }
                  aria-describedby="password-criteria password-error"
                />
                <p id="password-criteria" className="mt-1 text-xs text-slate-500">
                  At least {PASSWORD_MIN_LENGTH} characters (passphrases encouraged). No mandatory symbols or
                  numbers. We check strength and block passwords exposed in data breaches.
                </p>
                {breachCheckStatus === "checking" && (
                  <p className="mt-1 text-xs text-slate-400" role="status">
                    Checking whether this password has been exposed…
                  </p>
                )}
                {(fieldErrors.password ||
                  (password.length > 0 && !passwordValidation.valid) ||
                  breachCheckStatus === "breached") && (
                  <p id="password-error" className="mt-1 text-xs text-rose-200" role="alert">
                    {fieldErrors.password ||
                      (breachCheckStatus === "breached"
                        ? "This password has been exposed in a data breach. Choose a different one."
                        : passwordValidation.message)}
                  </p>
                )}
              </div>

              <div>
                <label className="block text-base text-slate-400 mb-1">Confirm password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => {
                    setConfirmPassword(e.target.value);
                    clearFieldError("confirmPassword");
                  }}
                  className={inputClass(
                    Boolean(fieldErrors.confirmPassword) || (confirmPassword.length > 0 && !passwordsMatch)
                  )}
                  placeholder="••••••••"
                  autoComplete="new-password"
                  aria-invalid={confirmPassword.length > 0 && !passwordsMatch}
                />
                {((confirmPassword.length > 0 && !passwordsMatch) || fieldErrors.confirmPassword) && (
                  <p className="mt-1 text-xs text-rose-200" role="alert">
                    {fieldErrors.confirmPassword || "Passwords do not match."}
                  </p>
                )}
              </div>
            </div>

            <div className="flex items-start gap-3">
              <input
                id="accept_terms"
                type="checkbox"
                checked={acceptTerms}
                onChange={(e) => {
                  setAcceptTerms(e.target.checked);
                  clearFieldError("acceptTerms");
                }}
                className={`mt-1 h-4 w-4 rounded border-slate-700 bg-slate-950 ${
                  fieldErrors.acceptTerms ? "ring-2 ring-rose-500/70" : ""
                }`}
              />
              <label htmlFor="accept_terms" className="text-sm text-slate-300">
                I accept the terms and conditions
              </label>
            </div>

            <div className="flex items-start gap-3">
              <input
                id="is_owner"
                type="checkbox"
                checked={isOwnerOrAdmin}
                onChange={(e) => {
                  setIsOwnerOrAdmin(e.target.checked);
                  clearFieldError("isOwnerOrAdmin");
                }}
                className={`mt-1 h-4 w-4 rounded border-slate-700 bg-slate-950 ${
                  fieldErrors.isOwnerOrAdmin ? "ring-2 ring-rose-500/70" : ""
                }`}
              />
              <label htmlFor="is_owner" className="text-sm text-slate-300">
                I am the owner/admin for this company
              </label>
            </div>

            <div className="flex gap-3">
              <button
                disabled={sendOtpDisabled}
                className="w-full rounded-lg bg-indigo-600 py-2 font-semibold hover:bg-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed"
                type="submit"
                title={
                  sendOtpDisabled && !busy
                    ? breachCheckStatus === "breached"
                      ? "This password was exposed in a data breach. Choose a different one."
                      : breachCheckStatus === "checking"
                        ? "Checking password…"
                        : !passwordValidation.valid
                          ? "Meet password criteria first."
                          : !passwordsMatch
                            ? "Passwords must match."
                            : undefined
                    : undefined
                }
              >
                {busy ? "Sending OTP…" : "Send OTP"}
              </button>
            </div>

            <div className="text-center text-xs text-slate-500">
              Plan:{" "}
              <select
                value={plan}
                onChange={(e) => setPlan(e.target.value)}
                className="ml-2 rounded-md bg-slate-950 border border-slate-800 px-2 py-1 text-xs outline-none focus:border-indigo-500"
                >
                  <option value="trial">Trial</option>
                  <option value="basic">Basic</option>
                  <option value="pro">Pro</option>
                  <option value="enterprise">Enterprise</option>
                </select>
            </div>

            <div className="text-center text-sm text-slate-400">
              Already have a workspace?{" "}
              <button type="button" className="text-indigo-400 hover:underline" onClick={() => nav("/login")}>
                Login
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={onVerifyOtp} className="mt-6 space-y-4">
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">
              <div>
                <span className="text-slate-500">Workspace:</span>{" "}
                <span className="text-slate-200">{normalizedSlug || "your-slug"}.truckerp.me</span>
              </div>
              <div>
                <span className="text-slate-500">Email:</span> <span className="text-slate-200">{email || "—"}</span>
              </div>
              {reservationExpiresAt ? (
                <div>
                  <span className="text-slate-500">Reservation expires:</span>{" "}
                  <span className="text-slate-200">
                    {new Date(reservationExpiresAt).toLocaleString()}
                  </span>
                </div>
              ) : null}
            </div>

            {isOtpEntryAllowed ? (
              <>
                <div>
                  <label className="block text-base text-slate-400 mb-1">OTP code</label>
                  <input
                    value={otp}
                    onChange={(e) => {
                      setOtp(e.target.value);
                      clearFieldError("otp");
                    }}
                    className={inputClass(Boolean(fieldErrors.otp))}
                    placeholder="123456"
                    autoComplete="one-time-code"
                  />
                </div>

                <button
                  disabled={busy}
                  className="w-full rounded-lg bg-indigo-600 py-2 font-semibold hover:bg-indigo-500 disabled:opacity-60"
                  type="submit"
                >
                  {busy ? "Verifying…" : "Verify & Continue"}
                </button>
              </>
            ) : (
              <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">
                <div className="text-slate-400">Email already verified.</div>
                <button
                  type="button"
                  className="mt-2 text-sm text-indigo-400 hover:underline"
                  onClick={onContinueAfterVerify}
                >
                  {attemptState === "PROVISIONED" ? "Go to setup" : "Continue setup"}
                </button>
              </div>
            )}

            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-sm">
              <div className="text-slate-400 mb-2">Need to change your slug?</div>
              <div className="flex gap-2">
                <input
                  value={newSlug}
                  onChange={(e) => {
                    setNewSlug(e.target.value);
                    clearFieldError("newSlug");
                  }}
                  className={inputClass(Boolean(fieldErrors.newSlug))}
                  placeholder="new-workspace-slug"
                />
                <button
                  type="button"
                  className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-sm font-semibold text-slate-200 hover:bg-slate-900 disabled:opacity-60"
                  onClick={onChangeSlug}
                  disabled={changeSlugBusy}
                >
                  {changeSlugBusy ? "Saving…" : "Update"}
                </button>
              </div>
            </div>

            <button
              type="button"
              className="w-full rounded-lg border border-slate-800 bg-slate-950/40 py-2 font-semibold text-slate-200 hover:bg-slate-900 disabled:opacity-60"
              onClick={onResendOtp}
              disabled={resendBusy}
            >
              {resendBusy ? "Resending…" : "Resend code"}
            </button>

            {polling || provisionError ? (
              <button
                type="button"
                className="w-full rounded-lg border border-slate-800 bg-slate-950/40 py-2 font-semibold text-slate-200 hover:bg-slate-900 disabled:opacity-60"
                onClick={onRetryProvisioning}
                disabled={retryBusy}
              >
                {retryBusy ? "Retrying…" : "Retry provisioning"}
              </button>
            ) : null}

            <button
              type="button"
              className="w-full rounded-lg border border-slate-800 bg-slate-950/40 py-2 font-semibold text-slate-200 hover:bg-slate-900"
              onClick={() => {
                setOtp("");
                setStep("details");
                setServerMsg(null);
              }}
            >
              Back
            </button>

            <button
              type="button"
              className="w-full rounded-lg border border-rose-500/40 bg-rose-500/10 py-2 font-semibold text-rose-200 hover:bg-rose-500/20"
              onClick={onCancelSignup}
            >
              Cancel signup
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
