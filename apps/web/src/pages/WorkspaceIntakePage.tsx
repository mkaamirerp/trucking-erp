import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useLocation, useSearchParams } from "react-router-dom";
import { submitWorkspaceIntake } from "../api";

const PACKAGE_CODES = ["FREE_TRIAL", "BASIC", "PRO", "ENTERPRISE"] as const;
const PACKAGE_LABEL: Record<(typeof PACKAGE_CODES)[number], string> = {
  FREE_TRIAL: "Free trial",
  BASIC: "Basic",
  PRO: "Pro",
  ENTERPRISE: "Enterprise",
};

function WorkspaceIntakePage() {
  const nav = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const pkgParam = searchParams.get("package");
  const invalidPackageFromRoute = Boolean(
    (location.state as { invalidPackage?: boolean } | null)?.invalidPackage,
  );
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [confirmEmail, setConfirmEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [selectedPackage, setSelectedPackage] = useState<(typeof PACKAGE_CODES)[number] | "">("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initialFromQuery = useMemo(() => {
    if (!pkgParam) return null;
    if (PACKAGE_CODES.includes(pkgParam as (typeof PACKAGE_CODES)[number])) {
      return pkgParam as (typeof PACKAGE_CODES)[number];
    }
    return false;
  }, [pkgParam]);

  useEffect(() => {
    if (initialFromQuery === false) {
      nav("/workspace-intake", { replace: true, state: { invalidPackage: true } });
    } else if (initialFromQuery) {
      setSelectedPackage(initialFromQuery);
    }
  }, [initialFromQuery, nav]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!selectedPackage) {
      setError("Select a package.");
      return;
    }
    if (email.trim().toLowerCase() !== confirmEmail.trim().toLowerCase()) {
      setError("Email addresses must match.");
      return;
    }
    setBusy(true);
    try {
      await submitWorkspaceIntake({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        confirm_email: confirmEmail.trim(),
        phone_number: phone.trim(),
        selected_package_code: selectedPackage,
      });
      setDone(true);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : typeof err === "string" ? err : "Something went wrong.";
      setError(msg.slice(0, 400));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center px-6 py-12">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/50 p-8 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-sm font-semibold text-slate-400">TruckERP</div>
            <h1 className="mt-1 text-2xl font-bold tracking-tight">Request workspace access</h1>
          </div>
          <Link to="/" className="text-sm text-slate-400 hover:text-white shrink-0">
            Home
          </Link>
        </div>

        <p className="mt-3 text-sm text-slate-400 leading-relaxed">
          Enter your details. We’ll email you a one-time link to continue setup (valid 24 hours).
        </p>

        {invalidPackageFromRoute ? (
          <div className="mt-4 rounded-xl border border-amber-500/40 bg-amber-950/30 px-3 py-2 text-sm text-amber-100">
            That package link was invalid. Choose a package below.
          </div>
        ) : null}

        {done ? (
          <div className="mt-6 space-y-3 text-sm text-slate-300">
            <p>
              If this email can receive mail, you will get a link to continue shortly. Check your inbox and spam folder.
            </p>
            <Link to="/" className="inline-block text-indigo-400 hover:text-indigo-300 font-medium">
              Back to home
            </Link>
          </div>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={onSubmit}>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Package</label>
              <select
                required
                className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm outline-none focus:border-indigo-500"
                value={selectedPackage}
                onChange={(e) => setSelectedPackage(e.target.value as (typeof PACKAGE_CODES)[number] | "")}
              >
                <option value="" disabled>
                  Select a package
                </option>
                {PACKAGE_CODES.map((c) => (
                  <option key={c} value={c}>
                    {PACKAGE_LABEL[c]} ({c})
                  </option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">First name</label>
                <input
                  required
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm outline-none focus:border-indigo-500"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  autoComplete="given-name"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Last name</label>
                <input
                  required
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm outline-none focus:border-indigo-500"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  autoComplete="family-name"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Email</label>
              <input
                required
                type="email"
                className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm outline-none focus:border-indigo-500"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Confirm email</label>
              <input
                required
                type="email"
                className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm outline-none focus:border-indigo-500"
                value={confirmEmail}
                onChange={(e) => setConfirmEmail(e.target.value)}
                autoComplete="email"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Phone</label>
              <input
                required
                type="tel"
                className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm outline-none focus:border-indigo-500"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                autoComplete="tel"
              />
            </div>

            {error ? (
              <div className="rounded-xl border border-rose-500/40 bg-rose-950/30 px-3 py-2 text-sm text-rose-100">
                {error}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 py-3 text-sm font-semibold text-white hover:opacity-95 disabled:opacity-60"
            >
              {busy ? "Sending…" : "Email me the link"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default WorkspaceIntakePage;
