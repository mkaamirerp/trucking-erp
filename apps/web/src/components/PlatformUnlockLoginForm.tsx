import { useCallback, useEffect, useState } from "react";
import {
  getPlatformAdminApiKey,
  platformAdminJson,
  PlatformAdminHttpError,
  PlatformAdminUnauthorizedError,
} from "../lib/platformAdminFetch";
import { signalPlatformAdminUnauthorized } from "./PlatformShellLayout";

export type UnlockResponse = {
  tenant_id: number;
  tenant_slug: string;
  email_norm: string;
  cleared: {
    platform_login_password_fail_streaks: { rows_deleted: number };
    rate_limiters: Record<string, { key: string; had_entries: boolean }>;
  };
  state_after?: LoginLockStateBundle;
  note: string;
};

type RateLimitSnap = { key: string; at_limit: boolean; retry_after_seconds: number };

type LoginLockStateBundle = {
  password_fail_streak: {
    has_active_window: boolean;
    streak_count: number;
    turnstile_armed: boolean;
    otp_step_up_armed: boolean;
    window_started_at: string | null;
    window_expires_at: string | null;
  };
  tenant_email_rate_limits: Record<string, RateLimitSnap>;
  overall: {
    tenant_email_login_bucket_blocked: boolean;
    tenant_email_step_up_bucket_blocked: boolean;
    any_tenant_email_rate_bucket_blocked: boolean;
    password_fail_streak_failures_in_window: number;
    password_abuse_extra_friction_active: boolean;
    all_clear_for_tenant_email_unlock_tool: boolean;
  };
};

type LockStatusResponse = {
  tenant_id: number;
  tenant_slug: string;
  email_norm: string;
  state: LoginLockStateBundle;
  note: string;
};

function formatRetry(sec: number): string {
  if (sec <= 0) return "";
  if (sec < 120) return `${sec}s`;
  const m = Math.ceil(sec / 60);
  return `~${m} min`;
}

type Props = {
  /** Compact layout for platform home; full page adds more chrome in parent. */
  compact?: boolean;
  /** Pre-fill slug (e.g. from platform tenant detail). Updates when this prop changes. */
  initialTenantSlug?: string;
  /** If true, tenant slug cannot be edited (this workspace only). */
  lockTenantSlug?: boolean;
};

