import { Outlet } from "react-router-dom";
import TopNav from "./TopNav";

export default function AdminLayout() {
  return (
    <div className="min-h-screen bg-[#080a0f] text-[#e8edf5]">
      <div className="flex flex-col">
        <TopNav />
        <main className="flex-1 overflow-auto bg-transparent p-6 space-y-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
