import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
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

function peopleListOnboardingStatusStyle(status: string): { border: string; color: string } | undefined {
  const u = status.trim().toUpperCase();
  if (u === "REJECTED") return { border: "rgba(244, 63, 94, 0.35)", color: "#fda4af" };
  if (u === "APPROVED") return { border: "rgba(34, 197, 94, 0.35)", color: "#86efac" };
  if (u === "SUBMITTED") return { border: "rgba(245, 158, 11, 0.35)", color: "#fcd34d" };
  if (u === "DRAFT") return { border: `${C.border}`, color: C.muted };
  return undefined;
}

function PeopleListOnboardingStatusCell({ p }: { p: PeopleListItem }) {
  const la = p.latest_application;
  if (!la) {
    return <span className="text-[11px] text-[var(--trk-text-muted)]">No application</span>;
  }
  const st = la.status || "—";
  const accent = peopleListOnboardingStatusStyle(st);
  return (
    <div className="max-w-[200px] space-y-1">
      <span
        className="inline-block rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide"
        style={{
          border: `1px solid ${accent?.border ?? C.border}`,
          color: accent?.color ?? C.text,
          background: accent ? `${accent.color}12` : "transparent",
        }}
      >
        {st}
      </span>
      <div className="font-mono text-[10px] leading-tight text-[var(--trk-text-muted)]">
        {la.current_workflow_lane ? <span className="block">Lane: {la.current_workflow_lane}</span> : null}
        {la.setup_status ? <span className="block">Setup: {la.setup_status}</span> : null}
      </div>
    </div>
  );
}

