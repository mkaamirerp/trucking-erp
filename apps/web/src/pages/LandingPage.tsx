import React from "react";
import { Link, useSearchParams } from "react-router-dom";

const FeatureCard = ({
  title,
  desc,
  icon,
}: {
  title: string;
  desc: string;
  icon: React.ReactNode;
}) => (
  <div className="rounded-2xl border border-slate-200 bg-white/70 p-6 shadow-sm backdrop-blur hover:shadow-md transition">
    <div className="flex items-start gap-4">
      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow">
        {icon}
      </div>
      <div>
        <h3 className="text-base font-semibold text-slate-900">{title}</h3>
        <p className="mt-1 text-sm leading-relaxed text-slate-600">{desc}</p>
      </div>
    </div>
  </div>
);

const Step = ({
  num,
  title,
  desc,
}: {
  num: string;
  title: string;
  desc: string;
}) => (
  <div className="flex gap-4">
    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white text-sm font-semibold">
      {num}
    </div>
    <div>
      <h4 className="text-sm font-semibold text-slate-900">{title}</h4>
      <p className="mt-1 text-sm text-slate-600">{desc}</p>
    </div>
  </div>
);

const Check = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none">
    <path
      d="M20 6L9 17l-5-5"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const Truck = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none">
    <path
      d="M3 7h11v10H3V7Z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
    />
    <path
      d="M14 10h4l3 3v4h-7v-7Z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
    />
    <path
      d="M7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"
      stroke="currentColor"
      strokeWidth="2"
    />
    <path
      d="M17 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"
      stroke="currentColor"
      strokeWidth="2"
    />
  </svg>
);

const Shield = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none">
    <path
      d="M12 2l8 4v6c0 5-3.4 9.4-8 10-4.6-.6-8-5-8-10V6l8-4Z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
    />
  </svg>
);

const Chart = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none">
    <path
      d="M4 19V5"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    />
    <path
      d="M8 19V11"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    />
    <path
      d="M12 19V7"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    />
    <path
      d="M16 19V14"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    />
    <path
      d="M20 19V9"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    />
  </svg>
);

const Users = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none">
    <path
      d="M16 11a4 4 0 1 0-8 0 4 4 0 0 0 8 0Z"
      stroke="currentColor"
      strokeWidth="2"
    />
    <path
      d="M4 22v-1a7 7 0 0 1 14 0v1"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    />
  </svg>
);