export default function PlatformUnlockLoginForm({
  compact = false,
  initialTenantSlug,
  lockTenantSlug = false,
}: Props) {
  const [tenantSlug, setTenantSlug] = useState(() => (initialTenantSlug?.trim() ? initialTenantSlug.trim() : "demo"));

  useEffect(() => {
    const s = initialTenantSlug?.trim();
    if (s) setTenantSlug(s);
  }, [initialTenantSlug]);
  const [email, setEmail] = useState("");
  const [result, setResult] = useState<UnlockResponse | null>(null);
  const [lockState, setLockState] = useState<LoginLockStateBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [statusBusy, setStatusBusy] = useState(false);

  const runCheckStatus = useCallback(async () => {
    setError(null);
    setLockState(null);
    if (!getPlatformAdminApiKey().trim()) {
      signalPlatformAdminUnauthorized();
      setError("Save a platform admin key in the header first.");
      return;
    }
    const slug = tenantSlug.trim().toLowerCase();
    const em = email.trim();
    if (!slug || !em) {
      setError("Tenant slug and email are required.");
      return;
    }
    setStatusBusy(true);
    try {
      const data = await platformAdminJson<LockStatusResponse>("/platform/testing/login-lock-status", {
        method: "POST",
        body: JSON.stringify({ tenant_slug: slug, email: em }),
      });
      setLockState(data.state);
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        return;
      }
      if (e instanceof PlatformAdminHttpError) {
        setError(e.message);
        return;
      }
      setError("Request failed");
    } finally {
      setStatusBusy(false);
    }
  }, [tenantSlug, email]);

  const submit = useCallback(async () => {
    setError(null);
    setResult(null);
    if (!getPlatformAdminApiKey().trim()) {
      signalPlatformAdminUnauthorized();
      setError("Save a platform admin key in the header first.");
      return;
    }
    const slug = tenantSlug.trim().toLowerCase();
    const em = email.trim();
    if (!slug || !em) {
      setError("Tenant slug and email are required.");
      return;
    }
    setBusy(true);
    try {
      const data = await platformAdminJson<UnlockResponse>("/platform/testing/unlock-login", {
        method: "POST",
        body: JSON.stringify({ tenant_slug: slug, email: em }),
      });
      setResult(data);
    } catch (e) {
      if (e instanceof PlatformAdminUnauthorizedError) {
        signalPlatformAdminUnauthorized();
        return;
      }
      if (e instanceof PlatformAdminHttpError) {
        setError(e.message);
        return;
      }
      setError("Request failed");
    } finally {
      setBusy(false);
    }
  }, [tenantSlug, email]);

  const renderStatePanel = (state: LoginLockStateBundle, title: string) => {
    const o = state.overall;
    const loginMeta = state.tenant_email_rate_limits["login_per_tenant_email"];
    const issueMeta = state.tenant_email_rate_limits["login_step_up_issue_per_tenant_email"];
    const verifyMeta = state.tenant_email_rate_limits["login_step_up_verify_per_tenant_email"];
    const streak = state.password_fail_streak;

    return (
      <div
        className={`rounded-lg border text-sm space-y-2 ${
          o.all_clear_for_tenant_email_unlock_tool
            ? "border-emerald-900/50 bg-emerald-950/25 text-emerald-100"
            : "border-amber-900/50 bg-amber-950/30 text-amber-100"
        } ${compact ? "p-3" : "p-4"}`}
      >
        <p className={`font-medium text-white ${compact ? "text-xs" : "text-sm"}`}>{title}</p>
        {o.all_clear_for_tenant_email_unlock_tool ? (
          <p className={compact ? "text-xs" : "text-sm"}>
            <strong className="text-emerald-200">Clear</strong> — no active password-fail streak and no tenant+email
            login / step-up rate buckets full on this API instance.
          </p>
        ) : (
          <ul className={`list-disc list-inside space-y-1 ${compact ? "text-xs" : "text-sm"}`}>
            {o.tenant_email_login_bucket_blocked && loginMeta ? (
              <li>
                <strong>Login attempts limited</strong> for this workspace+email
                {loginMeta.retry_after_seconds > 0 ? ` (retry in ${formatRetry(loginMeta.retry_after_seconds)})` : ""}.
              </li>
            ) : null}
            {o.tenant_email_step_up_bucket_blocked ? (
              <li>
                <strong>OTP step-up path limited</strong>
                {issueMeta?.at_limit && issueMeta.retry_after_seconds > 0
                  ? ` (issue: ${formatRetry(issueMeta.retry_after_seconds)})`
                  : ""}
                {verifyMeta?.at_limit && verifyMeta.retry_after_seconds > 0
                  ? ` (verify: ${formatRetry(verifyMeta.retry_after_seconds)})`
                  : ""}
                .
              </li>
            ) : null}
            {streak.has_active_window && streak.streak_count > 0 ? (
              <li>
                <strong>Password fail streak</strong> in rolling window: {streak.streak_count} failure
                {streak.streak_count === 1 ? "" : "s"}
                {streak.turnstile_armed ? " · extra verification may be required before password check" : ""}
                {streak.otp_step_up_armed ? " · correct password may still require email OTP step-up" : ""}.
              </li>
            ) : null}
            {o.password_abuse_extra_friction_active && !(streak.has_active_window && streak.streak_count > 0) ? (
              <li>Abuse friction flags may still apply — check streak details in API state.</li>
            ) : null}
          </ul>
        )}
        <p className="text-slate-500 text-[10px] pt-1">
          IP-wide login throttle is not shown. Other app replicas may hold different in-memory buckets.
        </p>
      </div>
    );
  };

  return (
    <div className={compact ? "space-y-3" : "space-y-6 max-w-xl"}>
      {!compact ? (
        <>
          <p className="mt-1 text-sm text-slate-400">
            Clears password-fail streak and tenant+email login / step-up rate buckets for one user. Does not change
            passwords or OTP configuration.
          </p>
          <p className="mt-3 rounded border border-amber-900/50 bg-amber-950/30 px-3 py-2 text-sm text-amber-100">
            <strong>IP throttle not cleared.</strong> If the user still hits &quot;too many attempts from this
            network&quot;, wait ~15 minutes or try another connection — this tool only resets workspace+email buckets,
            not <code className="text-amber-200/90">login_per_ip</code>.
          </p>
        </>
      ) : (
        <p className="rounded border border-amber-900/50 bg-amber-950/30 px-2 py-1.5 text-xs text-amber-100">
          <strong>IP throttle not cleared</strong> — only tenant+email buckets;{" "}
          <code className="text-amber-200/90">login_per_ip</code> unchanged.
        </p>
      )}

      <div className={`rounded-lg border border-slate-800 bg-slate-900/50 ${compact ? "p-3" : "p-4"} space-y-3`}>
        <div className={`flex flex-col ${compact ? "sm:flex-row sm:items-end sm:gap-2" : ""} gap-2`}>
          <label className={`block text-xs text-slate-400 ${compact ? "sm:flex-1 min-w-0" : ""}`}>
            Tenant slug
            <input
              className={`mt-1 w-full rounded border border-slate-700 px-2 py-1.5 text-sm text-white ${
                lockTenantSlug ? "cursor-not-allowed bg-slate-950/60 text-slate-300" : "bg-slate-900"
              }`}
              value={tenantSlug}
              onChange={(e) => !lockTenantSlug && setTenantSlug(e.target.value)}
              readOnly={lockTenantSlug}
              placeholder="demo"
            />
          </label>
          <label className={`block text-xs text-slate-400 ${compact ? "sm:flex-[2] min-w-0" : ""}`}>
            User email
            <input
              type="email"
              className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-white"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@example.com"
            />
          </label>
        </div>
        <div className={`flex flex-wrap gap-2 ${compact ? "" : ""}`}>
          <button
            type="button"
            disabled={statusBusy}
            onClick={() => void runCheckStatus()}
            className="rounded border border-slate-600 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-slate-700 disabled:opacity-50"
          >
            {statusBusy ? "Checking…" : "Check lock state"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void submit()}
            className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {busy ? "Unlocking…" : "Unlock login"}
          </button>
        </div>
      </div>

      {lockState ? renderStatePanel(lockState, "Lock state (this workspace + email)") : null}

      {error ? (
        <div className="rounded border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-200">{error}</div>
      ) : null}

      {result ? (
        <div
          className={`rounded-lg border border-slate-700 bg-slate-900/80 text-sm text-slate-200 space-y-2 ${
            compact ? "p-3" : "p-4"
          }`}
        >
          <p className={compact ? "text-xs" : ""}>
            <span className="text-slate-400">Tenant:</span> {result.tenant_slug} ({result.tenant_id}) ·{" "}
            <span className="text-slate-400">Email:</span> {result.email_norm}
          </p>
          <p className="text-slate-400 text-xs">Cleared:</p>
          <ul className={`list-disc list-inside text-slate-300 space-y-1 ${compact ? "text-xs" : ""}`}>
            <li>
              <code className="text-slate-200">platform_login_password_fail_streaks</code> rows:{" "}
              {result.cleared.platform_login_password_fail_streaks.rows_deleted}
            </li>
            {Object.entries(result.cleared.rate_limiters).map(([name, meta]) => (
              <li key={name}>
                <code className="text-slate-200">{name}</code> had entries: {String(meta.had_entries)}
              </li>
            ))}
          </ul>
          {result.state_after ? (
            <div className="pt-2 border-t border-slate-700">
              {renderStatePanel(result.state_after, "After unlock")}
            </div>
          ) : null}
          <p className="text-slate-400 text-xs pt-1">{result.note}</p>
        </div>
      ) : null}
    </div>
  );
}
