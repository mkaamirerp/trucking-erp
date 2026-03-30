import { Link } from "react-router-dom";
import { PLATFORM } from "../routes";

export default function PlatformHomePage() {
  return (
    <div>
      <h1 className="text-xl font-semibold text-white tracking-tight">Control plane</h1>
      <p className="mt-1 text-sm text-slate-400">
        Internal tools for platform operators. Uses{" "}
        <code className="text-slate-300">X-Platform-Admin-Key</code> and the apex host only.
      </p>

      <ul className="mt-8 grid gap-4 sm:grid-cols-2">
        <li>
          <Link
            to={PLATFORM.TENANTS}
            className="block rounded-lg border border-slate-800 bg-slate-900/50 p-4 hover:border-slate-600"
          >
            <h2 className="font-medium text-white">Tenants</h2>
            <p className="mt-1 text-sm text-slate-400">List and inspect platform workspaces.</p>
          </Link>
        </li>
        <li>
          <Link
            to={PLATFORM.LOGIN_FAILURES}
            className="block rounded-lg border border-slate-800 bg-slate-900/50 p-4 hover:border-slate-600"
          >
            <h2 className="font-medium text-white">Login failures</h2>
            <p className="mt-1 text-sm text-slate-400">Recent failed sign-in audit rows.</p>
          </Link>
        </li>
      </ul>
    </div>
  );
}
