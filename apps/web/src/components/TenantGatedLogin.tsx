import React, { useEffect, useState } from "react";
import { getTenantStatus } from "../api";
import { getTenantSlugFromHost } from "../tenant";
import { WorkspaceNotFoundView } from "./WorkspaceNotFoundView";
import LoginPage from "../pages/LoginPage";

/**
 * When the user is on a tenant subdomain (e.g. demo.truckerp.me/login), verify the workspace exists.
 * If it does not exist, show "Workspace not found" with links to main site and signup.
 */
export function TenantGatedLogin() {
  const slug = getTenantSlugFromHost();
  const [state, setState] = useState<"idle" | "checking" | "exists" | "not_found" | "error">(slug ? "checking" : "exists");

  useEffect(() => {
    if (!slug) {
      setState("exists");
      return;
    }
    let cancelled = false;
    getTenantStatus(slug)
      .then((s) => {
        if (cancelled) return;
        setState(s.exists ? "exists" : "not_found");
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (!slug) return <LoginPage />;
  if (state === "checking") {
    return (
      <div className="trk-auth">
        <div className="trk-auth-wrap flex items-center justify-center min-h-[200px]">
          <p className="text-slate-400">Checking workspace…</p>
        </div>
      </div>
    );
  }
  if (state === "not_found") return <WorkspaceNotFoundView slug={slug} />;
  if (state === "error") {
    return (
      <div className="trk-auth">
        <div className="trk-auth-wrap">
          <div className="trk-card">
            <h2>Something went wrong</h2>
            <p className="trk-foot">We couldn’t verify this workspace. Try again later or use the main site.</p>
            <a href="https://truckerp.me" className="trk-primary block w-full text-center py-2 mt-4">
              Go to main site
            </a>
          </div>
        </div>
      </div>
    );
  }
  return <LoginPage />;
}
