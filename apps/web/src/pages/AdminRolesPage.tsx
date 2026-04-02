import { useMe } from "../hooks/useMe";
import AdminPlaceholderPage from "./AdminPlaceholderPage";

export default function AdminRolesPage() {
  const { me } = useMe();
  const roles = (me?.roles || []).join(", ") || "None";

  return (
    <div className="space-y-6">
      <h1 className="font-['Barlow_Condensed'] text-3xl font-bold tracking-tight text-[#e8edf5]">
        Roles & Permissions
      </h1>
      <p className="text-[#94a3b8]">
        Kanban-style RBAC management coming later. For now, this page shows your current role.
      </p>
      <div className="rounded-xl border border-[#1e293b] bg-[#0a0e14] p-6">
        <h2 className="mb-2 text-sm font-medium text-[#94a3b8]">Your current role(s)</h2>
        <p className="font-mono text-[#e8edf5]">{roles}</p>
      </div>
      <div className="rounded-xl border border-dashed border-[#334155] bg-[#0a0e14]/50 p-12 text-center text-[#64748b]">
        Full Kanban RBAC manager — coming soon
      </div>
    </div>
  );
}
