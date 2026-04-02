import { useCallback, useEffect, useState } from "react";
import {
  getTenantUserSignInSecurity,
  unlockTenantUserSignIn,
  type SignInSecurity,
  type UserMember,
} from "../api";

type Props = {
  user: UserMember | null;
  open: boolean;
  onClose: () => void;
  canUnlock: boolean;
  onAfterUnlock: () => void;
};

function formatActivity(value: string | null | undefined): string {
  if (value == null || String(value).trim() === "") return "Not available";
  return String(value);
}

export default function AdminUserDetailDrawer({ user, open, onClose, canUnlock, onAfterUnlock }: Props) {
  const [sec, setSec] = useState<SignInSecurity | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [unlockBusy, setUnlockBusy] = useState(false);
  const [unlockOk, setUnlockOk] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!user) return;
    setErr(null);
    setUnlockOk(null);
    setLoading(true);
    try {
      const data = await getTenantUserSignInSecurity(user.user_id);
      setSec(data);
    } catch (e) {
      setSec(null);
      setErr(e instanceof Error ? e.message : "Could not load sign-in information.");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (open && user) void load();
    if (!open) {
      setSec(null);
      setErr(null);
      setUnlockOk(null);
    }
  }, [open, user, load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const doUnlock = async () => {
    if (!user) return;
    setUnlockBusy(true);
    setErr(null);
    setUnlockOk(null);
    try {
      const data = await unlockTenantUserSignIn(user.user_id);
      setUnlockOk(
        data.operator_message?.trim() ||
          "Sign-in limits were cleared for this account. If they still cannot sign in, wait a little, try again, or use a different internet connection.",
      );
      await load();
      onAfterUnlock();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Unlock did not complete.");
    } finally {
      setUnlockBusy(false);
    }
  };

  if (!open || !user) return null;

  const st = (user.membership_status || "").toLowerCase();
  const canShowUnlock = canUnlock && (st === "active" || st === "invited") && sec && !sec.all_clear;

  const rs = sec?.restriction_summary as Record<string, unknown> | undefined;
  const lim = (at: unknown) => (at === true ? "At limit" : "Not at limit");
  const pwdAtLimit = rs?.wrong_password_attempts_at_limit === true;
  const pwdLine = pwdAtLimit ? "At limit" : "0";

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-40 bg-black/60"
        aria-label="Close user details"
        onClick={onClose}
      />
      <aside
        className="fixed right-0 top-0 z-50 h-full w-full max-w-md overflow-y-auto border-l border-[#334155] bg-[#0a0e14] p-6 text-[#e8edf5] shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-user-detail-title"
      >
        <div className="flex items-start justify-between gap-4">
          <h2 id="admin-user-detail-title" className="font-['Barlow_Condensed'] text-2xl font-bold">
            {user.username}
          </h2>
          <button type="button" onClick={onClose} className="shrink-0 text-sm text-[#94a3b8] hover:text-white">
            Close
          </button>
        </div>
        <p className="mt-1 text-sm text-[#64748b]">{user.email}</p>
        {user.phone ? <p className="text-sm text-[#94a3b8]">{user.phone}</p> : null}

        <dl className="mt-6 space-y-3 text-sm">
          <div>
            <dt className="text-xs uppercase tracking-wider text-[#64748b]">Membership status</dt>
            <dd className="mt-1 capitalize text-[#e8edf5]">{user.membership_status}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wider text-[#64748b]">Access level</dt>
            <dd className="mt-1 text-[#e8edf5]">{user.access_level}</dd>
          </div>
        </dl>

        <section className="mt-8 rounded-lg border border-[#334155] bg-[#0f172a]/50 p-4">
          <h3 className="text-sm font-semibold text-[#e8edf5]">Sign-in Security</h3>
          <p className="mt-1 text-xs text-[#64748b]">
            Account status (such as Active) is separate from sign-in protection shown below.
          </p>

          {loading ? <p className="mt-4 text-sm text-[#94a3b8]">Loading…</p> : null}
          {err ? <p className="mt-4 text-sm whitespace-pre-wrap text-red-400">{err}</p> : null}
          {unlockOk ? <p className="mt-4 text-sm text-emerald-400">{unlockOk}</p> : null}

          {sec && !loading ? (
            <div className="mt-4 space-y-4 text-sm">
              <div>
                <span className="text-xs uppercase tracking-wider text-[#64748b]">Sign-in status</span>
                <p className="mt-1">
                  <span
                    className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${
                      sec.sign_in_status === "clear"
                        ? "bg-emerald-900/40 text-emerald-400"
                        : sec.sign_in_status === "verification_on_next_sign_in"
                          ? "bg-amber-900/40 text-amber-200"
                          : "bg-rose-900/40 text-rose-300"
                    }`}
                  >
                    {sec.sign_in_status === "clear"
                      ? "No lock"
                      : sec.sign_in_status === "verification_on_next_sign_in"
                        ? "Code on next sign-in"
                        : "Locked"}
                  </span>
                </p>
              </div>

              {sec.reasons.length > 0 ? (
                <div>
                  <span className="text-xs uppercase tracking-wider text-[#64748b]">Why sign-in was blocked</span>
                  <ul className="mt-2 list-disc space-y-1 pl-4 text-[#cbd5e1]">
                    {sec.reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
              ) : sec.sign_in_status === "verification_on_next_sign_in" ? (
                <p className="text-[#cbd5e1]">
                  Limits are cleared. The user will be asked for a verification email code the next time they sign
                  in; after that they can trust their browser to skip the code on that device.
                </p>
              ) : sec.all_clear ? (
                <p className="text-[#94a3b8]">There is no user-specific sign-in lock on this account right now.</p>
              ) : null}

              {rs && typeof rs === "object" ? (
                <div>
                  <span className="text-xs uppercase tracking-wider text-[#64748b]">Current sign-in checks</span>
                  <ul className="mt-2 space-y-2 text-[#cbd5e1]">
                    <li>
                      <span className="text-[#94a3b8]">Wrong password attempts: </span>
                      <span className="font-medium text-[#e8edf5]">{pwdLine}</span>
                    </li>
                    <li>
                      <span className="text-[#94a3b8]">Workspace sign-in limit: </span>
                      <span className="font-medium text-[#e8edf5]">
                        {lim(rs.workspace_email_login_at_limit)}
                      </span>
                    </li>
                    <li>
                      <span className="text-[#94a3b8]">OTP request limit: </span>
                      <span className="font-medium text-[#e8edf5]">
                        {lim(rs.workspace_step_up_issue_at_limit)}
                      </span>
                    </li>
                    <li>
                      <span className="text-[#94a3b8]">OTP verification limit: </span>
                      <span className="font-medium text-[#e8edf5]">
                        {lim(rs.workspace_step_up_verify_at_limit)}
                      </span>
                    </li>
                  </ul>
                </div>
              ) : null}

              <div>
                <span className="text-xs uppercase tracking-wider text-[#64748b]">Recent activity</span>
                <ul className="mt-2 space-y-2 text-[#cbd5e1]">
                  <li>
                    <span className="text-[#94a3b8]">Lock started: </span>
                    <span className="text-[#e8edf5]">{formatActivity(sec.timestamps.streak_window_started_at)}</span>
                  </li>
                  <li>
                    <span className="text-[#94a3b8]">Lock may clear after: </span>
                    <span className="text-[#e8edf5]">{formatActivity(sec.timestamps.streak_window_expires_at)}</span>
                  </li>
                  <li>
                    <span className="text-[#94a3b8]">Last failed password activity: </span>
                    <span className="text-[#e8edf5]">{formatActivity(sec.timestamps.last_streak_activity_at)}</span>
                  </li>
                </ul>
              </div>

              {typeof sec.lock_scope?.ip_based_note === "string" && sec.lock_scope.ip_based_note.trim() !== "" ? (
                <div className="rounded border border-amber-900/40 bg-amber-950/20 p-3 text-xs leading-relaxed text-amber-100/95">
                  {sec.lock_scope.ip_based_note}
                </div>
              ) : null}

              {canShowUnlock ? (
                <div className="space-y-2 border-t border-[#334155] pt-4">
                  <button
                    type="button"
                    disabled={unlockBusy}
                    onClick={() => void doUnlock()}
                    className="w-full rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                  >
                    {unlockBusy ? "Unlocking…" : "Unlock sign-in"}
                  </button>
                  <p className="text-center text-xs text-[#64748b]">
                    Clears workspace limits for this account. The user will verify by email on their next sign-in,
                    then can choose to trust their device again.
                  </p>
                </div>
              ) : null}

              {st === "suspended" ? (
                <p className="text-xs leading-relaxed text-amber-400/90">
                  This user is suspended. Restore access with Reactivate before sign-in can work normally.
                </p>
              ) : null}
            </div>
          ) : null}
        </section>
      </aside>
    </>
  );
}
