import { Link } from "react-router-dom";
import PlatformUnlockLoginForm from "../components/PlatformUnlockLoginForm";
import { PLATFORM } from "../routes";

export default function PlatformHomePage() {
  return (
    <div>
      <h1 className="text-xl font-semibold text-white tracking-tight">Control plane</h1>
      <p className="mt-1 text-sm text-slate-400">
        Internal tools for platform operators. Uses{" "}
        <code className="text-slate-300">X-Platform-Admin-Key</code> on the{" "}
        <strong className="text-slate-200 font-medium">apex hostname only</strong> (not{" "}
        <code className="text-slate-400">demo.…</code> workspace URLs).
      </p>
      <p className="mt-2 text-sm text-slate-400">
        <strong className="text-slate-200 font-medium">Unlock blocked sign-in:</strong> use the form below, the{" "}
        <span className="text-slate-300">Unlock login</span> link in the header, or{" "}
        <Link to={PLATFORM.TESTING_UNLOCK_LOGIN} className="text-indigo-400 hover:text-indigo-300 underline">
          open the full-page tool
        </Link>
        .
      </p>

      <section className="mt-6 rounded-lg border border-indigo-900/50 bg-slate-900/60 p-4 ring-1 ring-indigo-500/20">
        <h2 className="text-base font-semibold text-white">Unlock login</h2>
        <p className="mt-1 text-xs text-slate-500">
          Clear password-fail streak and tenant+email login / step-up limits for one user (does not clear IP throttle).
        </p>
        <div className="mt-4">
          <PlatformUnlockLoginForm compact />
        </div>
      </section>

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
        <li>
          <Link
            to={PLATFORM.TESTING_UNLOCK_LOGIN}
            className="block rounded-lg border border-slate-800 bg-slate-900/50 p-4 hover:border-slate-600"
          >
            <h2 className="font-medium text-white">Unlock login (full page)</h2>
            <p className="mt-1 text-sm text-slate-400">Same tool with more room for results.</p>
          </Link>
        </li>
      </ul>
    </div>
  );
}
