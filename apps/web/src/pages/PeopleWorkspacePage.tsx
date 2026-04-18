import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import {
  getPersonWorkspaceDetail,
  listPeopleForWorkspace,
  listPersonWorkspaceAuditLog,
  patchPersonDriverProfile,
  patchPersonWorkspaceCore,
  type PeopleAuditLogEntry,
  type PeopleDetail,
  type PeopleListItem,
} from "../api";
import DriverCompensationSetupAdminPanel from "../components/DriverCompensationSetupAdminPanel";
import DriverPersonExtensionAdminPanel from "../components/DriverPersonExtensionAdminPanel";
import { OPS } from "../routes";

const C = {
  bg: "var(--trk-bg)",
  card: "var(--trk-surface)",
  border: "var(--trk-border)",
  text: "var(--trk-text)",
  muted: "var(--trk-text-muted)",
  accent: "var(--trk-heading)",
};

function fmt(v: string | null | undefined) {
  if (v == null || v === "") return "—";
  return v;
}

function FormField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium" style={{ color: C.muted }}>
        {label}
      </span>
      {children}
    </label>
  );
}

function PeopleListView() {
  const [items, setItems] = useState<PeopleListItem[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listPeopleForWorkspace({ q: q.trim() || undefined, limit: 200, offset: 0 });
      setItems(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load people.");
    } finally {
      setLoading(false);
    }
  }, [q]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="min-h-screen overflow-x-hidden text-[var(--trk-text)]" style={{ background: C.bg, margin: -24 }}>
      <div className="relative px-8 py-8">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div
              className="mb-2 font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--trk-heading)]"
              style={{ color: C.accent }}
            >
              Operations
            </div>
            <h1 className="font-['Barlow_Condensed',sans-serif] text-4xl font-extrabold tracking-tight" style={{ color: C.text }}>
              People
            </h1>
            <p className="mt-2 max-w-xl text-sm" style={{ color: C.muted }}>
              Maintained person records after onboarding. Edit core contact and address here; driver classification and pay use linked
              workspaces.
            </p>
          </div>
        </div>

        <div className="mb-6 flex flex-wrap items-center gap-3">
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void load()}
            placeholder="Search name, email, phone…"
            className="min-w-[240px] max-w-md flex-1 rounded-lg border px-4 py-2.5 text-sm outline-none"
            style={{ borderColor: C.border, background: C.card, color: C.text }}
          />
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-lg px-5 py-2.5 text-sm font-semibold text-[var(--trk-bg)]"
            style={{ background: C.accent }}
          >
            Search
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>
        )}

        <div className="overflow-hidden rounded-2xl border" style={{ borderColor: C.border, background: C.card }}>
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b" style={{ borderColor: C.border }}>
                <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-wider" style={{ color: C.muted }}>
                  Name
                </th>
                <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-wider" style={{ color: C.muted }}>
                  Email
                </th>
                <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-wider" style={{ color: C.muted }}>
                  Phone
                </th>
                <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-wider" style={{ color: C.muted }}>
                  Location
                </th>
                <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-wider" style={{ color: C.muted }}>
                  Active
                </th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center" style={{ color: C.muted }}>
                    Loading…
                  </td>
                </tr>
              )}
              {!loading &&
                items.map((p) => (
                  <tr key={p.id} className="border-b transition hover:bg-[#161b27]" style={{ borderColor: C.border }}>
                    <td className="px-4 py-3">
                      <Link className="font-medium hover:underline" style={{ color: C.accent }} to={OPS.PEOPLE_DETAIL(p.id)}>
                        {[p.first_name, p.last_name].filter(Boolean).join(" ") || `Person #${p.id}`}
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: C.muted }}>
                      {fmt(p.email)}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: C.muted }}>
                      {fmt(p.phone)}
                    </td>
                    <td className="px-4 py-3 text-xs" style={{ color: C.muted }}>
                      {[p.city, p.region].filter(Boolean).join(", ") || "—"}
                    </td>
                    <td className="px-4 py-3 text-xs">{p.is_active ? "Yes" : "No"}</td>
                  </tr>
                ))}
              {!loading && items.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center" style={{ color: C.muted }}>
                    No people match your search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

type FormState = {
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  street_address: string;
  city: string;
  region: string;
  postal_code: string;
  zip_code: string;
  country: string;
  notes: string;
  is_active: boolean;
};

function detailToForm(d: PeopleDetail): FormState {
  return {
    first_name: d.first_name ?? "",
    last_name: d.last_name ?? "",
    phone: d.phone ?? "",
    email: d.email ?? "",
    street_address: d.street_address ?? "",
    city: d.city ?? "",
    region: d.region ?? "",
    postal_code: d.postal_code ?? "",
    zip_code: d.zip_code ?? "",
    country: d.country ?? "",
    notes: d.notes ?? "",
    is_active: d.is_active,
  };
}

type DriverFormState = {
  license_number: string;
  license_region: string;
  license_expiry: string;
  is_active: boolean;
};

function hasActiveDriverRole(d: PeopleDetail): boolean {
  return d.roles.some((r) => r.role_code.toUpperCase() === "DRIVER" && r.is_active);
}

function hasActiveOperationalDriver(d: PeopleDetail): boolean {
  return d.operational_drivers.some((od) => od.is_active);
}

function peopleMaintenanceAuditActionLabel(action: string): string {
  switch (action) {
    case "people_core_patch":
      return "Person — core fields";
    case "people_driver_profile_patch":
      return "Driver profile / license";
    case "people_compensation_patch":
      return "Compensation";
    case "people_driver_role_configuration_patch":
      return "Role-attached configuration (driver)";
    default:
      return action;
  }
}

function formatAuditValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") {
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  return String(v);
}

