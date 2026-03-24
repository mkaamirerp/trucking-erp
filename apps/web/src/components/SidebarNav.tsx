import { NavLink, useNavigate } from "react-router-dom";
import { clsx } from "clsx";
import { getTenantSlugFromHost } from "../tenant";
import { useAuth } from "../contexts/AuthContext";
import { useEffect, useState } from "react";
import { useMe, isTenantAdmin } from "../hooks/useMe";
import { OPS, ADMIN } from "../routes";

function BoardIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="6" height="6" rx="1" />
      <rect x="15" y="3" width="6" height="6" rx="1" />
      <rect x="3" y="15" width="6" height="6" rx="1" />
      <rect x="15" y="15" width="6" height="6" rx="1" />
    </svg>
  );
}

const operationsLinks = [
  { to: OPS.DASHBOARD, label: "Dashboard", short: "Home", icon: GridIcon },
  { to: OPS.INBOX, label: "Load Intake", short: "Intake", icon: MailIcon },
  { to: OPS.DISPATCH, label: "Dispatch", short: "Dispatch", icon: BoardIcon },
  { to: OPS.DRIVER_ONBOARDING_REVIEW, label: "Onboarding Review", short: "Review", icon: ReviewIcon },
  { to: OPS.DRIVER_ONBOARDING_APPLICANT, label: "Driver Onboarding", short: "Drivers", icon: UserIcon },
  { to: OPS.FLEET, label: "Fleet", short: "Fleet", icon: TruckIcon },
  { to: OPS.LOADS, label: "Loads", short: "Loads", icon: BoxIcon },
  { to: OPS.PAY_RUNS, label: "Pay Runs", short: "Payroll", icon: BoxIcon },
  { to: OPS.PAY_PERIODS, label: "Pay Periods", short: "Cards", icon: CardIcon },
  { to: OPS.DOCUMENTS, label: "Documents", short: "Docs", icon: FolderIcon },
];

function GridIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="4" width="7" height="7" rx="1.5" />
      <rect x="13" y="4" width="7" height="7" rx="1.5" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" />
      <rect x="13" y="13" width="7" height="7" rx="1.5" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4Z" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </svg>
  );
}

function TruckIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 7h11v8H3z" />
      <path d="M14 10h3l3 3v2h-6z" />
      <circle cx="7.5" cy="17.5" r="1.5" />
      <circle cx="17.5" cy="17.5" r="1.5" />
    </svg>
  );
}

function BoxIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="m12 3 8 4.5-8 4.5-8-4.5Z" />
      <path d="M4 7.5V16.5L12 21l8-4.5V7.5" />
      <path d="M12 12v9" />
    </svg>
  );
}

function CardIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="6" width="18" height="12" rx="2" />
      <path d="M3 10h18" />
      <path d="M7 15h3" />
    </svg>
  );
}

function FolderIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 7.5A1.5 1.5 0 0 1 4.5 6H10l1.5 2H19.5A1.5 1.5 0 0 1 21 9.5v8A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5Z" />
    </svg>
  );
}

function ReviewIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H15l5 5v9.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5Z" />
      <path d="M14 4v6h6" />
      <path d="m9 13 2 2 4-4" />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M4 7l8 6 8-6" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 8.5A3.5 3.5 0 1 0 15.5 12 3.5 3.5 0 0 0 12 8.5Z" />
      <path d="M19 12a7.4 7.4 0 0 0-.08-1l2-1.55-2-3.46-2.38.88a7.54 7.54 0 0 0-1.74-1l-.36-2.5h-4l-.36 2.5a7.54 7.54 0 0 0-1.74 1L5.08 5.99l-2 3.46 2 1.55a7.4 7.4 0 0 0 0 2l-2 1.55 2 3.46 2.38-.88a7.54 7.54 0 0 0 1.74 1l.36 2.5h4l.36-2.5a7.4 7.4 0 0 0 1.74-1l2.38.88 2-3.46-2-1.55a7.4 7.4 0 0 0 .08-1Z" />
    </svg>
  );
}

function NavItem({
  link,
  slug,
  collapsed,
}: {
  link: { to: string; label: string; short: string; icon: () => JSX.Element };
  slug: string;
  collapsed: boolean;
}) {
  const Icon = link.icon;
  return (
    <NavLink
      to={`${slug}${link.to}`}
      className={({ isActive }) =>
        clsx(
          "group relative flex items-center rounded-2xl border transition-all duration-200",
          collapsed ? "h-12 w-12 justify-center" : "h-12 w-full justify-start px-3",
          isActive
            ? "border-[#1a2231] bg-[#141924] text-[#f5a623] shadow-[0_6px_16px_rgba(245,166,35,0.05)]"
            : "border-transparent text-[#64748b] hover:border-[#171d2b] hover:bg-[#0f1420] hover:text-[#cbd5e1]"
        )
      }
      title={collapsed ? link.label : undefined}
    >
      {({ isActive }) => (
        <>
          {isActive && <span className="absolute left-0 top-1/2 h-7 w-[3px] -translate-y-1/2 rounded-r-full bg-[#f5a623]" />}
          <span className={clsx("flex items-center justify-center", collapsed ? "" : "ml-1")}>
            <Icon />
          </span>
          {!collapsed && (
            <span className="ml-3 min-w-0">
              <span className="block truncate text-sm font-semibold text-current">{link.short}</span>
              <span className="block truncate text-[11px] text-[#475569]">{link.label}</span>
            </span>
          )}
        </>
      )}
    </NavLink>
  );
}

