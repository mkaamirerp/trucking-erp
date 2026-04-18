import { useEffect, useState } from "react";
import {
  listTenantUsers,
  inviteTenantUser,
  suspendTenantUser,
  reactivateTenantUser,
  resendTenantUserInvite,
  removeTenantUserFromWorkspace,
  UserMember,
  InviteUserPayload,
} from "../api";
import AdminUserDetailDrawer from "../components/AdminUserDetailDrawer";
import { useMe, hasFullAccess } from "../hooks/useMe";

export default function AdminUsersPage() {
  const { me } = useMe();
  const canInvite = hasFullAccess(me?.roles ?? []);
  const [users, setUsers] = useState<UserMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inviteUsername, setInviteUsername] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [invitePhone, setInvitePhone] = useState("");
  const [inviteAccessLevel, setInviteAccessLevel] = useState("READ_ONLY");
  const [inviteSubmitting, setInviteSubmitting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteSuccess, setInviteSuccess] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [detailUser, setDetailUser] = useState<UserMember | null>(null);

  const loadUsers = () => {
    listTenantUsers()
      .then(setUsers)
      .catch((err) => setError(err?.message || "Failed to load users"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteError(null);
    setInviteSuccess(null);
    if (!inviteEmail.trim() || !inviteUsername.trim()) {
      setInviteError("Username and email are required");
      return;
    }
    setInviteSubmitting(true);
    try {
      const payload: InviteUserPayload = {
        username: inviteUsername.trim(),
        email: inviteEmail.trim().toLowerCase(),
        phone: invitePhone.trim() || undefined,
        access_level: inviteAccessLevel,
      };
      const inv = await inviteTenantUser(payload);
      if (inv.email_sent === false) {
        setInviteSuccess(`${inv.message} (${inviteEmail})`);
      } else {
        setInviteSuccess(
          inv.message?.includes("again") ? `${inv.message} (${inviteEmail})` : `Invite sent to ${inviteEmail}`,
        );
      }
      setInviteUsername("");
      setInviteEmail("");
      setInvitePhone("");
      loadUsers();
    } catch (err) {
      setInviteError(err instanceof Error ? err.message : "Invite failed");
    } finally {
      setInviteSubmitting(false);
    }
  };

  const handleSuspend = async (userId: string) => {
    setActionLoading(userId);
    try {
      await suspendTenantUser(userId);
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to suspend");
    } finally {
      setActionLoading(null);
    }
  };

  const handleReactivate = async (userId: string) => {
    setActionLoading(userId);
    try {
      await reactivateTenantUser(userId);
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reactivate");
    } finally {
      setActionLoading(null);
    }
  };

  const handleResendInvite = async (userId: string, email: string) => {
    setInviteError(null);
    setInviteSuccess(null);
    setActionLoading(userId);
    try {
      const inv = await resendTenantUserInvite(userId);
      setInviteSuccess(inv.email_sent === false ? inv.message : `Invite resent to ${email}`);
      loadUsers();
    } catch (err) {
      setInviteError(err instanceof Error ? err.message : "Resend failed");
    } finally {
      setActionLoading(null);
    }
  };

  const handleRemoveFromWorkspace = async (userId: string, label: string) => {
    if (!window.confirm(`Remove ${label} from this workspace? You can invite them again afterward.`)) {
      return;
    }
    setInviteError(null);
    setInviteSuccess(null);
    setActionLoading(userId);
    try {
      await removeTenantUserFromWorkspace(userId);
      setInviteSuccess(`${label} was removed from this workspace.`);
      if (detailUser?.user_id === userId) setDetailUser(null);
      loadUsers();
    } catch (err) {
      setInviteError(err instanceof Error ? err.message : "Remove failed");
    } finally {
      setActionLoading(null);
    }
  };

  if (loading && users.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-[var(--trk-text-muted)]">Loading users...</div>
    );
  }

  return (
    <div className="space-y-8">
      <h1 className="font-['Barlow_Condensed'] text-3xl font-bold tracking-tight text-[var(--trk-text)]">Users</h1>
      <p className="text-sm text-[var(--trk-text-muted)] -mt-4">
        Click a user&apos;s name or row to open details and sign-in security.
      </p>

      {error && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-4 text-red-400">{error}</div>
      )}

      <AdminUserDetailDrawer
        user={detailUser}
        open={detailUser !== null}
        onClose={() => setDetailUser(null)}
        canUnlock={canInvite}
        onAfterUnlock={() => loadUsers()}
      />

      <div className={`rounded-xl border border-[var(--trk-border-strong)] bg-[var(--trk-bg)]/50 p-6 ${!canInvite ? "opacity-60" : ""}`}>
        <h2 className="mb-4 text-lg font-semibold text-[var(--trk-text)]">
          Invite user
          {!canInvite && (
            <span className="ml-2 text-sm font-normal text-[var(--trk-text-muted)]">(Read-only: invite disabled)</span>
          )}
        </h2>
        <form onSubmit={handleInvite} className="space-y-4">
          {inviteError && (
            <div className="rounded border border-red-800/50 bg-red-950/30 p-3 text-sm text-red-400">{inviteError}</div>
          )}
          {inviteSuccess && (
            <div className="rounded border border-emerald-800/50 bg-emerald-950/30 p-3 text-sm text-emerald-400">
              {inviteSuccess}
            </div>
          )}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">
                Username
              </label>
              <input
                type="text"
                required
                disabled={!canInvite}
                value={inviteUsername}
                onChange={(e) => setInviteUsername(e.target.value)}
                className="w-full rounded-lg border border-[var(--trk-border-strong)] bg-[#0f172a] px-3 py-2 text-[var(--trk-text)] placeholder-[var(--trk-text-muted)] focus:border-[var(--trk-text-muted)] focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
                placeholder="Display name"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">Email</label>
              <input
                type="email"
                required
                disabled={!canInvite}
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="w-full rounded-lg border border-[var(--trk-border-strong)] bg-[#0f172a] px-3 py-2 text-[var(--trk-text)] placeholder-[var(--trk-text-muted)] focus:border-[var(--trk-text-muted)] focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
                placeholder="user@company.com"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">Phone</label>
              <input
                type="tel"
                disabled={!canInvite}
                value={invitePhone}
                onChange={(e) => setInvitePhone(e.target.value)}
                className="w-full rounded-lg border border-[var(--trk-border-strong)] bg-[#0f172a] px-3 py-2 text-[var(--trk-text)] placeholder-[var(--trk-text-muted)] focus:border-[var(--trk-text-muted)] focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
                placeholder="+1 (optional)"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">
                Access level
              </label>
              <select
                value={inviteAccessLevel}
                onChange={(e) => setInviteAccessLevel(e.target.value)}
                disabled={!canInvite}
                className="w-full rounded-lg border border-[var(--trk-border-strong)] bg-[#0f172a] px-3 py-2 text-[var(--trk-text)] focus:border-[var(--trk-text-muted)] focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              >
                <option value="READ_ONLY">Read only</option>
                <option value="FULL_ACCESS">Full access</option>
              </select>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <button
              type="submit"
              disabled={inviteSubmitting || !canInvite}
              className="rounded-lg bg-[#3b82f6] px-4 py-2 font-medium text-white hover:bg-[#2563eb] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {inviteSubmitting ? "Sending..." : "Send invite"}
            </button>
          </div>
        </form>
      </div>

      <div className="overflow-hidden rounded-xl border border-[var(--trk-border-strong)] bg-[var(--trk-bg)]/50">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[var(--trk-border-strong)] bg-[#0f172a]/80">
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">
                Username
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">
                Email
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">
                Phone
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">
                Access
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">
                Status
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--trk-border-strong)]">
            {users.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-[var(--trk-text-muted)]">
                  No users yet. Invite someone to get started.
                </td>
              </tr>
            ) : (
              users.map((u) => {
                const st = (u.membership_status || "").toLowerCase();
                return (
                  <tr
                    key={u.user_id}
                    className="cursor-pointer hover:bg-[#0f172a]/30"
                    onClick={() => setDetailUser(u)}
                    title="View user details"
                  >
                    <td className="px-4 py-3 font-medium text-[var(--trk-text)]">{u.username}</td>
                    <td className="px-4 py-3 text-[var(--trk-text-muted)]">{u.email}</td>
                    <td className="px-4 py-3 text-[var(--trk-text-muted)]">{u.phone ?? "—"}</td>
                    <td className="px-4 py-3 text-[var(--trk-text-muted)]">{u.access_level}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex w-fit rounded px-2 py-0.5 text-xs font-medium ${
                          st === "active"
                            ? "bg-emerald-900/40 text-emerald-400"
                            : st === "suspended"
                              ? "bg-amber-900/40 text-amber-400"
                              : "bg-[var(--trk-border-strong)] text-[var(--trk-text-muted)]"
                        }`}
                      >
                        {u.membership_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                      {canInvite && (
                        <div className="flex flex-wrap justify-end gap-2">
                          {st === "invited" && (
                            <>
                              <button
                                type="button"
                                onClick={() => handleResendInvite(u.user_id, u.email)}
                                disabled={actionLoading === u.user_id}
                                className="text-sm text-sky-400 hover:text-sky-300 disabled:opacity-50"
                              >
                                Resend invite
                              </button>
                              <button
                                type="button"
                                onClick={() => handleRemoveFromWorkspace(u.user_id, u.email)}
                                disabled={actionLoading === u.user_id}
                                className="text-sm text-red-400 hover:text-red-300 disabled:opacity-50"
                              >
                                Remove
                              </button>
                            </>
                          )}
                          {st === "active" && (
                            <>
                              <button
                                type="button"
                                onClick={() => handleSuspend(u.user_id)}
                                disabled={actionLoading === u.user_id}
                                className="text-sm text-amber-400 hover:text-amber-300 disabled:opacity-50"
                              >
                                Suspend
                              </button>
                              <button
                                type="button"
                                onClick={() => handleRemoveFromWorkspace(u.user_id, u.email)}
                                disabled={actionLoading === u.user_id}
                                className="text-sm text-red-400 hover:text-red-300 disabled:opacity-50"
                              >
                                Remove
                              </button>
                            </>
                          )}
                          {st === "suspended" && (
                            <>
                              <button
                                type="button"
                                onClick={() => handleReactivate(u.user_id)}
                                disabled={actionLoading === u.user_id}
                                className="text-sm text-emerald-400 hover:text-emerald-300 disabled:opacity-50"
                              >
                                Reactivate
                              </button>
                              <button
                                type="button"
                                onClick={() => handleRemoveFromWorkspace(u.user_id, u.email)}
                                disabled={actionLoading === u.user_id}
                                className="text-sm text-red-400 hover:text-red-300 disabled:opacity-50"
                              >
                                Remove
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
