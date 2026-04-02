import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  listPersonApplicationsForAdmin,
  createOnboardingInviteLink,
  PersonApplicationListItem,
} from "../api";

type StatusFilter = "ALL" | "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED";
type SortMode = "created_desc" | "submitted_desc" | "name_asc";

const STATUS_ORDER: StatusFilter[] = ["ALL", "DRAFT", "SUBMITTED", "APPROVED", "REJECTED"];

const APPLICATION_TYPES = [
  "DRIVER",
  "DISPATCHER",
  "HR",
  "MECHANIC",
  "PAYROLL",
  "SAFETY",
  "OFFICE_ADMIN",
  "OTHER",
] as const;

function formatIsoDay(value?: string | null) {
  if (!value) return "—";
  return value.slice(0, 10);
}

function formatRelative(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const diffMs = Date.now() - date.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays <= 0) {
    const diffHours = Math.max(1, Math.floor(diffMs / 3600000));
    return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;
  }
  return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
}

function displayName(item: PersonApplicationListItem) {
  const name = [item.first_name, item.last_name].filter(Boolean).join(" ").trim();
  return name || `Application #${item.id}`;
}

function secondaryLine(item: PersonApplicationListItem) {
  return item.email || item.phone || "Invite not yet claimed";
}

function initials(item: PersonApplicationListItem) {
  const parts = [item.first_name, item.last_name].filter(Boolean).map((part) => String(part).trim()).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("");
}

function statusBadgeClass(status: string) {
  switch (status) {
    case "SUBMITTED":
      return "bg-blue-500/10 text-blue-300 border border-blue-400/20";
    case "APPROVED":
      return "bg-emerald-500/10 text-emerald-300 border border-emerald-400/20";
    case "REJECTED":
      return "bg-rose-500/10 text-rose-300 border border-rose-400/20";
    default:
      return "bg-slate-500/10 text-slate-400 border border-slate-400/15";
  }
}