export default function SidebarNav() {
  const navigate = useNavigate();
  const { logout, isLoggingOut } = useAuth();
  const { me } = useMe();
  const [collapsed, setCollapsed] = useState(true);
  const slug = getTenantSlugFromHost() ? "" : "";
  const showAdmin = isTenantAdmin(me?.roles ?? []);

  useEffect(() => {
    const saved = window.localStorage.getItem("sidebar-collapsed");
    if (saved != null) setCollapsed(saved === "true");
  }, []);

  useEffect(() => {
    window.localStorage.setItem("sidebar-collapsed", String(collapsed));
  }, [collapsed]);

  const handleLogout = async () => {
    if (isLoggingOut) return;
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <aside
      className={clsx(
        "relative min-h-screen shrink-0 border-r border-[#0d121d] bg-[#080a0f] text-[#94a3b8] transition-[width] duration-300",
        collapsed ? "w-[86px]" : "w-[250px]"
      )}
    >
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(245,166,35,0.05),transparent_26%),repeating-linear-gradient(0deg,transparent,transparent_39px,rgba(255,255,255,0.02)_39px,rgba(255,255,255,0.02)_40px)]" />
      <button
        type="button"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        onClick={() => setCollapsed((prev) => !prev)}
        className="absolute -right-3 top-1/2 z-20 flex h-14 w-3 -translate-y-1/2 items-center justify-center rounded-full border border-[#141b28] bg-[#0d111a] text-[#475569] shadow-[0_8px_24px_rgba(0,0,0,0.28)] transition hover:text-[#cbd5e1]"
      >
        <span className="text-[10px]">{collapsed ? "›" : "‹"}</span>
      </button>

      <div className="relative flex min-h-screen flex-col items-center px-3 py-6">
        <div className={clsx("mb-8 flex w-full items-center", collapsed ? "justify-center" : "justify-start px-2")}>
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#f5a623] font-['Barlow_Condensed'] text-2xl font-extrabold tracking-tight text-[#080a0f]">
            FP
          </div>
          {!collapsed && (
            <div className="ml-3 min-w-0">
              <div className="font-['Barlow_Condensed'] text-2xl font-bold tracking-wide text-[#e8edf5]">FleetPro</div>
              <div className="text-xs text-[#64748b]">Operations Suite</div>
            </div>
          )}
        </div>

        <nav className="flex w-full flex-1 flex-col gap-2 overflow-auto">
          {/* Operations section */}
          <div className="space-y-2">
            {!collapsed && (
              <div className="px-2 text-[10px] font-semibold uppercase tracking-wider text-[#475569]">Operations</div>
            )}
            {operationsLinks.map((link) => (
              <NavItem key={link.to} link={link} slug={slug} collapsed={collapsed} />
            ))}
          </div>

          {/* Administration section — only for admin roles */}
          {showAdmin && (
            <div className="mt-4 space-y-2 border-t border-[#0d121d] pt-4">
              {!collapsed && (
                <div className="px-2 text-[10px] font-semibold uppercase tracking-wider text-[#64748b]">Administration</div>
              )}
              <NavItem
                link={{ to: ADMIN.COMPANY_PROFILE, label: "Company Settings", short: "Admin", icon: GearIcon }}
                slug={slug}
                collapsed={collapsed}
              />
            </div>
          )}
        </nav>

        <div className={clsx("mt-6 flex w-full flex-col items-center border-t border-[#0d121d] pt-5", collapsed ? "" : "px-1")}>
        <button
          type="button"
          onClick={handleLogout}
          disabled={isLoggingOut}
          title={collapsed ? "Log out" : undefined}
          className={clsx(
            "group flex items-center rounded-2xl border border-transparent text-[#64748b] transition-all hover:border-[#171d2b] hover:bg-[#0f1420] hover:text-[#f87171] disabled:opacity-50",
            collapsed ? "h-12 w-12 justify-center" : "h-12 w-full px-3"
          )}
        >
          <span className="flex items-center justify-center">
            <GearIcon />
          </span>
          {!collapsed && (
            <span className="ml-3">
              <span className="block text-sm font-semibold text-current">{isLoggingOut ? "Logging out..." : "Settings"}</span>
              <span className="block text-[11px] text-[#475569]">End session</span>
            </span>
          )}
        </button>
      </div>
      </div>
    </aside>
  );
}
