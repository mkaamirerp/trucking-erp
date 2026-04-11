import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { useState, useRef } from "react";
import { clsx } from "clsx";
import { useAuth } from "../contexts/AuthContext";
import { useMe, isTenantAdmin } from "../hooks/useMe";
import { OPS, ADMIN } from "../routes";

// ─── Navigation data ──────────────────────────────────────────────────────────

const dispatchLinks = [
  { label: "Dispatch", to: OPS.DISPATCH },
  { label: "Loads", to: OPS.LOADS },
  { label: "Email", to: OPS.EMAIL_LOAD },
  { label: "Intake", to: OPS.INTAKE },
];

const fleetLinks = [
  { label: "Drivers", to: OPS.DRIVER_ONBOARDING_APPLICANT },
  { label: "Review", to: OPS.DRIVER_ONBOARDING_REVIEW },
  { label: "Fleet", to: OPS.FLEET },
  { label: "Brokers", to: OPS.BROKERS },
];

const financeLinks = [
  { label: "Payroll", to: OPS.PAY_RUNS },
  { label: "Cards", to: OPS.PAY_PERIODS },
  { label: "Docs", to: OPS.DOCUMENTS },
];

const settingsGroups = [
  {
    label: "Company",
    items: [
      { label: "Company Profile", to: ADMIN.COMPANY_PROFILE },
      { label: "Users", to: ADMIN.USERS },
      { label: "Roles & Permissions", to: ADMIN.ROLES },
    ],
  },
  {
    label: "Integrations",
    items: [
      { label: "Email", to: ADMIN.SETTINGS_EMAIL },
      { label: "ELD", to: ADMIN.INTEGRATIONS_ELD },
      { label: "Fuel", to: ADMIN.INTEGRATIONS_FUEL },
    ],
  },
  {
    label: "Config",
    items: [
      { label: "Payroll Settings", to: ADMIN.PAYROLL },
      { label: "Dispatch Numbering", to: ADMIN.DISPATCH_NUMBERING },
      { label: "Broker Intake", to: ADMIN.BROKER_INTAKE },
      { label: "Onboarding Settings", to: ADMIN.ONBOARDING },
      { label: "Document Rules", to: ADMIN.DOCUMENTS },
    ],
  },
];

// ─── Breadcrumb helper ────────────────────────────────────────────────────────

function usePageLabel(): string {
  const { pathname } = useLocation();
  if (pathname === OPS.DASHBOARD) return "Dashboard";
  if (pathname.startsWith("/dispatch")) return "Dispatch";
  if (pathname.startsWith("/loads")) return "Loads";
  if (pathname.startsWith("/inbox")) return "Email";
  if (pathname.startsWith("/intake")) return "Intake";
  if (pathname.startsWith("/operations/driver-onboarding")) return "Onboarding Review";
  if (pathname.startsWith("/driver-onboarding")) return "Drivers";
  if (pathname.startsWith("/fleet")) return "Fleet";
  if (pathname.startsWith("/brokers")) return "Brokers";
  if (pathname.startsWith("/payroll/pay-runs")) return "Pay Runs";
  if (pathname.startsWith("/payroll/pay-periods")) return "Pay Periods";
  if (pathname.startsWith("/payroll/documents")) return "Documents";
  if (pathname.startsWith("/admin/company-profile")) return "Company Profile";
  if (pathname.startsWith("/admin/users")) return "Users";
  if (pathname.startsWith("/admin/roles")) return "Roles & Permissions";
  if (pathname.startsWith("/admin/payroll")) return "Payroll Settings";
  if (pathname.startsWith("/admin/dispatch-numbering")) return "Dispatch Numbering";
  if (pathname.startsWith("/admin/broker-intake")) return "Broker Intake";
  if (pathname.startsWith("/admin/settings/email")) return "Email Settings";
  if (pathname.startsWith("/admin/integrations/eld")) return "ELD";
  if (pathname.startsWith("/admin/integrations/fuel")) return "Fuel";
  if (pathname.startsWith("/admin/onboarding")) return "Onboarding Settings";
  if (pathname.startsWith("/admin/documents")) return "Document Rules";
  return "";
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function TopNavLink({ label, to }: { label: string; to: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        clsx(
          "box-border inline-flex min-h-[2.25rem] items-end border-b-2 px-3 py-1 text-sm font-medium leading-none transition-colors whitespace-nowrap",
          isActive
            ? "border-[#f5a623] text-[#e8ecf4]"
            : "border-transparent text-[#7a8299] hover:text-[#e8ecf4]"
        )
      }
    >
      {label}
    </NavLink>
  );
}