export default function DriverOnboardingAdminListPage() {
  const [items, setItems] = useState<PersonApplicationListItem[]>([]);
  const [status, setStatus] = useState<StatusFilter>("ALL");
  const [query, setQuery] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("created_desc");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [inviteApplicationType, setInviteApplicationType] = useState<string>("DRIVER");
  const [inviteEmail, setInviteEmail] = useState("");
  const [invitePhone, setInvitePhone] = useState("");
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [inviteEmailSent, setInviteEmailSent] = useState(false);
  const [inviteEmailError, setInviteEmailError] = useState<string | null>(null);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);

  const openInviteModal = () => {
    setInviteModalOpen(true);
    setInviteLink(null);
    setInviteEmailSent(false);
    setInviteEmailError(null);
    setInviteError(null);
    setInviteApplicationType("DRIVER");
    setInviteEmail("");
    setInvitePhone("");
  };

  const closeInviteModal = () => {
    setInviteModalOpen(false);
    setInviteLink(null);
    setInviteError(null);
  };

  const handleGenerateLink = async () => {
    const email = inviteEmail.trim() || null;
    const phone = invitePhone.trim() || null;
    if (!email && !phone) {
      setInviteError("Enter an email or phone number to send the link to.");
      return;
    }
    if (!inviteApplicationType || !APPLICATION_TYPES.includes(inviteApplicationType as (typeof APPLICATION_TYPES)[number])) {
      setInviteError("Select an application type.");
      return;
    }
    setInviteLoading(true);
    setInviteError(null);
    setInviteEmailError(null);
    setInviteLink(null);
    try {
      const res = await createOnboardingInviteLink({ email, phone, application_type: inviteApplicationType });
      setInviteLink(res.link);
      setInviteEmailSent(res.email_sent);
      if (res.email_error) setInviteEmailError(res.email_error);
    } catch (err: any) {
      setInviteError(err?.message || "Failed to generate link.");
    } finally {
      setInviteLoading(false);
    }
  };

  const copyLink = () => {
    if (inviteLink) {
      navigator.clipboard.writeText(inviteLink);
    }
  };

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await listPersonApplicationsForAdmin({
          limit: 200,
          offset: 0,
        });
        setItems(data);
      } catch (err: any) {
        setError(err?.message || "Unable to load submissions.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const counts = useMemo(() => ({
    ALL: items.length,
    DRAFT: items.filter((item) => item.status === "DRAFT").length,
    SUBMITTED: items.filter((item) => item.status === "SUBMITTED").length,
    APPROVED: items.filter((item) => item.status === "APPROVED").length,
    REJECTED: items.filter((item) => item.status === "REJECTED").length,
  }), [items]);

  const filteredItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    let next = [...items];

    if (status !== "ALL") {
      next = next.filter((item) => item.status === status);
    }

    if (normalizedQuery) {
      next = next.filter((item) => {
        const haystack = [
          item.id,
          item.first_name,
          item.last_name,
          item.email,
          item.phone,
          item.source,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(normalizedQuery);
      });
    }

    next.sort((a, b) => {
      if (sortMode === "name_asc") {
        return displayName(a).localeCompare(displayName(b));
      }
      if (sortMode === "submitted_desc") {
        return new Date(b.submitted_at || 0).getTime() - new Date(a.submitted_at || 0).getTime();
      }
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });

    return next;
  }, [items, query, sortMode, status]);

  const allVisibleSelected = filteredItems.length > 0 && filteredItems.every((item) => selectedIds.includes(item.id));
  const hasFilters = status !== "ALL" || query.trim().length > 0;

  const toggleSelectAll = () => {
    if (allVisibleSelected) {
      setSelectedIds((prev) => prev.filter((id) => !filteredItems.some((item) => item.id === id)));
      return;
    }
    setSelectedIds((prev) => Array.from(new Set([...prev, ...filteredItems.map((item) => item.id)])));
  };

  const toggleSelected = (id: number) => {
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((current) => current !== id) : [...prev, id]);
  };

  const cycleSort = () => {
    setSortMode((prev) => {
      if (prev === "created_desc") return "submitted_desc";
      if (prev === "submitted_desc") return "name_asc";
      return "created_desc";
    });
  };

  const resetFilters = () => {
    setStatus("ALL");
    setQuery("");
  };

  const sortLabel =
    sortMode === "created_desc" ? "Created" :
    sortMode === "submitted_desc" ? "Submitted" :
    "Name";

  return (
    <div className="-m-6 min-h-screen overflow-x-hidden bg-[#080a0f] text-[#e8edf5]">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');
      `}</style>
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_70%_-10%,rgba(245,166,35,0.05)_0%,transparent_60%),radial-gradient(ellipse_40%_30%_at_5%_80%,rgba(59,130,246,0.05)_0%,transparent_50%),repeating-linear-gradient(0deg,transparent,transparent_39px,rgba(255,255,255,0.02)_39px,rgba(255,255,255,0.02)_40px),repeating-linear-gradient(90deg,transparent,transparent_79px,rgba(255,255,255,0.015)_79px,rgba(255,255,255,0.015)_80px)]" />
      <div className="relative px-10 py-9">
        <div className="mb-9 flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="mb-2 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-[#f5a623] before:inline-block before:h-px before:w-5 before:bg-[#f5a623] before:content-['']">
              Driver Onboarding
            </div>
            <h2 className="font-['Barlow_Condensed'] text-5xl font-extrabold leading-none tracking-tight text-[#e8edf5]">
              Applications
            </h2>
            <p className="mt-2 text-sm text-[#7c8ba1]">
              Review invite-link onboarding submissions from the new applicant portal.
            </p>
          </div>
          <button
            type="button"
            onClick={openInviteModal}
            className="inline-flex items-center gap-2 rounded-lg bg-[#f5a623] px-5 py-2.5 text-sm font-bold text-[#080a0f] shadow-[0_2px_16px_rgba(245,166,35,0.2)] transition hover:opacity-90"
          >
            <span className="text-base leading-none">+</span>
            Generate Link
          </button>
        </div>

        <div className="mb-8 grid grid-cols-1 gap-3 md:grid-cols-5">
          {STATUS_ORDER.map((key) => {
            const accent =
              key === "ALL" ? "#94a3b8" :
              key === "DRAFT" ? "#94a3b8" :
              key === "SUBMITTED" ? "#3b82f6" :
              key === "APPROVED" ? "#22d3a0" :
              "#f43f5e";
            const active = status === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setStatus(key)}
                className={`relative overflow-hidden rounded-xl border px-5 py-4 text-left transition ${active ? "bg-[#161b27]" : "bg-[#111520] hover:bg-[#161b27]"} ${active ? "border-white/20" : "border-[#1c2235]"}`}
                style={{ boxShadow: active ? `inset 0 0 0 1px ${accent}40` : undefined }}
              >
                <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7c8ba1]">
                  {key === "ALL" ? "All" : key.charAt(0) + key.slice(1).toLowerCase()}
                </div>
                <div className="font-['Barlow_Condensed'] text-4xl font-extrabold leading-none" style={{ color: active ? accent : "#e8edf5" }}>
                  {counts[key]}
                </div>
                <span className="absolute inset-x-0 bottom-0 h-0.5" style={{ background: accent, opacity: active ? 1 : 0.35 }} />
              </button>
            );
          })}
        </div>

        <div className="mb-5 flex flex-wrap items-center gap-3">
          <div className="relative min-w-[240px] flex-1 max-w-[360px]">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-[#475569]">🔍</span>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search applicants..."
              className="w-full rounded-lg border border-[#1c2235] bg-[#111520] py-2.5 pl-9 pr-3 text-sm text-[#e8edf5] outline-none transition placeholder:text-[#475569] focus:border-[#242840]"
            />
          </div>
          <button
            type="button"
            onClick={cycleSort}
            className="inline-flex items-center gap-2 rounded-lg border border-[#1c2235] bg-[#111520] px-4 py-2.5 text-sm font-medium text-[#94a3b8] transition hover:border-[#242840] hover:text-[#e8edf5]"
          >
            ⇅ Sort: {sortLabel}
          </button>
          <button
            type="button"
            onClick={resetFilters}
            className="inline-flex items-center gap-2 rounded-lg border border-[#1c2235] bg-[#111520] px-4 py-2.5 text-sm font-medium text-[#94a3b8] transition hover:border-[#242840] hover:text-[#e8edf5]"
          >
            ⊟ {hasFilters ? "Reset" : "Filter"}
          </button>
        </div>

        {inviteModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
            <div className="w-full max-w-md rounded-2xl border border-[#242840] bg-[#111520] shadow-2xl">
              <div className="border-b border-[#1c2235] px-5 py-4">
                <h3 className="font-['Barlow_Condensed'] text-2xl font-bold tracking-wide text-[#e8edf5]">Generate invite link</h3>
                <p className="text-sm text-[#7c8ba1]">Enter email or phone to send the link to.</p>
              </div>
              <div className="space-y-4 px-5 py-5">
              <div>
                <label className="mb-1 block text-sm font-medium text-[#cbd5e1]">Application type (required)</label>
                <select
                  value={inviteApplicationType}
                  onChange={(e) => setInviteApplicationType(e.target.value)}
                  className="w-full rounded-lg border border-[#1c2235] bg-[#0d1017] px-3 py-2.5 text-sm text-[#e8edf5] outline-none"
                  disabled={!!inviteLink}
                >
                  {APPLICATION_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-[#cbd5e1]">Email</label>
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="applicant@example.com"
                  className="w-full rounded-lg border border-[#1c2235] bg-[#0d1017] px-3 py-2.5 text-sm text-[#e8edf5] outline-none placeholder:text-[#475569]"
                  disabled={!!inviteLink}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-[#cbd5e1]">Phone (optional)</label>
                <input
                  type="tel"
                  value={invitePhone}
                  onChange={(e) => setInvitePhone(e.target.value)}
                  placeholder="+1 234 567 8900"
                  className="w-full rounded-lg border border-[#1c2235] bg-[#0d1017] px-3 py-2.5 text-sm text-[#e8edf5] outline-none placeholder:text-[#475569]"
                  disabled={!!inviteLink}
                />
              </div>
              {inviteError && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
                  {inviteError}
                </div>
              )}
              {inviteLink && (
                <div className="space-y-2 rounded-lg border border-[#242840] bg-[#0d1017] p-3 text-sm">
                  {inviteEmailSent ? (
                    <p className="text-emerald-300">Link created and sent to {inviteEmail}. Check spam if you don’t see it.</p>
                  ) : (
                    <>
                      <p className="text-amber-300">Link created. Email could not be sent; copy the link below to share.</p>
                      {inviteEmailError && (
                        <p className="mt-1 text-xs text-amber-200">{inviteEmailError}</p>
                      )}
                    </>
                  )}
                  <span className="font-medium text-[#cbd5e1]">Invite link</span>
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="flex-1 truncate rounded bg-[#161b27] px-2 py-1 text-[#e8edf5]">{inviteLink}</code>
                    <button
                      type="button"
                      onClick={copyLink}
                      className="rounded border border-[#242840] bg-[#161b27] px-3 py-1 text-[#cbd5e1] hover:bg-[#1c2235]"
                    >
                      Copy
                    </button>
                  </div>
                </div>
              )}
              </div>
              <div className="flex justify-end gap-2 border-t border-[#1c2235] px-5 py-4">
                {inviteLink ? (
                  <button
                    type="button"
                    onClick={closeInviteModal}
                    className="rounded-lg bg-[#f5a623] px-4 py-2 text-sm font-bold text-[#080a0f] hover:opacity-90"
                  >
                    Done
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={closeInviteModal}
                      className="rounded-lg border border-[#242840] bg-transparent px-4 py-2 text-sm font-medium text-[#94a3b8] hover:text-[#e8edf5]"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleGenerateLink}
                      disabled={inviteLoading}
                      className="rounded-lg bg-[#f5a623] px-4 py-2 text-sm font-bold text-[#080a0f] hover:opacity-90 disabled:opacity-50"
                    >
                      {inviteLoading ? "Generating…" : "Generate link"}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-5 rounded-xl border border-rose-500/25 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            {error}
          </div>
        )}

        <div className="overflow-hidden rounded-2xl border border-[#1c2235] bg-[#111520]">
          <div className="flex items-center gap-3 border-b border-[#1c2235] px-5 py-4">
            <input
              type="checkbox"
              checked={allVisibleSelected}
              onChange={toggleSelectAll}
              className="h-4 w-4 cursor-pointer rounded border border-[#242840] bg-[#0d1017] accent-[#f5a623]"
            />
            <span className="font-mono text-xs text-[#475569]">
              <span className="font-medium text-[#f5a623]">{filteredItems.length}</span> applications
            </span>
            {selectedIds.length > 0 && (
              <span className="ml-auto font-mono text-[11px] text-[#7c8ba1]">{selectedIds.length} selected</span>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse">
              <thead>
                <tr className="border-b border-[#1c2235]">
                  <th className="w-10 px-5 py-3 text-left font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-[#475569]"></th>
                  <th className="px-4 py-3 text-left font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-[#f5a623]">Name</th>
                  <th className="px-4 py-3 text-left font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-[#475569]">Type</th>
                  <th className="px-4 py-3 text-left font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-[#475569]">Status</th>
                  <th className="px-4 py-3 text-left font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-[#475569]">Created</th>
                  <th className="px-4 py-3 text-left font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-[#475569]">Submitted</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((item, index) => {
                  const nameMissing = !item.first_name && !item.last_name;
                  return (
                    <tr
                      key={item.id}
                      className="border-b border-[#1c2235] transition hover:bg-[#161b27]"
                      style={{ animation: `rowIn 0.25s ease ${Math.min(index, 6) * 0.04}s both` }}
                    >
                      <td className="px-5 py-4">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(item.id)}
                          onChange={() => toggleSelected(item.id)}
                          className="h-4 w-4 cursor-pointer rounded border border-[#242840] bg-[#0d1017] accent-[#f5a623]"
                        />
                      </td>
                      <td className="px-4 py-4">
                        <div className="flex items-center gap-3">
                          <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-sm font-bold ${nameMissing ? "border-dashed border-[#242840] bg-[#0d1017] text-[#64748b]" : "border-[#242840] bg-[#161b27] text-[#94a3b8]"}`}>
                            {initials(item)}
                          </div>
                          <div>
                            <Link
                              className="text-[15px] font-semibold text-[#e8edf5] transition hover:text-[#f5a623]"
                              to={`/operations/driver-onboarding-review/${item.id}`}
                            >
                              {displayName(item)}
                            </Link>
                            <div className="mt-0.5 text-xs text-[#7c8ba1]">{secondaryLine(item)}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <span className="font-mono text-xs text-[#94a3b8]">{item.application_type || "DRIVER"}</span>
                      </td>
                      <td className="px-4 py-4">
                        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.08em] ${statusBadgeClass(item.status)}`}>
                          <span className="h-1.5 w-1.5 rounded-full bg-current" />
                          {item.status}
                        </span>
                      </td>
                      <td className="px-4 py-4 align-top">
                        <div className="font-mono text-sm text-[#94a3b8]">{formatIsoDay(item.created_at)}</div>
                        <div className="mt-1 text-xs text-[#7c8ba1]">{formatRelative(item.created_at)}</div>
                      </td>
                      <td className="px-4 py-4 align-top">
                        {item.submitted_at ? (
                          <>
                            <div className="font-mono text-sm text-[#94a3b8]">{formatIsoDay(item.submitted_at)}</div>
                            <div className="mt-1 text-xs text-[#7c8ba1]">{formatRelative(item.submitted_at)}</div>
                          </>
                        ) : (
                          <span className="text-sm text-[#475569]">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}

                {!loading && filteredItems.length === 0 && (
                  <tr>
                    <td className="px-4 py-8 text-center text-sm text-[#7c8ba1]" colSpan={6}>
                      No applications match the current filters.
                    </td>
                  </tr>
                )}

                {loading && (
                  <tr>
                    <td className="px-4 py-8 text-center text-sm text-[#7c8ba1]" colSpan={6}>
                      Loading applications...
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between border-t border-[#1c2235] px-5 py-4 text-sm text-[#7c8ba1]">
            <span>
              Showing {filteredItems.length === 0 ? 0 : 1}-{filteredItems.length} of {filteredItems.length}
            </span>
            <div className="flex items-center gap-1">
              <button type="button" className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#1c2235] text-[#94a3b8]">‹</button>
              <button type="button" className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#f5a623]/40 bg-[#f5a623]/10 text-[#f5a623]">1</button>
              <button type="button" className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#1c2235] text-[#94a3b8]">›</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
