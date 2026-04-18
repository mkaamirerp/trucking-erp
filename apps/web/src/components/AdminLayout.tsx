import { Outlet } from "react-router-dom";
import TopNav from "./TopNav";

export default function AdminLayout() {
  return (
    <div className="min-h-screen bg-[var(--trk-bg)] text-[var(--trk-text)]">
      <div className="flex flex-col">
        <TopNav />
        <main className="flex-1 overflow-auto bg-transparent p-6 space-y-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
