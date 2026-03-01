import { NavLink, useNavigate } from "react-router-dom";
import { clsx } from "clsx";
import { getTenantSlugFromHost } from "../tenant";
import { useAuth } from "../contexts/AuthContext";
import { logoutAndClearTraces } from "../utils/sessionCheck";
import { useState } from "react";

const links = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/payroll/pay-periods", label: "Pay Periods" },
  { to: "/payroll/pay-runs", label: "Pay Runs" },
  { to: "/payroll/documents", label: "Documents" },
  { to: "/driver-onboarding", label: "Driver Onboarding" },
  { to: "/admin/driver-onboarding", label: "Onboarding Review" },
  { to: "/admin/diagnostics/database", label: "DB Diagnostics" },
];

export default function SidebarNav() {
  const navigate = useNavigate();
  const { clearSession } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);
  const slug = getTenantSlugFromHost() ? "" : "";

  const handleLogout = () => {
    if (loggingOut) return;
    setLoggingOut(true);
    clearSession();
    // Clear storage and call logout API in background; never wait on server so we don't get stuck
    logoutAndClearTraces();
    setLoggingOut(false);
    navigate("/login", { replace: true });
  };

  return (
    <aside className="w-64 min-h-screen bg-white border-r border-gray-200 flex flex-col shrink-0">
      <div className="px-4 py-5 border-b border-gray-200 shrink-0">
        <h1 className="text-lg font-semibold">Trucking ERP</h1>
        <p className="text-sm text-gray-500">Payroll & Settlements</p>
      </div>
      <nav className="p-4 space-y-1 flex-1 overflow-auto">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={`${slug}${link.to}`}
            className={({ isActive }) =>
              clsx(
                "block px-3 py-2 rounded-md text-sm font-medium",
                isActive ? "bg-blue-50 text-blue-700" : "text-gray-700 hover:bg-gray-100"
              )
            }
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="p-4 border-t border-gray-200 shrink-0 mt-auto">
        <button
          type="button"
          onClick={handleLogout}
          disabled={loggingOut}
          className="w-full px-3 py-2.5 rounded-md text-sm font-medium text-red-700 bg-red-50 border border-red-200 hover:bg-red-100 hover:border-red-300 disabled:opacity-50 disabled:bg-red-50"
        >
          {loggingOut ? "Logging out…" : "Log out"}
        </button>
      </div>
    </aside>
  );
}
