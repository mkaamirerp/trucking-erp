import { useEffect, useState } from "react";
import { getCompanyProfile, patchDocRequestLinkExpiryDays, patchPersonSetupUiMode, type CompanyProfile, type PersonSetupUiMode } from "../api";

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  if (value == null || value === "") return null;
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">{label}</dt>
      <dd className="mt-1 text-sm text-[var(--trk-text)]">{value}</dd>
    </div>
  );
}

export default function AdminCompanyProfilePage() {
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [personSetupModeSaving, setPersonSetupModeSaving] = useState(false);
  const [personSetupLocalMode, setPersonSetupLocalMode] = useState<PersonSetupUiMode>("combined");
  const [expiryDays, setExpiryDays] = useState<number>(21);
  const [expiryInput, setExpiryInput] = useState<string>("21");
  const [expirySaving, setExpirySaving] = useState(false);
  const [expiryError, setExpiryError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCompanyProfile()
      .then((data) => {
        if (!cancelled) setProfile(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || "Failed to load company profile");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!profile) return;
    const raw = profile.person_setup_ui_mode;
    setPersonSetupLocalMode(raw === "segmented" ? "segmented" : "combined");
  }, [profile?.person_setup_ui_mode]);

  useEffect(() => {
    if (!profile) return;
    const days = profile.doc_request_link_expiry_days ?? 21;
    setExpiryDays(days);
    setExpiryInput(String(days));
  }, [profile?.doc_request_link_expiry_days]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-[var(--trk-text-muted)]">
        Loading company profile...
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-4 text-red-400">
        {error}
      </div>
    );
  }

  if (!profile) return null;

  const savePersonSetupUiMode = async (next: PersonSetupUiMode) => {
    setPersonSetupModeSaving(true);
    setError(null);
    try {
      await patchPersonSetupUiMode(next);
      setPersonSetupLocalMode(next);
      const data = await getCompanyProfile();
      setProfile(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not save people onboarding mode.");
    } finally {
      setPersonSetupModeSaving(false);
    }
  };

  const saveExpiryDays = async () => {
    const val = parseInt(expiryInput, 10);
    if (isNaN(val) || val < 1 || val > 90) {
      setExpiryError("Must be a number between 1 and 90.");
      return;
    }
    setExpirySaving(true);
    setExpiryError(null);
    try {
      const res = await patchDocRequestLinkExpiryDays(val);
      setExpiryDays(res.doc_request_link_expiry_days);
      setExpiryInput(String(res.doc_request_link_expiry_days));
    } catch (err: unknown) {
      setExpiryError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setExpirySaving(false);
    }
  };

  const hasAddress =
    profile.street || profile.city || profile.region || profile.postal || profile.country;
  const hasFallback =
    profile.company_phone_is_fallback ||
    profile.company_email_is_fallback ||
    profile.address_is_fallback;
  const showIncompleteWarning = hasFallback || !profile.is_document_contact_complete;

  return (
    <div className="space-y-8">
      {showIncompleteWarning && (
        <div
          className="rounded-lg border border-amber-700/60 bg-amber-950/30 p-4 text-amber-200"
          role="alert"
        >
          <p className="font-medium">Business contact information is incomplete.</p>
          <p className="mt-1 text-sm">
            Please save company phone, email, and address in Company Settings before using invoices
            or pay stubs. Document generation requires canonical company profile data, not owner
            contact info.
          </p>
        </div>
      )}

      <section className="rounded-xl border border-amber-900/40 bg-[var(--trk-bg)] p-6">
        <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-amber-500/90">Tenant admin</p>
        <h2 className="mb-2 text-lg font-semibold text-[var(--trk-text)]">People · onboarding workspace mode</h2>
        <p className="mb-4 text-sm text-[var(--trk-text-muted)] leading-relaxed">
          Tenant-wide, people-level setting (<code className="text-[var(--trk-text-muted)]">person_setup_ui_mode</code>).
          <strong className="font-medium text-[var(--trk-text)]"> Combined (ON)</strong> — small teams: driver setup appears on the
          onboarding review page; <strong className="font-medium text-[var(--trk-text)]">Approve</strong> stays blocked until that
          in-page setup is complete (saves are always allowed).
          <strong className="font-medium text-[var(--trk-text)]"> Segmented (OFF)</strong> — larger orgs: that setup is hidden here;
          managers can save and approve; downstream setup stays pending for HR/Payroll later.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={personSetupModeSaving}
            onClick={() => void savePersonSetupUiMode("combined")}
            className={`rounded-lg border px-4 py-2.5 text-sm font-semibold transition-colors ${
              personSetupLocalMode === "combined"
                ? "border-amber-500/70 bg-amber-500/15 text-amber-100"
                : "border-[var(--trk-border)] bg-[var(--trk-surface)] text-[var(--trk-text-muted)] hover:border-[var(--trk-border-strong)] hover:text-[var(--trk-text)]"
            }`}
          >
            Combined — ON
          </button>
          <button
            type="button"
            disabled={personSetupModeSaving}
            onClick={() => void savePersonSetupUiMode("segmented")}
            className={`rounded-lg border px-4 py-2.5 text-sm font-semibold transition-colors ${
              personSetupLocalMode === "segmented"
                ? "border-sky-500/70 bg-sky-500/15 text-sky-100"
                : "border-[var(--trk-border)] bg-[var(--trk-surface)] text-[var(--trk-text-muted)] hover:border-[var(--trk-border-strong)] hover:text-[var(--trk-text)]"
            }`}
          >
            Segmented — OFF
          </button>
          {personSetupModeSaving && <span className="text-xs text-[var(--trk-text-muted)]">Saving…</span>}
        </div>
      </section>

      <section className="rounded-xl border border-amber-900/40 bg-[var(--trk-bg)] p-6">
        <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-amber-500/90">Tenant admin</p>
        <h2 className="mb-2 text-lg font-semibold text-[var(--trk-text)]">Onboarding · Document request link expiry</h2>
        <p className="mb-4 text-sm text-[var(--trk-text-muted)] leading-relaxed">
          When you send a document request to an applicant, how many days the link stays active.
          The applicant can upload documents and come back multiple times until the link expires or all documents are submitted.
          Range: 1–90 days.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="number"
            min={1}
            max={90}
            value={expiryInput}
            onChange={(e) => setExpiryInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void saveExpiryDays(); }}
            className="w-24 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] focus:border-amber-500/50 focus:outline-none"
          />
          <span className="text-sm text-[var(--trk-text-muted)]">days</span>
          <button
            type="button"
            disabled={expirySaving || parseInt(expiryInput, 10) === expiryDays}
            onClick={() => void saveExpiryDays()}
            className="rounded-lg border border-amber-500/70 bg-amber-500/15 px-4 py-2 text-sm font-semibold text-amber-100 transition-colors hover:bg-amber-500/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {expirySaving ? "Saving…" : "Save"}
          </button>
          {expiryError && <span className="text-xs text-red-400">{expiryError}</span>}
          {!expiryError && <span className="text-xs text-[var(--trk-text-muted)]">Currently: {expiryDays} days</span>}
        </div>
      </section>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-['Barlow_Condensed'] text-3xl font-bold tracking-tight text-[var(--trk-text)]">
            Company Profile
          </h1>
          <p className="mt-1 text-sm text-[var(--trk-text-muted)]">
            Business information for invoices and pay stubs. Edit support coming soon.
          </p>
        </div>
        <button
          type="button"
          disabled
          className="rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] px-4 py-2 text-sm font-medium text-[var(--trk-text-muted)] cursor-not-allowed"
        >
          Edit (coming soon)
        </button>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-xl border border-[var(--trk-border)] bg-[var(--trk-bg)] p-6">
          <h2 className="mb-4 font-semibold text-[var(--trk-text)]">Workspace</h2>
          <dl className="space-y-4">
            <Field label="Subdomain / Slug" value={profile.slug} />
            <Field label="Name" value={profile.tenant_name} />
            <Field label="Timezone" value={profile.timezone} />
            <Field label="Base Currency" value={profile.base_currency} />
            <Field label="Country" value={profile.country_code} />
          </dl>
        </section>

        <section className="rounded-xl border border-[var(--trk-border)] bg-[var(--trk-bg)] p-6">
          <h2 className="mb-4 font-semibold text-[var(--trk-text)]">Company Identity</h2>
          <dl className="space-y-4">
            <Field label="Company Name" value={profile.tenant_name} />
            <Field label="Legal Name" value={profile.legal_name} />
            <Field label="Company Phone" value={profile.company_phone} />
            <Field label="Company Email" value={profile.company_email} />
          </dl>
        </section>

        <section className="rounded-xl border border-[var(--trk-border)] bg-[var(--trk-bg)] p-6 md:col-span-2">
          <h2 className="mb-4 font-semibold text-[var(--trk-text)]">Business Address</h2>
          <p className="mb-4 text-sm text-[var(--trk-text-muted)]">
            Mailing/business address for invoices, pay stubs, and documents.
          </p>
          {hasAddress ? (
            <dl className="space-y-4">
              <Field label="Street" value={profile.street} />
              <Field label="City" value={profile.city} />
              <Field label="Region / State" value={profile.region} />
              <Field label="Postal / ZIP" value={profile.postal} />
              <Field label="Country" value={profile.country} />
            </dl>
          ) : (
            <p className="text-sm text-[var(--trk-text-muted)]">No business address on file.</p>
          )}
        </section>

        <section className="rounded-xl border border-[var(--trk-border)] bg-[var(--trk-bg)] p-6 md:col-span-2">
          <h2 className="mb-4 font-semibold text-[var(--trk-text)]">Business Registration</h2>
          <p className="mb-4 text-sm text-[var(--trk-text-muted)]">USDOT / MC / CVOR / operator license / HST as available.</p>
          <dl className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
            <Field label="USDOT Number" value={profile.usdot_number} />
            <Field label="MC Number" value={profile.mc_number} />
            <Field label="CVOR Number" value={profile.cvor_number} />
            <Field label="Operator License" value={profile.operator_license} />
            <Field label="HST Number" value={profile.hst_number} />
            <Field label="W9 on File" value={profile.has_w9_file ? "Yes" : null} />
          </dl>
          {profile.setup_completed_at && (
            <p className="mt-4 text-xs text-[var(--trk-text-muted)]">
              Setup completed: {new Date(profile.setup_completed_at).toLocaleString()}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
