import { NavLink } from "react-router-dom";
import { clsx } from "clsx";
import { getControlPlaneBaseUrl, getTenantSlugFromHost } from "../tenant";
import { useEffect, useState } from "react";
import { OPS, ADMIN, PLATFORM } from "../routes";

const adminLinks = [
  { to: ADMIN.COMPANY_PROFILE, label: "Company Profile", icon: BuildingIcon },
  { to: ADMIN.USERS, label: "Users", icon: UsersIcon },
  { to: ADMIN.ROLES, label: "Roles & Permissions", icon: ShieldIcon },
  { to: ADMIN.PAYROLL, label: "Payroll Settings", icon: CardIcon },
  { to: ADMIN.DISPATCH_NUMBERING, label: "Dispatch numbering", icon: HashIcon },
  { to: ADMIN.BROKER_INTAKE, label: "Broker intake", icon: FileIcon },
  { to: ADMIN.SETTINGS_EMAIL, label: "Email", icon: MailIcon },
  { to: ADMIN.INTEGRATIONS_ELD, label: "ELD", icon: TruckIcon },
  { to: ADMIN.INTEGRATIONS_FUEL, label: "Fuel", icon: FuelIcon },
  { to: ADMIN.ONBOARDING, label: "Onboarding Settings", icon: UserPlusIcon },
  { to: ADMIN.DOCUMENTS, label: "Document Rules", icon: FileIcon },
];

function BuildingIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M4 21V9l8-4 8 4v12" />
      <path d="M4 9h16" />
      <path d="M4 13h6" />
      <path d="M14 13h6" />
    </svg>
  );
}
function UsersIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}
function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
    </svg>
  );
}
function CardIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7">
      <rect x="3" y="6" width="18" height="12" rx="2" />
      <path d="M3 10h18" />
      <path d="M7 15h3" />
    </svg>
  );
}
function HashIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M4 9h16" />
      <path d="M4 15h16" />
      <path d="M10 3 8 21" />
      <path d="M16 3l-2 18" />
    </svg>
  );
}
function MailIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7">
      <rect width="20" height="16" x="2" y="4" rx="2" />
      <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
    </svg>
  );
}
function TruckIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2" />
      <path d="M15 18h2" />
      <path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.624l-3.48-4.35A1 1 0 0 0 17.52 8H14" />
    </svg>
  );
}
function FuelIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M3 22h18" />
      <path d="M5 22V12l6-6 6 6v10" />
      <path d="M9 12h6" />
    </svg>
  );
}
function UserPlusIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M19 8v6" />
      <path d="M22 11h-6" />
    </svg>
  );
}
function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
      <path d="M14 2v6h6" />
      <path d="M12 18v-6" />
      <path d="M9 15h6" />
    </svg>
  );
}
function GridIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7">
      <rect x="4" y="4" width="7" height="7" rx="1.5" />
      <rect x="13" y="4" width="7" height="7" rx="1.5" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" />
      <rect x="13" y="13" width="7" height="7" rx="1.5" />
    </svg>
  );
}
function UnlockIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7">
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  );
}