function NavGroup({ label, links }: { label: string; links: { label: string; to: string }[] }) {
  return (
    <div className="flex flex-col justify-end">
      <div className="px-3 pb-[3px] text-[9px] font-semibold uppercase tracking-widest text-[#4a5068]">
        {label}
      </div>
      <div className="flex items-center">
        {links.map((link) => (
          <TopNavLink key={link.to} label={link.label} to={link.to} />
        ))}
      </div>
    </div>
  );
}

function Divider() {
  return <div className="mx-2 h-8 w-px shrink-0 bg-[#252a38]" />;
}

function SettingsDropdown() {
  const [open, setOpen] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const open_ = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const close_ = () => {
    closeTimer.current = setTimeout(() => setOpen(false), 100);
  };

  return (
    <div className="relative flex items-center" onMouseEnter={open_} onMouseLeave={close_}>
      <button
        type="button"
        className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-[#7a8299] transition-colors hover:text-[#e8ecf4]"
      >
        <GearIcon />
        <span>Settings</span>
        <ChevronDownIcon />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-0.5 flex gap-5 rounded-xl border border-[#252a38] bg-[#141720] px-5 py-4 shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
          {settingsGroups.map((group) => (
            <div key={group.label} className="flex min-w-[148px] flex-col">
              <div className="mb-2 text-[9px] font-semibold uppercase tracking-widest text-[#4a5068]">
                {group.label}
              </div>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    clsx(
                      "rounded px-2 py-1.5 text-sm transition-colors",
                      isActive
                        ? "bg-[#1c1f2b] text-[#f5a623]"
                        : "text-[#7a8299] hover:bg-[#1c1f2b] hover:text-[#e8ecf4]"
                    )
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TenantPill({ me }: { me: ReturnType<typeof useMe>["me"] }) {
  const slug = me?.tenant_slug ?? "";
  const email = (me?.email as string) ?? "";
  const initials = (slug || email).slice(0, 2).toUpperCase();
  return (
    <div className="flex items-center gap-2 border-l border-[#252a38] pl-3">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#252a38] text-[10px] font-bold text-[#f5a623]">
        {initials}
      </div>
      {slug && <span className="text-xs text-[#4a5068]">{slug}</span>}
    </div>
  );
}

function BreadcrumbBar({ pageLabel }: { pageLabel: string }) {
  return (
    <div className="flex h-8 items-center border-b border-[#252a38] bg-[#141720] px-5">
      <span className="text-xs text-[#4a5068]">FleetPro</span>
      {pageLabel && (
        <>
          <span className="mx-2 text-xs text-[#252a38]">/</span>
          <span className="text-xs text-[#7a8299]">{pageLabel}</span>
        </>
      )}
    </div>
  );
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function GearIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-3.5 w-3.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-3 w-3"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

export default function TopNav() {
  const navigate = useNavigate();
  const { logout, isLoggingOut } = useAuth();
  const { me } = useMe();
  const isAdmin = isTenantAdmin(me?.roles ?? []);
  const pageLabel = usePageLabel();

  const handleLogout = async () => {
    if (isLoggingOut) return;
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-[#252a38] bg-[#0d0f14]">
        <div className="flex h-14 items-center px-4">
          {/* Logo */}
          <div className="mr-4 flex shrink-0 items-center gap-2.5 border-r border-[#252a38] pr-5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#f5a623] font-['Barlow_Condensed'] text-sm font-extrabold tracking-tight text-[#080a0f]">
              FP
            </div>
            <span className="font-['Barlow_Condensed'] text-[17px] font-bold tracking-wide text-[#e8ecf4]">
              FleetPro
            </span>
          </div>

          {/* Navigation */}
          <nav className="flex items-center">
            {/* Dashboard — standalone, no group label */}
            <div className="flex flex-col justify-end">
              <div className="px-3 pb-[3px] text-[9px] font-semibold uppercase tracking-widest text-transparent select-none">
                ·
              </div>
              <TopNavLink label="Dashboard" to={OPS.DASHBOARD} />
            </div>

            <Divider />

            <NavGroup label="Dispatch" links={dispatchLinks} />

            <Divider />

            <NavGroup label="Fleet" links={fleetLinks} />

            <Divider />

            <NavGroup label="Finance" links={financeLinks} />
          </nav>

          {/* Push right side to the end */}
          <div className="flex-1" />

          {/* Right: Settings (admin only), tenant pill, sign out */}
          <div className="flex items-center gap-1">
            {isAdmin && <SettingsDropdown />}
            <TenantPill me={me} />
            <button
              type="button"
              onClick={handleLogout}
              disabled={isLoggingOut}
              className="ml-2 rounded px-3 py-1.5 text-sm text-[#7a8299] transition-colors hover:bg-[#1c1f2b] hover:text-[#f87171] disabled:opacity-50"
            >
              {isLoggingOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </div>
      </header>
      <BreadcrumbBar pageLabel={pageLabel} />
    </>
  );
}