function LandingPage() {
  const [searchParams] = useSearchParams();
  const showDebugLink =
    searchParams.get("debug") === "1" || import.meta.env.DEV;

  return (
    <div className="min-h-screen bg-slate-950">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-24 left-1/2 h-[520px] w-[880px] -translate-x-1/2 rounded-full bg-gradient-to-r from-blue-600/35 via-indigo-600/25 to-cyan-500/20 blur-3xl" />
      </div>

      <header className="relative z-10">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow">
              <Truck />
            </div>
            <div>
              <div className="text-sm font-semibold text-white">Trucking ERP</div>
              <div className="text-xs text-slate-300">Dispatch • Payroll • Compliance</div>
            </div>
          </div>

          <nav className="hidden items-center gap-6 md:flex">
            <a href="#features" className="text-sm text-slate-200 hover:text-white">
              Features
            </a>
            <a href="#how" className="text-sm text-slate-200 hover:text-white">
              How it works
            </a>
            <a href="#pricing" className="text-sm text-slate-200 hover:text-white">
              Pricing
            </a>
            {showDebugLink && (
              <Link
                to="/debug/dl-images?tenant=52&app=13"
                className="text-sm text-amber-300 hover:text-amber-200"
              >
                Debug → DL Gallery
              </Link>
            )}
          </nav>

          <div className="flex items-center gap-3">
            <Link
              to="/signup"
              className="rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-sm font-semibold text-white hover:bg-white/15 transition"
            >
              Sign up
            </Link>
            <Link
              to="/login"
              className="hidden rounded-xl bg-white px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-100 transition md:inline-flex"
            >
              Login
            </Link>
            <Link
              to="/workspace-intake"
              className="hidden rounded-xl border border-white/20 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10 transition lg:inline-flex"
            >
              New workspace
            </Link>
          </div>
        </div>
      </header>

      <main className="relative z-10">
        <section className="mx-auto max-w-6xl px-6 pt-10 pb-14 md:pt-16">
          <div className="grid items-center gap-10 md:grid-cols-2">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-200">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />
                Multi-tenant SaaS • Secure • Fast
              </div>

              <h1 className="mt-5 text-4xl font-extrabold tracking-tight text-white md:text-5xl">
                Run your trucking business on{" "}
                <span className="bg-gradient-to-r from-blue-400 via-indigo-300 to-cyan-300 bg-clip-text text-transparent">
                  one dashboard
                </span>
              </h1>

              <p className="mt-4 text-base leading-relaxed text-slate-200">
                Dispatch board, driver onboarding, payroll, documents, compliance, and KPIs —
                designed for real operations and built for strict tenant isolation.
              </p>

              <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                <Link
                  to="/workspace-intake"
                  className="inline-flex items-center justify-center rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow hover:opacity-95 transition"
                >
                  Create your workspace
                </Link>
                <a
                  href="#features"
                  className="inline-flex items-center justify-center rounded-xl border border-white/15 bg-white/5 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10 transition"
                >
                  See features
                </a>
              </div>

              <div className="mt-6 grid gap-2 text-sm text-slate-200">
                <div className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Tenant data separation (platform DB vs tenant DB)
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Driver onboarding + documents + approval workflow
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Dispatch KPIs, active loads, drivers on duty
                </div>
              </div>
            </div>

            <div className="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-xl backdrop-blur">
              <div className="rounded-2xl bg-slate-900/60 p-5">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold text-white">Dispatch Snapshot</div>
                  <div className="text-xs text-slate-300">Live</div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-2xl bg-white/5 p-4">
                    <div className="text-xs text-slate-300">Active Loads</div>
                    <div className="mt-1 text-2xl font-bold text-white">12</div>
                    <div className="mt-2 text-xs text-emerald-300">+2 today</div>
                  </div>
                  <div className="rounded-2xl bg-white/5 p-4">
                    <div className="text-xs text-slate-300">Drivers On Duty</div>
                    <div className="mt-1 text-2xl font-bold text-white">8</div>
                    <div className="mt-2 text-xs text-cyan-300">HOS OK</div>
                  </div>
                  <div className="rounded-2xl bg-white/5 p-4">
                    <div className="text-xs text-slate-300">Revenue (Week)</div>
                    <div className="mt-1 text-2xl font-bold text-white">$28.4k</div>
                    <div className="mt-2 text-xs text-slate-300">Estimated</div>
                  </div>
                  <div className="rounded-2xl bg-white/5 p-4">
                    <div className="text-xs text-slate-300">Alerts</div>
                    <div className="mt-1 text-2xl font-bold text-white">3</div>
                    <div className="mt-2 text-xs text-amber-300">Docs due</div>
                  </div>
                </div>

                <div className="mt-4 rounded-2xl border border-white/10 bg-gradient-to-r from-blue-600/20 to-indigo-600/20 p-4">
                  <div className="text-sm font-semibold text-white">Next up</div>
                  <div className="mt-1 text-sm text-slate-200">
                    Complete company profile to unlock the full dashboard.
                  </div>
                  <div className="mt-3 flex gap-2">
                    <Link
                      to="/signup"
                      className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-100 transition"
                    >
                      Start
                    </Link>
                    <a
                      href="#how"
                      className="rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10 transition"
                    >
                      How it works
                    </a>
                  </div>
                </div>
              </div>

              <div className="mt-5 grid grid-cols-3 gap-3 text-center">
                <div className="rounded-2xl bg-white/5 p-3">
                  <div className="mx-auto w-fit text-blue-300">
                    <Shield />
                  </div>
                  <div className="mt-2 text-xs font-semibold text-white">Secure</div>
                  <div className="text-[11px] text-slate-300">Tenant-safe</div>
                </div>
                <div className="rounded-2xl bg-white/5 p-3">
                  <div className="mx-auto w-fit text-indigo-300">
                    <Users />
                  </div>
                  <div className="mt-2 text-xs font-semibold text-white">Teams</div>
                  <div className="text-[11px] text-slate-300">Admin roles</div>
                </div>
                <div className="rounded-2xl bg-white/5 p-3">
                  <div className="mx-auto w-fit text-cyan-300">
                    <Chart />
                  </div>
                  <div className="mt-2 text-xs font-semibold text-white">KPIs</div>
                  <div className="text-[11px] text-slate-300">Real-time</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="features" className="mx-auto max-w-6xl px-6 pb-14">
          <div className="flex items-end justify-between gap-6">
            <div>
              <h2 className="text-2xl font-bold text-white">Built for real trucking operations</h2>
              <p className="mt-2 text-sm text-slate-200">
                A single system covering dispatch, drivers, payroll, docs, and reporting.
              </p>
            </div>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <FeatureCard
              title="Dispatch Dashboard"
              desc="Active loads, drivers on duty, ETA visibility, alerts, and daily execution KPIs."
              icon={<Truck />}
            />
            <FeatureCard
              title="Driver Onboarding"
              desc="Optional uploads at submission, required-vs-missing docs, and admin approval before finalizing data."
              icon={<Users />}
            />
            <FeatureCard
              title="Payroll & Pay Runs"
              desc="Pay periods, pay entries, overrides, deductions, and pay run exports — designed to scale."
              icon={<Chart />}
            />
            <FeatureCard
              title="Compliance & Documents"
              desc="CDL/medical/TWIC reminders, document lifecycle, and audit-friendly history."
              icon={<Shield />}
            />
          </div>
        </section>

        <section id="how" className="mx-auto max-w-6xl px-6 pb-14">
          <div className="rounded-3xl border border-white/10 bg-white/5 p-8 backdrop-blur">
            <h2 className="text-2xl font-bold text-white">How it works</h2>
            <p className="mt-2 text-sm text-slate-200">
              Simple setup, then you’re ready to run dispatch and operations.
            </p>

            <div className="mt-6 grid gap-6 md:grid-cols-3">
              <Step
                num="1"
                title="Create your workspace"
                desc="Choose a company slug (your subdomain) and verify your email."
              />
              <Step
                num="2"
                title="Complete company profile"
                desc="Finish onboarding to unlock dashboard access and operational modules."
              />
              <Step
                num="3"
                title="Start dispatching"
                desc="Add drivers, loads, and track KPIs with tenant-safe data isolation."
              />
            </div>

            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <Link
                to="/signup"
                className="inline-flex items-center justify-center rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-3 text-sm font-semibold text-white hover:opacity-95 transition"
              >
                Get started
              </Link>
              <Link
                to="/login"
                className="inline-flex items-center justify-center rounded-xl border border-white/15 bg-white/5 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10 transition"
              >
                Login
              </Link>
            </div>
          </div>
        </section>

        <section id="pricing" className="mx-auto max-w-6xl px-6 pb-16">
          <h2 className="text-2xl font-bold text-white">Pricing</h2>
          <p className="mt-2 text-sm text-slate-200">
            Package identity is fixed (trial, basic, pro, enterprise); pricing is configured in admin.
          </p>

          <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
              <div className="text-sm font-semibold text-white">Free trial</div>
              <div className="mt-2 text-3xl font-extrabold text-white">$0</div>
              <div className="mt-1 text-xs text-slate-300">Evaluation</div>
              <ul className="mt-4 space-y-2 text-sm text-slate-200">
                <li className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Core dashboard
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Driver onboarding
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Document uploads
                </li>
              </ul>
              <Link
                to="/workspace-intake?package=FREE_TRIAL"
                className="mt-5 inline-flex w-full items-center justify-center rounded-xl bg-white px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-100 transition"
              >
                Start free trial
              </Link>
            </div>

            <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
              <div className="text-sm font-semibold text-white">Basic</div>
              <div className="mt-2 text-3xl font-extrabold text-white">—</div>
              <div className="mt-1 text-xs text-slate-300">Small fleet essentials</div>
              <ul className="mt-4 space-y-2 text-sm text-slate-200">
                <li className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Operations workflows
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Team roles
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Email support
                </li>
              </ul>
              <Link
                to="/workspace-intake?package=BASIC"
                className="mt-5 inline-flex w-full items-center justify-center rounded-xl border border-white/15 bg-white/10 px-4 py-2 text-sm font-semibold text-white hover:bg-white/15 transition"
              >
                Choose Basic
              </Link>
            </div>

            <div className="rounded-3xl border border-blue-400/30 bg-gradient-to-b from-blue-600/20 to-indigo-600/10 p-6 shadow-xl">
              <div className="text-sm font-semibold text-white">Pro</div>
              <div className="mt-2 text-3xl font-extrabold text-white">—</div>
              <div className="mt-1 text-xs text-slate-200">Growing fleets</div>
              <ul className="mt-4 space-y-2 text-sm text-slate-100">
                <li className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Dispatch KPIs + loads
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Payroll pay runs
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Alerts & reminders
                </li>
              </ul>
              <Link
                to="/workspace-intake?package=PRO"
                className="mt-5 inline-flex w-full items-center justify-center rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:opacity-95 transition"
              >
                Choose Pro
              </Link>
            </div>

            <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
              <div className="text-sm font-semibold text-white">Enterprise</div>
              <div className="mt-2 text-3xl font-extrabold text-white">Custom</div>
              <div className="mt-1 text-xs text-slate-300">Multi-company, advanced needs</div>
              <ul className="mt-4 space-y-2 text-sm text-slate-200">
                <li className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Dedicated support
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Custom integrations
                </li>
                <li className="flex items-center gap-2">
                  <span className="text-emerald-300">
                    <Check />
                  </span>
                  Advanced security
                </li>
              </ul>
              <Link
                to="/workspace-intake?package=ENTERPRISE"
                className="mt-5 inline-flex w-full items-center justify-center rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-sm font-semibold text-white hover:bg-white/10 transition"
              >
                Choose Enterprise
              </Link>
            </div>
          </div>
        </section>

        <footer className="border-t border-white/10 bg-slate-950/60">
          <div className="mx-auto max-w-6xl px-6 py-10">
            <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
              <div className="text-sm text-slate-300">
                © {new Date().getFullYear()} Trucking ERP • All rights reserved.
              </div>
              <div className="flex gap-4 text-sm">
                <a href="#features" className="text-slate-300 hover:text-white">
                  Features
                </a>
                <a href="#how" className="text-slate-300 hover:text-white">
                  How it works
                </a>
                <a href="#pricing" className="text-slate-300 hover:text-white">
                  Pricing
                </a>
              </div>
            </div>
            <div className="mt-6 text-xs text-slate-400">
              Platform DB is control-plane only. Tenant DB holds business data. Tenant routing is registry-driven.
            </div>
          </div>
        </footer>
      </main>
    </div>
  );
}

export default LandingPage;
