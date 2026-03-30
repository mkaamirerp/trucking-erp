import type { ReactNode } from "react";
import { getTenantSlugFromHost } from "../tenant";

/**
 * Control-plane UI must not render on workspace subdomains (avoid mixing with tenant UX).
 */
export default function PlatformApexGate({ children }: { children: ReactNode }) {
  const slug = getTenantSlugFromHost();
  if (slug) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 px-4 py-12">
        <div className="max-w-lg mx-auto rounded-lg border border-slate-800 bg-slate-900/60 p-6">
          <h1 className="text-lg font-semibold text-white">Platform tools unavailable here</h1>
          <p className="mt-2 text-sm text-slate-400">
            Open the control plane from the main site (apex), not from a workspace URL like{" "}
            <span className="text-slate-300">{slug}.…</span>
          </p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