function PeopleListActiveRolesCell({ p }: { p: PeopleListItem }) {
  const codes = p.active_role_codes ?? [];
  const primary = p.primary_role_code ?? null;
  if (codes.length === 0) {
    return <span className="text-[11px] text-[var(--trk-text-muted)]">No active role</span>;
  }
  return (
    <div className="flex max-w-[220px] flex-wrap gap-1">
      {codes.map((code) => {
        const isPrimary = primary != null && primary !== "" && code === primary;
        return (
          <span
            key={code}
            className="rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide"
            style={{
              border: `1px solid ${isPrimary ? C.accent : C.border}`,
              color: isPrimary ? C.accent : C.muted,
              background: isPrimary ? `${C.accent}14` : "transparent",
            }}
            title={isPrimary ? "Primary role (active)" : undefined}
          >
            {code}
          </span>
        );
      })}
    </div>
  );
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

/** Client-only list filter sentinel (not a real role code). */
const PEOPLE_LIST_ROLE_FILTER_NONE = "__none_active__";
const PEOPLE_LIST_ROLE_FILTER_ALL = "";

/** Client-only: no linked latest application on list payload. */
const PEOPLE_LIST_ONBOARDING_FILTER_NONE = "__no_application__";
const PEOPLE_LIST_ONBOARDING_FILTER_ALL = "";

function PeopleListView() {
  const [items, setItems] = useState<PeopleListItem[]>([]);
  const [q, setQ] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>(PEOPLE_LIST_ROLE_FILTER_ALL);
  const [onboardingFilter, setOnboardingFilter] = useState<string>(PEOPLE_LIST_ONBOARDING_FILTER_ALL);
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

  const discoveredRoleCodes = useMemo(() => {
    const s = new Set<string>();
    for (const p of items) {
      for (const c of p.active_role_codes ?? []) {
        const t = (c || "").trim();
        if (t) s.add(t);
      }
    }
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [items]);

  const hasAnyoneWithoutActiveRole = useMemo(
    () => items.some((p) => !(p.active_role_codes && p.active_role_codes.length > 0)),
    [items]
  );

  const discoveredApplicationStatuses = useMemo(() => {
    const s = new Set<string>();
    for (const p of items) {
      const st = p.latest_application?.status;
      const t = (st || "").trim();
      if (t) s.add(t);
    }
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [items]);

  const hasAnyoneWithoutApplication = useMemo(() => items.some((p) => !p.latest_application), [items]);

  useEffect(() => {
    if (roleFilter === PEOPLE_LIST_ROLE_FILTER_ALL || roleFilter === PEOPLE_LIST_ROLE_FILTER_NONE) return;
    if (!discoveredRoleCodes.includes(roleFilter)) {
      setRoleFilter(PEOPLE_LIST_ROLE_FILTER_ALL);
    }
  }, [discoveredRoleCodes, roleFilter]);

  useEffect(() => {
    if (roleFilter === PEOPLE_LIST_ROLE_FILTER_NONE && !hasAnyoneWithoutActiveRole) {
      setRoleFilter(PEOPLE_LIST_ROLE_FILTER_ALL);
    }
  }, [hasAnyoneWithoutActiveRole, roleFilter]);

  useEffect(() => {
    if (
      onboardingFilter !== PEOPLE_LIST_ONBOARDING_FILTER_ALL &&
      onboardingFilter !== PEOPLE_LIST_ONBOARDING_FILTER_NONE &&
      !discoveredApplicationStatuses.includes(onboardingFilter)
    ) {
      setOnboardingFilter(PEOPLE_LIST_ONBOARDING_FILTER_ALL);
    }
  }, [discoveredApplicationStatuses, onboardingFilter]);

  useEffect(() => {
    if (onboardingFilter === PEOPLE_LIST_ONBOARDING_FILTER_NONE && !hasAnyoneWithoutApplication) {
      setOnboardingFilter(PEOPLE_LIST_ONBOARDING_FILTER_ALL);
    }
  }, [hasAnyoneWithoutApplication, onboardingFilter]);

  const roleFilteredItems = useMemo(() => {
    if (roleFilter === PEOPLE_LIST_ROLE_FILTER_ALL) return items;
    if (roleFilter === PEOPLE_LIST_ROLE_FILTER_NONE) {
      return items.filter((p) => !(p.active_role_codes && p.active_role_codes.length > 0));
    }
    return items.filter((p) => (p.active_role_codes ?? []).includes(roleFilter));
  }, [items, roleFilter]);

  const filteredItems = useMemo(() => {
    if (onboardingFilter === PEOPLE_LIST_ONBOARDING_FILTER_ALL) return roleFilteredItems;
    if (onboardingFilter === PEOPLE_LIST_ONBOARDING_FILTER_NONE) {
      return roleFilteredItems.filter((p) => !p.latest_application);
    }
    return roleFilteredItems.filter((p) => p.latest_application?.status === onboardingFilter);
  }, [roleFilteredItems, onboardingFilter]);

  const emptyMessage = useMemo(() => {
    if (loading) return "";
    if (items.length === 0) return "No people match your search.";
    if (filteredItems.length === 0) return "No people match the selected filters.";
    return "";
  }, [loading, items.length, filteredItems.length]);

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

        <div className="mb-6 flex flex-wrap items-end gap-3">
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
          <label className="flex shrink-0 flex-col gap-1">
            <span className="font-mono text-[10px] uppercase tracking-wide" style={{ color: C.muted }}>
              Role
            </span>
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              disabled={loading}
              className="min-w-[10rem] max-w-[14rem] cursor-pointer rounded-lg border px-3 py-2 text-xs outline-none disabled:cursor-not-allowed disabled:opacity-50"
              style={{ borderColor: C.border, background: C.card, color: C.text }}
              aria-label="Filter people by active role"
            >
              <option value={PEOPLE_LIST_ROLE_FILTER_ALL}>All roles</option>
              {hasAnyoneWithoutActiveRole ? (
                <option value={PEOPLE_LIST_ROLE_FILTER_NONE}>No active role</option>
              ) : null}
              {discoveredRoleCodes.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </label>
          <label className="flex shrink-0 flex-col gap-1">
            <span className="font-mono text-[10px] uppercase tracking-wide" style={{ color: C.muted }}>
              Onboarding
            </span>
            <select
              value={onboardingFilter}
              onChange={(e) => setOnboardingFilter(e.target.value)}
              disabled={loading}
              className="min-w-[9rem] max-w-[12rem] cursor-pointer rounded-lg border px-3 py-2 text-xs outline-none disabled:cursor-not-allowed disabled:opacity-50"
              style={{ borderColor: C.border, background: C.card, color: C.text }}
              aria-label="Filter people by latest application status"
            >
              <option value={PEOPLE_LIST_ONBOARDING_FILTER_ALL}>All statuses</option>
              {hasAnyoneWithoutApplication ? (
                <option value={PEOPLE_LIST_ONBOARDING_FILTER_NONE}>No application</option>
              ) : null}
              {discoveredApplicationStatuses.map((st) => (
                <option key={st} value={st}>
                  {st}
                </option>
              ))}
            </select>
          </label>
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
                  Roles
                </th>
                <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-wider" style={{ color: C.muted }}>
                  Onboarding
                </th>
                <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-wider" style={{ color: C.muted }}>
                  Active
                </th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center" style={{ color: C.muted }}>
                    Loading…
                  </td>
                </tr>
              )}
              {!loading &&
                filteredItems.map((p) => (
                  <tr key={p.id} className="border-b transition hover:bg-[var(--trk-surface)]" style={{ borderColor: C.border }}>
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
                    <td className="px-4 py-3 align-top">
                      <PeopleListActiveRolesCell p={p} />
                    </td>
                    <td className="px-4 py-3 align-top">
                      <PeopleListOnboardingStatusCell p={p} />
                    </td>
                    <td className="px-4 py-3 text-xs">{p.is_active ? "Yes" : "No"}</td>
                  </tr>
                ))}
              {!loading && emptyMessage && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center" style={{ color: C.muted }}>
                    {emptyMessage}
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

function formatRoleAttachedAt(iso: string | null | undefined): string {
  if (iso == null || iso === "") return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function compensationHasPayeeLink(c: PeopleDetail["compensation"]): boolean {
  return c.payee_id != null && c.payee_id !== undefined;
}

function PeopleRolesReadOnlySection({ detail }: { detail: PeopleDetail }) {
  const activeRoles = detail.roles.filter((r) => r.is_active);
  const inactiveRoles = detail.roles.filter((r) => !r.is_active);

  const badgeCls =
    "inline-block rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-[var(--trk-text-muted)]";
  const badgeWrap = "mt-2 flex flex-wrap gap-1";

  const renderRoleRow = (r: (typeof detail.roles)[number]) => {
    const isDriver = r.role_code.trim().toUpperCase() === "DRIVER";
    return (
      <li
        key={r.id}
        className="rounded-lg border px-3 py-2.5"
        style={{ borderColor: C.border, background: "var(--trk-bg)" }}
      >
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="font-mono text-sm" style={{ color: C.text }}>
            {r.role_code}
          </span>
          {r.is_primary ? (
            <span
              className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
              style={{ background: `${C.accent}22`, color: C.accent }}
            >
              Primary
            </span>
          ) : null}
        </div>
        <div className="mt-1 text-[11px]" style={{ color: C.muted }}>
          Attached {formatRoleAttachedAt(r.created_at)}
        </div>
        {isDriver ? (
          <div className={badgeWrap}>
            {detail.driver_profile ? (
              <span className={badgeCls} style={{ border: `1px solid ${C.border}` }}>
                Driver profile
              </span>
            ) : null}
            {detail.driver_person_extension ? (
              <span className={badgeCls} style={{ border: `1px solid ${C.border}` }}>
                Role config (driver)
              </span>
            ) : null}
            {detail.operational_drivers.length > 0 ? (
              <span className={badgeCls} style={{ border: `1px solid ${C.border}` }}>
                Operational roster ({detail.operational_drivers.length})
              </span>
            ) : null}
            {compensationHasPayeeLink(detail.compensation) ? (
              <span className={badgeCls} style={{ border: `1px solid ${C.border}` }}>
                Compensation payee
              </span>
            ) : null}
          </div>
        ) : (
          <p className="mt-2 text-[11px] leading-snug" style={{ color: C.muted }}>
            No dedicated People maintenance surface exists for this role yet.
          </p>
        )}
      </li>
    );
  };

  if (detail.roles.length === 0) {
    return (
      <section className="rounded-2xl border p-5" style={{ borderColor: C.border, background: C.card }}>
        <h3 className="mb-3 text-sm font-semibold" style={{ color: C.text }}>
          Roles
        </h3>
        <p className="text-xs" style={{ color: C.muted }}>
          No roles attached.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border p-5" style={{ borderColor: C.border, background: C.card }}>
      <h3 className="mb-3 text-sm font-semibold" style={{ color: C.text }}>
        Roles
      </h3>
      <p className="mb-4 text-[11px] leading-relaxed" style={{ color: C.muted }}>
        Read-only view of roles on this person. Role changes continue through onboarding and provisioning flows.
      </p>
      <div className="space-y-5">
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: C.muted }}>
            Active roles
          </h4>
          {activeRoles.length === 0 ? (
            <p className="text-xs" style={{ color: C.muted }}>
              None.
            </p>
          ) : (
            <ul className="space-y-2 text-xs">{activeRoles.map(renderRoleRow)}</ul>
          )}
        </div>
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: C.muted }}>
            Inactive roles
          </h4>
          {inactiveRoles.length === 0 ? (
            <p className="text-xs" style={{ color: C.muted }}>
              None.
            </p>
          ) : (
            <ul className="space-y-2 text-xs">{inactiveRoles.map(renderRoleRow)}</ul>
          )}
        </div>
      </div>
    </section>
  );
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
                    style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
                  />
                </FormField>
                <FormField label="Last name">
                  <input
                    value={form.last_name}
                    onChange={(e) => setForm((f) => (f ? { ...f, last_name: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
                  />
                </FormField>
                <FormField label="Phone">
                  <input
                    value={form.phone}
                    onChange={(e) => setForm((f) => (f ? { ...f, phone: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
                  />
                </FormField>
                <FormField label="Email">
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm((f) => (f ? { ...f, email: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
                  />
                </FormField>
                <FormField label="Street">
                  <input
                    value={form.street_address}
                    onChange={(e) => setForm((f) => (f ? { ...f, street_address: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none sm:col-span-2"
                    style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
                  />
                </FormField>
                <FormField label="City">
                  <input
                    value={form.city}
                    onChange={(e) => setForm((f) => (f ? { ...f, city: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
                  />
                </FormField>
                <FormField label="State / province">
                  <input
                    value={form.region}
                    onChange={(e) => setForm((f) => (f ? { ...f, region: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
                  />
                </FormField>
                <FormField label="Postal code">
                  <input
                    value={form.postal_code}
                    onChange={(e) => setForm((f) => (f ? { ...f, postal_code: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
                  />
                </FormField>
                <FormField label="ZIP">
                  <input
                    value={form.zip_code}
                    onChange={(e) => setForm((f) => (f ? { ...f, zip_code: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
                  />
                </FormField>
                <FormField label="Country">
                  <input
                    value={form.country}
                    onChange={(e) => setForm((f) => (f ? { ...f, country: e.target.value } : f))}
                    className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
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
                    style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
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
            <PeopleRolesReadOnlySection detail={detail} />

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
                        style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
                      />
                    </FormField>
                    <FormField label="Issuing region (state/province)">
                      <input
                        value={driverForm.license_region}
                        onChange={(e) => setDriverForm((f) => (f ? { ...f, license_region: e.target.value } : f))}
                        className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                        style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
                      />
                    </FormField>
                    <FormField label="Expiry">
                      <input
                        type="date"
                        value={driverForm.license_expiry}
                        onChange={(e) => setDriverForm((f) => (f ? { ...f, license_expiry: e.target.value } : f))}
                        className="w-full rounded-lg border px-3 py-2 text-sm outline-none"
                        style={{ borderColor: C.border, background: "var(--trk-bg)", color: C.text }}
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
                  <p className="mt-3 text-[11px] leading-relaxed" style={{ color: "var(--trk-text-muted)" }}>
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
              <p className="mt-3 text-[11px]" style={{ color: "var(--trk-text-muted)" }}>
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
                  <div className="mb-3 text-[11px] leading-relaxed" style={{ color: "var(--trk-text-muted)" }}>
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
                      style={{ borderColor: C.border, background: "var(--trk-bg)" }}
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
                        <div className="mt-2 text-[11px]" style={{ color: "var(--trk-text-muted)" }}>
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
