import { useEffect, useState } from "react";
import { getCompanyProfile, CompanyProfile } from "../api";

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  if (value == null || value === "") return null;
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wider text-[#64748b]">{label}</dt>
      <dd className="mt-1 text-sm text-[#e8edf5]">{value}</dd>
    </div>
  );
}

export default function AdminCompanyProfilePage() {
  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-[#94a3b8]">
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-['Barlow_Condensed'] text-3xl font-bold tracking-tight text-[#e8edf5]">
            Company Profile
          </h1>
          <p className="mt-1 text-sm text-[#64748b]">
            Business information for invoices and pay stubs. Edit support coming soon.
          </p>
        </div>
        <button
          type="button"
          disabled
          className="rounded-lg border border-[#1e293b] bg-[#0f1420] px-4 py-2 text-sm font-medium text-[#64748b] cursor-not-allowed"
        >
          Edit (coming soon)
        </button>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-xl border border-[#1e293b] bg-[#0a0e14] p-6">
          <h2 className="mb-4 font-semibold text-[#e8edf5]">Workspace</h2>
          <dl className="space-y-4">
            <Field label="Subdomain / Slug" value={profile.slug} />
            <Field label="Name" value={profile.tenant_name} />
            <Field label="Timezone" value={profile.timezone} />
            <Field label="Base Currency" value={profile.base_currency} />
            <Field label="Country" value={profile.country_code} />
          </dl>
        </section>

        <section className="rounded-xl border border-[#1e293b] bg-[#0a0e14] p-6">
          <h2 className="mb-4 font-semibold text-[#e8edf5]">Company Identity</h2>
          <dl className="space-y-4">
            <Field label="Company Name" value={profile.tenant_name} />
            <Field label="Legal Name" value={profile.legal_name} />
            <Field label="Company Phone" value={profile.company_phone} />
            <Field label="Company Email" value={profile.company_email} />
          </dl>
        </section>

        <section className="rounded-xl border border-[#1e293b] bg-[#0a0e14] p-6 md:col-span-2">
          <h2 className="mb-4 font-semibold text-[#e8edf5]">Business Address</h2>
          <p className="mb-4 text-sm text-[#64748b]">
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
            <p className="text-sm text-[#94a3b8]">No business address on file.</p>
          )}
        </section>

        <section className="rounded-xl border border-[#1e293b] bg-[#0a0e14] p-6 md:col-span-2">
          <h2 className="mb-4 font-semibold text-[#e8edf5]">Business Registration</h2>
          <p className="mb-4 text-sm text-[#64748b]">USDOT / MC / CVOR / operator license / HST as available.</p>
          <dl className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
            <Field label="USDOT Number" value={profile.usdot_number} />
            <Field label="MC Number" value={profile.mc_number} />
            <Field label="CVOR Number" value={profile.cvor_number} />
            <Field label="Operator License" value={profile.operator_license} />
            <Field label="HST Number" value={profile.hst_number} />
            <Field label="W9 on File" value={profile.has_w9_file ? "Yes" : null} />
          </dl>
          {profile.setup_completed_at && (
            <p className="mt-4 text-xs text-[#64748b]">
              Setup completed: {new Date(profile.setup_completed_at).toLocaleString()}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
