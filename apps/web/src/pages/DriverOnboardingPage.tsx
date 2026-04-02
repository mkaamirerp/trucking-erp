import { useState, useEffect, useCallback } from "react";
import {
  createDriverOnboardingSubmission,
  getMyDriverOnboardingSubmission,
  uploadDriverLicense,
  swapDriverLicenseFrontBack,
  submitDriverOnboardingSubmission,
  DriverOnboardingSubmission,
  DriverOnboardingSubmissionCreate,
} from "../api";

const ACCEPT_LICENSE = "image/jpeg,image/png,image/heic,image/heif,.heic,.heif,application/pdf";

export default function DriverOnboardingPage() {
  const [submission, setSubmission] = useState<DriverOnboardingSubmission | null>(null);
  const [form, setForm] = useState<DriverOnboardingSubmissionCreate>({
    first_name: "",
    last_name: "",
    phone: "",
    email: "",
    address_street: "",
    address_city: "",
    address_region: "",
    address_postal: "",
    address_country: "",
    driver_license_number: "",
    license_region: "",
    license_expiry: "",
    notes: "",
  });
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [step2Complete, setStep2Complete] = useState(false);
  const [manualConfirm, setManualConfirm] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDraft = useCallback(async () => {
    try {
      const me = await getMyDriverOnboardingSubmission();
      setSubmission(me ?? null);
      if (me) {
        setForm({
          first_name: me.first_name ?? "",
          last_name: me.last_name ?? "",
          phone: me.phone ?? "",
          email: me.email ?? "",
          address_street: me.address_street ?? "",
          address_city: me.address_city ?? "",
          address_region: me.address_region ?? "",
          address_postal: me.address_postal ?? "",
          address_country: me.address_country ?? "",
          driver_license_number: me.driver_license_number ?? "",
          license_region: me.license_region ?? "",
          license_expiry: me.license_expiry ?? "",
          notes: me.notes ?? "",
        });
      }
    } catch {
      setSubmission(null);
    }
  }, []);

  useEffect(() => {
    loadDraft();
  }, [loadDraft]);

  const ensureDraft = async (): Promise<DriverOnboardingSubmission> => {
    if (submission?.status === "DRAFT") return submission;
    setLoading(true);
    setError(null);
    try {
      const res = await createDriverOnboardingSubmission({ ...form, submit: false });
      setSubmission(res.submission);
      return res.submission;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Could not create draft";
      setError(msg);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const onLicenseFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    setError(null);
    setUploading(true);
    try {
      let sub = submission;
      if (!sub || sub.status !== "DRAFT") {
        sub = await ensureDraft();
      }
      const front = files[0];
      const back = files.length > 1 ? files[1] : undefined;
      await uploadDriverLicense(sub.id, front, back ?? null);
      await loadDraft();
      const updated = await getMyDriverOnboardingSubmission();
      if (updated?.extraction_status === "EXTRACTED" && updated.extraction_result_json) {
        try {
          const result = typeof updated.extraction_result_json === "string"
            ? JSON.parse(updated.extraction_result_json)
            : updated.extraction_result_json;
          const fields = result?.fields;
          if (fields) {
            setForm((prev) => ({
              ...prev,
              first_name: fields.first_name?.chosen?.value ?? prev.first_name,
              last_name: fields.last_name?.chosen?.value ?? prev.last_name,
              driver_license_number: fields.license_number?.chosen?.value ?? prev.driver_license_number,
              license_region: fields.issuing_region?.chosen?.value ?? prev.license_region,
              address_street: fields.address_street?.chosen?.value ?? prev.address_street,
              address_city: fields.address_city?.chosen?.value ?? prev.address_city,
              address_region: fields.address_region?.chosen?.value ?? prev.address_region,
              address_postal: fields.address_postal?.chosen?.value ?? prev.address_postal,
              address_country: fields.country?.chosen?.value ?? prev.address_country,
              license_expiry: fields.expiry_date?.chosen?.value ?? prev.license_expiry,
            }));
          }
        } catch {
          // ignore prefill parse errors
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const onSwapFrontBack = async () => {
    if (!submission?.id) return;
    setError(null);
    setLoading(true);
    try {
      await swapDriverLicenseFrontBack(submission.id);
      await loadDraft();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Swap failed");
    } finally {
      setLoading(false);
    }
  };

  const hasLicenseUploads =
    submission?.license_uploads_json &&
    typeof submission.license_uploads_json === "object" &&
    "front" in (submission.license_uploads_json as object) &&
    "back" in (submission.license_uploads_json as object);

  const canSubmit =
    submission?.status === "DRAFT" &&
    step2Complete &&
    (submission.extraction_status === "EXTRACTED" || manualConfirm) &&
    (form.first_name?.trim() && form.last_name?.trim() && form.driver_license_number?.trim());

  const saveDraft = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await createDriverOnboardingSubmission({ ...form, submit: false });
      setSubmission(res.submission);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setLoading(false);
    }
  };

  const submit = async (doSubmit: boolean) => {
    if (!doSubmit) {
      await saveDraft();
      return;
    }
    if (!submission?.id) {
      setError("Save a draft first.");
      return;
    }
    setLoading(true);
    setError(null);
    setSuccessMessage(null);
    try {
      await createDriverOnboardingSubmission({ ...form, submit: true });
      setSuccessMessage("Submitted for admin review.");
      await loadDraft();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Submit failed");
    } finally {
      setLoading(false);
    }
  };

  const onChange = (key: keyof DriverOnboardingSubmissionCreate, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h2 className="text-xl font-semibold">Driver Onboarding</h2>
        <p className="text-sm text-gray-600">
          Two steps: upload your license and confirm basic info, then add job history and references.
        </p>
      </div>

      {successMessage && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {successMessage}
        </div>
      )}
      {error && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          {error}
        </div>
      )}

      {/* Step 1 — License upload + Basic info */}
      <section className="space-y-4">
        <h3 className="text-lg font-medium">Step 1: License &amp; basic info</h3>

        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
          <label className="block text-sm font-medium text-gray-700">License upload</label>
          <p className="mt-1 text-xs text-gray-500">
            First file = front, second = back. Accepted: JPG, PNG, HEIC, PDF.
          </p>
          <input
            type="file"
            accept={ACCEPT_LICENSE}
            multiple
            className="mt-2 block w-full text-sm text-gray-600 file:mr-4 file:rounded file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-blue-700"
            disabled={uploading || (submission?.status !== "DRAFT" && !!submission)}
            onChange={(e) => onLicenseFiles(e.target.files)}
          />
          {uploading && (
            <p className="mt-2 text-sm text-blue-600">Reading your license…</p>
          )}
          {submission?.extraction_status === "EXTRACTING" && !uploading && (
            <p className="mt-2 text-sm text-blue-600">Reading your license…</p>
          )}
          {submission?.extraction_status === "EXTRACTION_FAILED" && (
            <p className="mt-2 text-sm text-amber-600">Extraction failed. You can enter details manually.</p>
          )}
          {hasLicenseUploads && (
            <button
              type="button"
              className="mt-2 text-sm text-blue-600 hover:underline"
              onClick={onSwapFrontBack}
              disabled={loading}
            >
              Swap front / back
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label className="text-sm font-medium">First name</label>
            <input
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.first_name ?? ""}
              onChange={(e) => onChange("first_name", e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">Last name</label>
            <input
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.last_name ?? ""}
              onChange={(e) => onChange("last_name", e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">Phone</label>
            <input
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.phone ?? ""}
              onChange={(e) => onChange("phone", e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">Email</label>
            <input
              type="email"
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.email ?? ""}
              onChange={(e) => onChange("email", e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <label className="text-sm font-medium">Street address</label>
            <input
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.address_street ?? ""}
              onChange={(e) => onChange("address_street", e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">City</label>
            <input
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.address_city ?? ""}
              onChange={(e) => onChange("address_city", e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">Region/State</label>
            <input
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.address_region ?? ""}
              onChange={(e) => onChange("address_region", e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">Postal code</label>
            <input
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.address_postal ?? ""}
              onChange={(e) => onChange("address_postal", e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">Country</label>
            <input
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.address_country ?? ""}
              onChange={(e) => onChange("address_country", e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">License number</label>
            <input
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.driver_license_number ?? ""}
              onChange={(e) => onChange("driver_license_number", e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">License region</label>
            <input
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.license_region ?? ""}
              onChange={(e) => onChange("license_region", e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium">License expiry</label>
            <input
              type="date"
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              value={form.license_expiry ?? ""}
              onChange={(e) => onChange("license_expiry", e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <label className="text-sm font-medium">Notes</label>
            <textarea
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
              rows={2}
              value={form.notes ?? ""}
              onChange={(e) => onChange("notes", e.target.value)}
            />
          </div>
        </div>

        {!submission?.extraction_status && submission?.status === "DRAFT" && (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={manualConfirm}
              onChange={(e) => setManualConfirm(e.target.checked)}
            />
            I will enter my details manually (no license upload)
          </label>
        )}
      </section>

      {/* Step 2 — Placeholders */}
      <section className="space-y-4">
        <h3 className="text-lg font-medium">Step 2: Job history, references &amp; 3-year docs</h3>
        <div className="rounded-lg border border-gray-200 bg-gray-100 p-4 text-sm text-gray-600">
          <p>References (2 required), job history (last 3 jobs), and 3-year documents — coming next.</p>
          <label className="mt-3 flex items-center gap-2">
            <input
              type="checkbox"
              checked={step2Complete}
              onChange={(e) => setStep2Complete(e.target.checked)}
            />
            I have completed job history and references (placeholder)
          </label>
        </div>
      </section>

      <div className="flex flex-wrap gap-3">
        <button
          className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          onClick={saveDraft}
          disabled={loading}
        >
          Save Draft
        </button>
        <button
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          onClick={() => submit(true)}
          disabled={loading || !canSubmit}
          title={
            !canSubmit
              ? "Complete step 2 and ensure basic info (name, license number) is filled. Upload license or check manual entry."
              : undefined
          }
        >
          Submit for review
        </button>
      </div>
    </div>
  );
}