function detailToDriverForm(d: PeopleDetail): DriverFormState {
  const dp = d.driver_profile;
  const exp = dp?.license_expiry;
  return {
    license_number: dp?.license_number ?? "",
    license_region: dp?.license_region ?? "",
    license_expiry: typeof exp === "string" && exp.length >= 10 ? exp.slice(0, 10) : "",
    is_active: dp?.is_active ?? true,
  };
}

function PersonDetailView() {
  const { personId } = useParams<{ personId: string }>();
  const navigate = useNavigate();
  const id = personId ? Number(personId) : NaN;

  const [detail, setDetail] = useState<PeopleDetail | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [driverForm, setDriverForm] = useState<DriverFormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingDriver, setSavingDriver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [auditEntries, setAuditEntries] = useState<PeopleAuditLogEntry[]>([]);

  const fetchMaintenanceAudit = useCallback(async (): Promise<PeopleAuditLogEntry[]> => {
    if (!Number.isFinite(id)) return [];
    try {
      return await listPersonWorkspaceAuditLog(id, { limit: 100 });
    } catch {
      return [];
    }
  }, [id]);

  const load = useCallback(async () => {
    if (!Number.isFinite(id)) return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const [d, audit] = await Promise.all([getPersonWorkspaceDetail(id), fetchMaintenanceAudit()]);
      setDetail(d);
      setForm(detailToForm(d));
      setDriverForm(detailToDriverForm(d));
      setAuditEntries(audit);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load person.");
      setDetail(null);
      setForm(null);
      setDriverForm(null);
      setAuditEntries([]);
    } finally {
      setLoading(false);
    }
  }, [id, fetchMaintenanceAudit]);

  useEffect(() => {
    void load();
  }, [load]);

  const onSave = async () => {
    if (!Number.isFinite(id) || !form) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const res = await patchPersonWorkspaceCore(id, {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        street_address: form.street_address.trim() || null,
        city: form.city.trim() || null,
        region: form.region.trim() || null,
        postal_code: form.postal_code.trim() || null,
        zip_code: form.zip_code.trim() || null,
        country: form.country.trim() || null,
        notes: form.notes.trim() || null,
        is_active: form.is_active,
      });
      setDetail(res.person);
      setForm(detailToForm(res.person));
      setDriverForm(detailToDriverForm(res.person));
      const syncMsg =
        res.synced_operational_driver_ids.length > 0
          ? ` Synced operational driver row(s): ${res.synced_operational_driver_ids.join(", ")}.`
          : "";
      setNotice(`Saved.${syncMsg}`);
      setAuditEntries(await fetchMaintenanceAudit());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  const onSaveDriverProfile = async () => {
    if (!Number.isFinite(id) || !driverForm || !detail) return;
    if (!hasActiveDriverRole(detail)) return;
    setSavingDriver(true);
    setError(null);
    setNotice(null);
    try {
      const res = await patchPersonDriverProfile(id, {
        license_number: driverForm.license_number.trim() || null,
        license_region: driverForm.license_region.trim() || null,
        license_expiry: driverForm.license_expiry.trim() || null,
        is_active: driverForm.is_active,
      });
      setDetail(res.person);
      setForm(detailToForm(res.person));
      setDriverForm(detailToDriverForm(res.person));
      const syncMsg =
        res.synced_operational_driver_ids.length > 0
          ? ` Synced operational driver row(s): ${res.synced_operational_driver_ids.join(", ")}.`
          : "";
      setNotice(`Driver license saved.${syncMsg}`);
      setAuditEntries(await fetchMaintenanceAudit());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setSavingDriver(false);
    }
  };

  if (!Number.isFinite(id)) {
    return (
      <div className="p-8 text-rose-300" style={{ background: C.bg, margin: -24 }}>
        Invalid person id.
      </div>
    );
  }

  if (loading || !form || !detail || !driverForm) {
    return (
      <div className="min-h-screen p-8" style={{ background: C.bg, margin: -24, color: C.muted }}>
        {error ? <div className="text-rose-300">{error}</div> : "Loading…"}
      </div>
    );
  }

  return (
    <div className="min-h-screen overflow-x-hidden pb-12 text-[var(--trk-text)]" style={{ background: C.bg, margin: -24 }}>
      <div className="relative px-8 py-8">
        <button
          type="button"
          onClick={() => navigate(OPS.PEOPLE)}
          className="mb-6 text-sm hover:underline"
          style={{ color: C.accent }}
        >
          ← Back to People
        </button>

        <div className="mb-6 flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <h1 className="font-['Barlow_Condensed',sans-serif] text-3xl font-bold" style={{ color: C.text }}>
              {[form.first_name, form.last_name].filter(Boolean).join(" ") || `Person #${id}`}
            </h1>
            <p className="mt-1 font-mono text-xs" style={{ color: C.muted }}>
              Person #{id}
              {detail.platform_user_id ? ` · platform user ${detail.platform_user_id}` : ""}
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>
        )}
        {notice && (
          <div className="mb-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
            {notice}
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <section className="rounded-2xl border p-5" style={{ borderColor: C.border, background: C.card }}>
              <h2 className="mb-4 font-semibold" style={{ color: C.text }}>
                Core contact & address
              </h2>
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField label="First name">
                  <input
                    value={form.first_name}
                    onChange={(e) => setForm((f) => (f ? { ...f, first_name: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                  />
                </FormField>
                <FormField label="Last name">
                  <input
                    value={form.last_name}
                    onChange={(e) => setForm((f) => (f ? { ...f, last_name: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                  />
                </FormField>
                <FormField label="Phone">
                  <input
                    value={form.phone}
                    onChange={(e) => setForm((f) => (f ? { ...f, phone: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                  />
                </FormField>
                <FormField label="Email">
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm((f) => (f ? { ...f, email: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                  />
                </FormField>
                <FormField label="Street">
                  <input
                    value={form.street_address}
                    onChange={(e) => setForm((f) => (f ? { ...f, street_address: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none sm:col-span-2"
                    style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                  />
                </FormField>
                <FormField label="City">
                  <input
                    value={form.city}
                    onChange={(e) => setForm((f) => (f ? { ...f, city: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                  />
                </FormField>
                <FormField label="State / province">
                  <input
                    value={form.region}
                    onChange={(e) => setForm((f) => (f ? { ...f, region: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                  />
                </FormField>
                <FormField label="Postal code">
                  <input
                    value={form.postal_code}
                    onChange={(e) => setForm((f) => (f ? { ...f, postal_code: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                  />
                </FormField>
                <FormField label="ZIP">
                  <input
                    value={form.zip_code}
                    onChange={(e) => setForm((f) => (f ? { ...f, zip_code: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                  />
                </FormField>
                <FormField label="Country">
                  <input
                    value={form.country}
                    onChange={(e) => setForm((f) => (f ? { ...f, country: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                  />
                </FormField>
              </div>
              <div className="mt-4">
                <FormField label="Notes">
                  <textarea
                    value={form.notes}
                    onChange={(e) => setForm((f) => (f ? { ...f, notes: e.target.value } : f))}
                    rows={3}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                  />
                </FormField>
              </div>
              <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm" style={{ color: C.muted }}>
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) => setForm((f) => (f ? { ...f, is_active: e.target.checked } : f))}
                  className="rounded border"
                  style={{ borderColor: C.border }}
                />
                Person is active
              </label>
              <div className="mt-6">
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void onSave()}
                  className="rounded-lg px-6 py-2.5 text-sm font-bold text-[var(--trk-bg)] disabled:opacity-50"
                  style={{ background: C.accent }}
                >
                  {saving ? "Saving…" : "Save core fields"}
                </button>
              </div>
            </section>
          </div>

          <div className="space-y-4">
            <section className="rounded-2xl border p-5" style={{ borderColor: C.border, background: C.card }}>
              <h3 className="mb-3 text-sm font-semibold" style={{ color: C.text }}>
                Roles
              </h3>
              {detail.roles.length === 0 ? (
                <p className="text-xs" style={{ color: C.muted }}>
                  No roles attached.
                </p>
              ) : (
                <ul className="space-y-2 text-xs" style={{ color: C.muted }}>
                  {detail.roles.map((r) => (
                    <li key={`${r.role_code}-${r.is_primary}`}>
                      <span className="font-mono text-[var(--trk-text)]">{r.role_code}</span>
                      {r.is_primary ? " · primary" : ""}
                      {r.is_active ? "" : " · inactive"}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="rounded-2xl border p-5" style={{ borderColor: C.border, background: C.card }}>
              <h3 className="mb-3 text-sm font-semibold" style={{ color: C.text }}>
                Driver profile (license)
              </h3>
              {!hasActiveDriverRole(detail) ? (
                <p className="text-xs" style={{ color: C.muted }}>
                  This person does not have an active DRIVER role. Activate or assign the role before editing license fields.
                </p>
              ) : (
                <>
                  {!detail.driver_profile && (
                    <p className="mb-3 text-xs" style={{ color: C.muted }}>
                      No driver profile row yet — saving will create one.
                    </p>
                  )}
                  <div className="space-y-3 text-xs">
                    <FormField label="License number">
                      <input
                        value={driverForm.license_number}
                        onChange={(e) => setDriverForm((f) => (f ? { ...f, license_number: e.target.value } : f))}
                        className="w-full rounded-lg border px-3 py-2 font-mono text-sm outline-none"
                        style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                      />
                    </FormField>
                    <FormField label="Issuing region (state/province)">
                      <input
                        value={driverForm.license_region}
                        onChange={(e) => setDriverForm((f) => (f ? { ...f, license_region: e.target.value } : f))}
                        className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                        style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                      />
                    </FormField>
                    <FormField label="Expiry">
                      <input
                        type="date"
                        value={driverForm.license_expiry}
                        onChange={(e) => setDriverForm((f) => (f ? { ...f, license_expiry: e.target.value } : f))}
                        className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                        style={{ borderColor: C.border, background: "#0d1017", color: C.text }}
                      />
                    </FormField>
                    <label className="flex cursor-pointer items-center gap-2 text-sm" style={{ color: C.muted }}>
                      <input
                        type="checkbox"
                        checked={driverForm.is_active}
                        onChange={(e) => setDriverForm((f) => (f ? { ...f, is_active: e.target.checked } : f))}
                        className="rounded border"
                        style={{ borderColor: C.border }}
                      />
                      Driver profile active
                    </label>
                  </div>
                  <div className="mt-4">
                    <button
                      type="button"
                      disabled={savingDriver}
                      onClick={() => void onSaveDriverProfile()}
                      className="rounded-lg px-5 py-2 text-sm font-bold text-[var(--trk-bg)] disabled:opacity-50"
                      style={{ background: C.accent }}
                    >
                      {savingDriver ? "Saving…" : "Save license"}
                    </button>
                  </div>
                  <p className="mt-3 text-[11px] leading-relaxed" style={{ color: "#64748b" }}>
                    Updates the canonical <span className="font-mono">driver_profiles</span> row and copies license fields onto active operational{" "}
                    <span className="font-mono">drivers</span> rows for this person.
                  </p>
                </>
              )}
            </section>

            <section className="rounded-2xl border p-5" style={{ borderColor: C.border, background: C.card }}>
              <h3 className="mb-3 text-sm font-semibold" style={{ color: C.text }}>
                Role-attached configuration (driver)
              </h3>
              <p className="mb-3 text-xs leading-relaxed" style={{ color: C.muted }}>
                Classification and equipment rules for the <strong className="font-normal">driver</strong> role live on{" "}
                <span className="font-mono">driver_person_extensions</span> — not on <span className="font-mono">people</span>. Edit here
                as the maintained path; onboarding is workflow only.
              </p>
              {!hasActiveDriverRole(detail) ? (
                <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-100/90">
                  <strong className="font-semibold">Editing blocked:</strong> this person needs an <strong>active</strong> DRIVER role before
                  role-attached configuration can be saved. Assign the role, then return here — first save will create the extension row if
                  none exists.
                </div>
              ) : (
                <DriverPersonExtensionAdminPanel
                  key={`people-dpe-${id}`}
                  mode="people"
                  personId={id}
                  editable
                  onAfterPersist={() => void load()}
                />
              )}
            </section>

            <section className="rounded-2xl border p-5" style={{ borderColor: C.border, background: C.card }}>
              <h3 className="mb-3 text-sm font-semibold" style={{ color: C.text }}>
                Operational driver
              </h3>
              {detail.operational_drivers.length === 0 ? (
                <p className="text-xs" style={{ color: C.muted }}>
                  No dispatch roster row for this person.
                </p>
              ) : (
                <ul className="space-y-2 text-xs" style={{ color: C.muted }}>
                  {detail.operational_drivers.map((d) => (
                    <li key={d.driver_id} className="font-mono">
                      Driver #{d.driver_id}
                      {d.is_active ? "" : " (inactive)"}
                      {d.payee_id != null ? ` · payee #${d.payee_id}` : ""}
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-3 text-[11px]" style={{ color: "#64748b" }}>
                Name/phone/email on roster rows update when you save core fields here (canonical <span className="font-mono">people</span>).
              </p>
            </section>

            <section className="rounded-2xl border p-5" style={{ borderColor: C.border, background: C.card }}>
              <h3 className="mb-3 text-sm font-semibold" style={{ color: C.text }}>
                Compensation
              </h3>
              <p className="mb-3 text-xs leading-relaxed" style={{ color: C.muted }}>
                Pay model and rates are stored on the tenant <span className="font-mono">payees</span> and{" "}
                <span className="font-mono">compensation_profiles</span> linked from the active operational driver row — not on{" "}
                <span className="font-mono">people</span>.
              </p>
              {!hasActiveOperationalDriver(detail) ? (
                <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-100/90">
                  <strong className="font-semibold">Editing blocked:</strong> this person has no <strong>active</strong> operational{" "}
                  <span className="font-mono">drivers</span> row. Create or activate a roster driver linked to this person (and ensure{" "}
                  <span className="font-mono">drivers.payee_id</span> is set, or save driver classification first so a payee can be
                  bootstrapped) before correcting compensation here.
                </div>
              ) : (
                <>
                  <div className="mb-3 text-[11px] leading-relaxed" style={{ color: "#64748b" }}>
                    If <span className="font-mono">payee_id</span> is empty on the roster row, saving below requires a{" "}
                    <span className="font-mono">driver_person_extensions</span> row (driver classification) so worker type is known when
                    creating the payee.
                  </div>
                  <DriverCompensationSetupAdminPanel
                    key={`people-comp-${id}`}
                    mode="person"
                    personId={id}
                    editable
                    onAfterPersist={() => void load()}
                  />
                </>
              )}
              {detail.latest_application && (
                <Link
                  className="mt-4 inline-block text-xs font-medium hover:underline"
                  style={{ color: C.accent }}
                  to={OPS.DRIVER_ONBOARDING_REVIEW_DETAIL(detail.latest_application.id)}
                >
                  Open linked onboarding application (workflow history) →
                </Link>
              )}
            </section>

            <section className="rounded-2xl border p-5" style={{ borderColor: C.border, background: C.card }}>
              <h3 className="mb-2 text-sm font-semibold" style={{ color: C.text }}>
                Correction history
              </h3>
              <p className="mb-3 text-xs leading-relaxed" style={{ color: C.muted }}>
                Changes made from this People workspace (core, profile, compensation, and role-attached configuration). Workflow-only
                onboarding edits are not listed here unless they used the same audit actions.
              </p>
              {auditEntries.length === 0 ? (
                <p className="text-xs" style={{ color: C.muted }}>
                  {loading ? "Loading…" : "No recorded maintenance changes yet."}
                </p>
              ) : (
                <div className="max-h-[480px] space-y-3 overflow-y-auto pr-1">
                  {auditEntries.map((a) => (
                    <div
                      key={a.id}
                      className="rounded-lg border p-3 text-xs"
                      style={{ borderColor: C.border, background: "#0d1017" }}
                    >
                      <div className="font-semibold" style={{ color: C.text }}>
                        {peopleMaintenanceAuditActionLabel(a.action)}
                      </div>
                      <div className="mt-0.5" style={{ color: C.muted }}>
                        {new Date(a.created_at).toLocaleString()}
                      </div>
                      <div className="mt-0.5" style={{ color: C.muted }}>
                        Actor:{" "}
                        {a.actor_email?.trim()
                          ? a.actor_email
                          : a.actor_user_id != null
                            ? `Platform member #${a.actor_user_id}`
                            : "—"}
                      </div>
                      {a.changed_keys.length > 0 && (
                        <div className="mt-2 text-[11px]" style={{ color: "#64748b" }}>
                          Fields: <span className="font-mono text-[var(--trk-text-muted)]">{a.changed_keys.join(", ")}</span>
                        </div>
                      )}
                      {Object.keys(a.snapshot).length > 0 && (
                        <div className="mt-2 space-y-1 border-t pt-2" style={{ borderColor: C.border }}>
                          {Object.entries(a.snapshot).map(([field, raw]) => {
                            const delta = raw as { before?: unknown; after?: unknown };
                            return (
                              <div key={field} className="font-mono text-[11px] leading-snug" style={{ color: C.muted }}>
                                <span style={{ color: C.text }}>{field}</span>: {formatAuditValue(delta.before)} →{" "}
                                {formatAuditValue(delta.after)}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function PeopleWorkspacePage() {
  return (
    <Routes>
      <Route index element={<PeopleListView />} />
      <Route path=":personId" element={<PersonDetailView />} />
    </Routes>
  );
}
