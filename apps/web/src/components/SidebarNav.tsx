import { NavLink } from "react-router-dom";
import { clsx } from "clsx";

const links = [
  { to: "/payroll/pay-periods", label: "Pay Periods" },
  { to: "/payroll/pay-runs", label: "Pay Runs" },
  { to: "/payroll/documents", label: "Documents" },
];

export default function SidebarNav() {
  return (
    <aside className="w-64 min-h-screen bg-white border-r border-gray-200">
      <div className="px-4 py-5 border-b border-gray-200">
        <h1 className="text-lg font-semibold">Trucking ERP</h1>
        <p className="text-sm text-gray-500">Payroll & Settlements</p>
      </div>
      <nav className="p-4 space-y-1">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
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
    </aside>
  );
}