export default function AdminSidebarNav() {
  const slug = getTenantSlugFromHost() ? "" : "";
  const platformUnlockUrl = `${getControlPlaneBaseUrl()}${PLATFORM.TESTING_UNLOCK_LOGIN}`;
  const [collapsed, setCollapsed] = useState(true);

  useEffect(() => {
    const saved = window.localStorage.getItem("admin-sidebar-collapsed");
    if (saved != null) setCollapsed(saved === "true");
  }, []);
  useEffect(() => {
    window.localStorage.setItem("admin-sidebar-collapsed", String(collapsed));
  }, [collapsed]);

  return (
    <aside
      className={clsx(
        "relative min-h-screen shrink-0 border-r border-[#0d121d] bg-[#0a0e14] text-[#94a3b8] transition-[width] duration-300",
        collapsed ? "w-[86px]" : "w-[250px]"
      )}
    >
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(59,130,246,0.04),transparent_26%),repeating-linear-gradient(0deg,transparent,transparent_39px,rgba(255,255,255,0.015)_39px,rgba(255,255,255,0.015)_40px)]" />
      <button
        type="button"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        onClick={() => setCollapsed((p) => !p)}
        className="absolute -right-3 top-1/2 z-20 flex h-14 w-3 -translate-y-1/2 items-center justify-center rounded-full border border-[#141b28] bg-[#0d111a] text-[#475569] shadow-[0_8px_24px_rgba(0,0,0,0.28)] transition hover:text-[#cbd5e1]"
      >
        <span className="text-[10px]">{collapsed ? "›" : "‹"}</span>
      </button>

      <div className="relative flex min-h-screen flex-col items-center px-3 py-6">
        <div className={clsx("mb-8 flex w-full items-center", collapsed ? "justify-center" : "justify-start px-2")}>
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#3b82f6] font-['Barlow_Condensed'] text-2xl font-extrabold tracking-tight text-white">
            ⚙
          </div>
          {!collapsed && (
            <div className="ml-3 min-w-0">
              <div className="font-['Barlow_Condensed'] text-2xl font-bold tracking-wide text-[#e8edf5]">
                Admin
              </div>
              <div className="text-xs text-[#64748b]">Company Configuration</div>
            </div>
          )}
        </div>

        <NavLink
          to={`${slug}${OPS.DASHBOARD}`}
          className={clsx(
            "group flex items-center rounded-2xl border border-transparent text-[#64748b] transition-all hover:border-[#171d2b] hover:bg-[#0f1420] hover:text-[#cbd5e1] mb-4",
            collapsed ? "h-12 w-12 justify-center" : "h-12 w-full px-3"
          )}
        >
          <GridIcon />
          {!collapsed && <span className="ml-3 text-sm font-semibold">Back to Operations</span>}
        </NavLink>

        <nav className="flex w-full flex-1 flex-col items-center gap-2 overflow-auto">
          {adminLinks.map((link) => (
            <NavLink
              key={link.to}
              to={`${slug}${link.to}`}
              className={({ isActive }) =>
                clsx(
                  "group relative flex items-center rounded-2xl border transition-all duration-200",
                  collapsed ? "h-12 w-12 justify-center" : "h-12 w-full justify-start px-3",
                  isActive
                    ? "border-[#1a2231] bg-[#141924] text-[#3b82f6] shadow-[0_6px_16px_rgba(59,130,246,0.08)]"
                    : "border-transparent text-[#64748b] hover:border-[#171d2b] hover:bg-[#0f1420] hover:text-[#cbd5e1]"
                )
              }
              title={collapsed ? link.label : undefined}
            >
              {({ isActive }) => {
                const Icon = link.icon;
                return (
                  <>
                    {isActive && (
                      <span className="absolute left-0 top-1/2 h-7 w-[3px] -translate-y-1/2 rounded-r-full bg-[#3b82f6]" />
                    )}
                    <span className={clsx("flex items-center justify-center", collapsed ? "" : "ml-1")}>
                      <Icon />
                    </span>
                    {!collapsed && <span className="ml-3 min-w-0 truncate text-sm font-semibold">{link.label}</span>}
                  </>
                );
              }}
            </NavLink>
          ))}
        </nav>

        <div className={clsx("mt-4 w-full border-t border-[#141b28] pt-4", collapsed ? "px-0" : "px-1")}>
          <a
            href={platformUnlockUrl}
            target="_blank"
            rel="noopener noreferrer"
            title={
              collapsed
                ? "Unlock sign-in (opens main site; needs platform admin key)"
                : undefined
            }
            className={clsx(
              "group flex items-center rounded-2xl border border-transparent text-[#64748b] transition-all hover:border-[#171d2b] hover:bg-[#0f1420] hover:text-[#cbd5e1]",
              collapsed ? "h-12 w-12 justify-center" : "h-auto w-full flex-col items-stretch px-3 py-2.5"
            )}
          >
            <span className={clsx("flex items-center justify-center", collapsed ? "" : "w-full")}>
              <UnlockIcon />
              {!collapsed && (
                <span className="ml-3 text-sm font-semibold text-[#cbd5e1]">Unlock sign-in (platform)</span>
              )}
            </span>
            {!collapsed && (
              <span className="mt-1.5 block text-[11px] leading-snug text-[#64748b]">
                Opens control plane on the main site. Paste your platform admin API key there (not your user password).
              </span>
            )}
          </a>
        </div>
      </div>
    </aside>
  );
}
