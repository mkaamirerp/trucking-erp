import { Outlet } from "react-router-dom";
import TopNav from "./TopNav";

export default function AdminLayout() {
  return (
    <div className="trk-app-shell">
      <TopNav />
      <main className="trk-app-main">
        <Outlet />
      </main>
    </div>
  );
}
