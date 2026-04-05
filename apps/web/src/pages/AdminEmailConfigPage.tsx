import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  getPrimaryEmailConfig,
  updatePrimaryEmailConfig,
  testPrimaryEmailConfig,
  testPrimaryEmailInbound,
  testPrimaryEmailOutbound,
  syncOtherImapNow,
  disconnectPrimaryEmailConfig,
  registerGmailWatch,
  renewGmailWatch,
  syncGmailNow,
  getGmailIngestionHealth,
  EmailConfig,
  EmailConfigUpdatePayload,
  type GmailIngestionHealth,
} from "../api";

const STATUS_BADGE: Record<string, string> = {
  NOT_CONNECTED: "Not connected",
  CONNECTING: "Connecting",
  CONNECTED: "Connected",
  ERROR: "Error",
  DISABLED: "Disabled",
  NOT_CONFIGURED: "Not configured",
  CONFIGURED: "Configured",
  TESTING: "Testing",
};

const STATUS_COLORS: Record<string, string> = {
  NOT_CONNECTED: "bg-[#1e293b] text-[#94a3b8]",
  CONNECTING: "bg-amber-900/40 text-amber-200",
  CONNECTED: "bg-emerald-900/40 text-emerald-300",
  ERROR: "bg-red-900/40 text-red-400",
  DISABLED: "bg-[#1e293b] text-[#64748b]",
  NOT_CONFIGURED: "bg-[#1e293b] text-[#94a3b8]",
  CONFIGURED: "bg-[#1e293b] text-[#94a3b8]",
  TESTING: "bg-amber-900/40 text-amber-200",
};

function formatLastTested(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return "—";
  }
}

export default function AdminEmailConfigPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [config, setConfig] = useState<EmailConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showAdvancedSetup, setShowAdvancedSetup] = useState(false);
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false);
  const [syncingGmail, setSyncingGmail] = useState(false);
  const [registeringWatch, setRegisteringWatch] = useState(false);
  const [renewingWatch, setRenewingWatch] = useState(false);
  const [testingInbound, setTestingInbound] = useState(false);
  const [testingOutbound, setTestingOutbound] = useState(false);
  const [syncingOther, setSyncingOther] = useState(false);
  const [gmailOpsAdvancedOpen, setGmailOpsAdvancedOpen] = useState(false);
  const [gmailHealth, setGmailHealth] = useState<GmailIngestionHealth | null>(null);
  const [loadingGmailHealth, setLoadingGmailHealth] = useState(false);

  const [form, setForm] = useState<EmailConfigUpdatePayload>({
    email_address: "",
    display_name: "",
    reply_to: "",
    mailbox_type: "other",
    provider_name: "Other IMAP/SMTP",
    connection_mode: "manual",
    inbound_enabled: true,
    outbound_enabled: true,
    is_primary: true,
    imap_host: "",
    imap_port: 993,
    imap_username: "",
    imap_password: "",
    imap_security: "ssl",
    smtp_host: "",
    smtp_port: 587,
    smtp_username: "",
    smtp_password: "",
    smtp_security: "starttls",
    use_ssl: true,
    use_tls: true,
  });

  const refreshConfig = async () => {
    const data = await getPrimaryEmailConfig();
    setConfig(data ?? null);
  };

  useEffect(() => {
    const gmail = searchParams.get("gmail");
    const err = searchParams.get("error");
    if (gmail === "connected") {
      const watchFailed = searchParams.get("gmail_watch") === "failed";
      setSuccess(
        watchFailed
          ? "Signed in with Google, but automatic new-mail alerts could not be activated. See “Automatic mail” below or open Advanced."
          : "Signed in with Google. Confirm “Automatic mail” below shows Live before treating Gmail intake as complete.",
      );
      setSearchParams({}, { replace: true });
      refreshConfig();
    } else if (err) {
      const messages: Record<string, string> = {
        missing_params: "Connection failed: missing parameters.",
        invalid_state: "Connection failed: session expired or invalid. Please try again.",
        tenant_required: "Connection failed: tenant context required.",
        unauthorized: "You must be logged in as an admin.",
        token_exchange_failed: "Connection failed: could not complete authorization.",
        no_refresh_token: "Connection failed: no refresh token. Please try again.",
        userinfo_failed: "Connection failed: could not fetch account info.",
      };
      setError(messages[err] || `Connection failed: ${err}`);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (!config || config.mailbox_type !== "gmail" || config.connection_mode !== "oauth" || !gmailOpsAdvancedOpen) {
      return;
    }
    let cancelled = false;
    setLoadingGmailHealth(true);
    getGmailIngestionHealth()
      .then((h) => {
        if (!cancelled) setGmailHealth(h);
      })
      .catch(() => {
        if (!cancelled) setGmailHealth(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingGmailHealth(false);
      });
    return () => {
      cancelled = true;
    };
  }, [config, gmailOpsAdvancedOpen]);

  useEffect(() => {
    let cancelled = false;
    getPrimaryEmailConfig()
      .then((data) => {
        if (!cancelled && data) {
          setConfig(data);
          if (data.connection_mode === "manual") {
            const mt = data.mailbox_type === "imap" ? "other" : data.mailbox_type;
            setForm({
              email_address: data.email_address,
              display_name: data.display_name ?? "",
              reply_to: data.reply_to ?? "",
              mailbox_type: mt,
              provider_name: data.provider_name ?? "Other IMAP/SMTP",
              connection_mode: "manual",
              inbound_enabled: data.inbound_enabled,
              outbound_enabled: data.outbound_enabled,
              is_primary: data.is_primary ?? true,
              imap_host: data.imap_host ?? "",
              imap_port: data.imap_port ?? 993,
              imap_username: data.imap_username ?? "",
              imap_password: "",
              imap_security: data.imap_security ?? (data.use_ssl ? "ssl" : "starttls"),
              smtp_host: data.smtp_host ?? "",
              smtp_port: data.smtp_port ?? 587,
              smtp_username: data.smtp_username ?? "",
              smtp_password: "",
              smtp_security: data.smtp_security ?? (data.smtp_port === 465 ? "ssl" : "starttls"),
              use_ssl: data.use_ssl ?? true,
              use_tls: data.use_tls ?? true,
            });
            setShowAdvancedSetup(true);
          }
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || "Failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const handleRegisterWatch = async () => {
    setRegisteringWatch(true);
    setError(null);
    setSuccess(null);
    try {
      const r = await registerGmailWatch();
      setSuccess(
        `Gmail watch registered. Expires: ${r.gmail_watch_expires_at ? new Date(r.gmail_watch_expires_at).toLocaleString() : "—"}.`
      );
      await refreshConfig();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Register watch failed");
    } finally {
      setRegisteringWatch(false);
    }
  };

  const handleRenewWatch = async (force: boolean) => {
    setRenewingWatch(true);
    setError(null);
    setSuccess(null);
    try {
      const r = await renewGmailWatch(force);
      if (r.skipped === "not_due") {
        setSuccess(`Watch still valid until ${r.gmail_watch_expires_at ? new Date(r.gmail_watch_expires_at).toLocaleString() : "—"} (renew within ${r.renew_within_hours ?? "?"}h).`);
      } else {
        setSuccess(`Watch renewed. Expires: ${r.gmail_watch_expires_at ? new Date(r.gmail_watch_expires_at).toLocaleString() : "—"}.`);
      }
      await refreshConfig();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Renew watch failed");
    } finally {
      setRenewingWatch(false);
    }
  };

  const handleSyncGmail = async () => {
    setSyncingGmail(true);
    setError(null);
    setSuccess(null);
    try {
      const r = await syncGmailNow(30);
      const when = r.last_sync_at ? ` Last delta sync (server): ${new Date(r.last_sync_at).toLocaleString()}.` : "";
      setSuccess(
        `Ingestion: ${r.threads_scanned} Gmail thread(s) with changes, ${r.messages_upserted} message row(s), ${r.attachments_upserted} attachment row(s), history pages ${r.history_pages ?? 0}.${when}`
      );
      await refreshConfig();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gmail sync failed");
    } finally {
      setSyncingGmail(false);
    }
  };

  const handleConnectGmail = () => {
    setError(null);
    window.location.href = "/api/v1/admin/email-config/gmail/authorize";
  };

  const handleDisconnect = async () => {
    setShowDisconnectConfirm(false);
    setError(null);
    setSuccess(null);
    setDisconnecting(true);
    try {
      await disconnectPrimaryEmailConfig();
      setConfig(null);
      setSuccess("Primary mailbox disconnected.");
      setForm((f) => ({ ...f, email_address: "", imap_host: "", smtp_host: "" }));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Disconnect failed");
    } finally {
      setDisconnecting(false);
    }
  };

  const handleSaveAdvanced = async () => {
    setError(null);
    setSuccess(null);
    setSaving(true);
    try {
      const imapSec = form.imap_security ?? (form.use_ssl ? "ssl" : "starttls");
      const smtpSec = form.smtp_security ?? (form.smtp_port === 465 ? "ssl" : "starttls");
      const payload: EmailConfigUpdatePayload = {
        email_address: form.email_address,
        display_name: form.display_name || undefined,
        reply_to: form.reply_to?.trim() || undefined,
        mailbox_type: form.mailbox_type === "imap" ? "other" : form.mailbox_type,
        provider_name: form.provider_name || undefined,
        connection_mode: "manual",
        inbound_enabled: form.inbound_enabled,
        outbound_enabled: form.outbound_enabled,
        is_primary: form.is_primary ?? true,
        imap_host: form.imap_host || undefined,
        imap_port: form.imap_port ?? undefined,
        imap_username: form.imap_username || undefined,
        imap_security: imapSec,
        smtp_host: form.smtp_host || undefined,
        smtp_port: form.smtp_port ?? undefined,
        smtp_username: form.smtp_username || undefined,
        smtp_security: smtpSec,
        use_ssl: imapSec === "ssl",
        use_tls: smtpSec === "starttls",
      };
      if (form.imap_password) payload.imap_password = form.imap_password;
      if (form.smtp_password) payload.smtp_password = form.smtp_password;
      await updatePrimaryEmailConfig(payload);
      await refreshConfig();
      setSuccess("Settings saved.");
      setForm((f) => ({ ...f, imap_password: "", smtp_password: "" }));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setError(null);
    setSuccess(null);
    setTesting(true);
    try {
      const result = await testPrimaryEmailConfig();
      setSuccess(result.ok ? "Connection successful." : `Test: ${result.status}. ${result.message || ""}`);
      await refreshConfig();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(false);
    }
  };

  const handleTestInbound = async () => {
    setError(null);
    setSuccess(null);
    setTestingInbound(true);
    try {
      const result = await testPrimaryEmailInbound();
      setSuccess(
        result.ok
          ? "Inbound (IMAP) connection OK."
          : `Inbound test: ${result.status}. ${result.message || ""}`,
      );
      await refreshConfig();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Inbound test failed");
    } finally {
      setTestingInbound(false);
    }
  };

  const handleTestOutbound = async () => {
    setError(null);
    setSuccess(null);
    setTestingOutbound(true);
    try {
      const result = await testPrimaryEmailOutbound();
      setSuccess(
        result.ok
          ? "Outbound (SMTP) connection OK."
          : `Outbound test: ${result.status}. ${result.message || ""}`,
      );
      await refreshConfig();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Outbound test failed");
    } finally {
      setTestingOutbound(false);
    }
  };

  const handleSyncOther = async () => {
    setSyncingOther(true);
    setError(null);
    setSuccess(null);
    try {
      const r = await syncOtherImapNow(80);
      setSuccess(
        `IMAP sync: ${r.uids_fetched} UID(s) fetched, ${r.messages_upserted} new message row(s), ${r.attachments_upserted} attachment row(s).`,
      );
      await refreshConfig();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "IMAP sync failed");
    } finally {
      setSyncingOther(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12 text-[#94a3b8]">Loading...</div>
    );
  }

  const isGmailConnected = config?.mailbox_type === "gmail" && config?.connection_mode === "oauth";
  const isOtherManualMailbox = (t: string | undefined) => t === "other" || t === "imap";
  const isManualConnected =
    config?.connection_mode === "manual" &&
    !!config?.email_address &&
    isOtherManualMailbox(config?.mailbox_type);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-['Barlow_Condensed'] text-3xl font-bold tracking-tight text-[#e8edf5]">
          Email Configuration
        </h1>
        <p className="mt-1 text-sm text-[#64748b]">
          Connect the mailbox your company uses for inbound and outbound load-related email.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-4 text-red-400">{error}</div>
      )}
      {success && (
        <div className="rounded-lg border border-emerald-900/50 bg-emerald-950/20 p-4 text-emerald-400">{success}</div>
      )}

      {/* Section 1 — Provider cards */}
      <section>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-[#64748b]">
          Connect a mailbox
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {/* Gmail card — primary, recommended */}
          <div className="relative rounded-xl border-2 border-[#3b82f6]/50 bg-[#0a0e14] p-6 shadow-[0_0_0_1px_rgba(59,130,246,0.2)]">
            <span className="absolute right-3 top-3 rounded bg-[#3b82f6]/20 px-2 py-0.5 text-xs font-medium text-[#60a5fa]">
              Recommended
            </span>
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-white">
                <svg viewBox="0 0 24 24" className="h-6 w-6">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold text-[#e8edf5]">Gmail / Google Workspace</h3>
                <span className={`mt-2 inline-block rounded px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[isGmailConnected ? config?.status ?? "CONNECTED" : "NOT_CONNECTED"]}`}>
                  {STATUS_BADGE[isGmailConnected ? (config?.status ?? "CONNECTED") : "NOT_CONNECTED"]}
                </span>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {isGmailConnected ? (
                <>
                  <button
                    type="button"
                    onClick={handleTest}
                    disabled={testing}
                    className="rounded-lg border border-[#1e293b] bg-[#0f1420] px-3 py-1.5 text-sm font-medium text-[#94a3b8] transition hover:border-[#334155] hover:text-[#e8edf5] disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {testing ? "Testing…" : "Test connection"}
                  </button>
                  <button
                    type="button"
                    onClick={handleConnectGmail}
                    className="rounded-lg border border-[#334155] px-3 py-1.5 text-sm font-medium text-[#94a3b8] transition hover:border-[#475569] hover:text-[#e8edf5]"
                  >
                    Reconnect
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowDisconnectConfirm(true)}
                    disabled={disconnecting}
                    className="rounded-lg border border-red-900/50 px-3 py-1.5 text-sm font-medium text-red-400 transition hover:bg-red-950/30 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {disconnecting ? "Disconnecting…" : "Disconnect"}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={handleConnectGmail}
                  className="rounded-lg border border-[#3b82f6] bg-[#3b82f6] px-4 py-2 text-sm font-semibold text-white shadow-[0_2px_8px_rgba(59,130,246,0.4)] transition hover:bg-[#2563eb] hover:shadow-[0_2px_12px_rgba(59,130,246,0.5)]"
                >
                  Connect with Google
                </button>
              )}
            </div>
            <p className="mt-3 text-sm text-[#94a3b8]">
              Recommended for Gmail and Google Workspace. Sign in with Google and approve access.
            </p>
          </div>

          {/* Microsoft 365 card — Coming soon */}
          <div className="rounded-xl border border-[#1e293b] bg-[#0a0e14] p-6 opacity-90">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-[#00a4ef]">
                <svg viewBox="0 0 24 24" className="h-6 w-6 text-white">
                  <path fill="currentColor" d="M11.4 24H0L12 12 24 0h-4.2L8.4 12 11.4 24zm12.6 0h-4.2L12 12 4.2 24H0L12 0l12 24z"/>
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold text-[#e8edf5]">Microsoft 365 / Outlook</h3>
                <span className="mt-2 inline-block rounded bg-amber-900/40 px-2 py-0.5 text-xs font-medium text-amber-200">
                  Coming soon
                </span>
              </div>
            </div>
            <p className="mt-4 text-sm text-[#64748b]">
              Connect with Microsoft — same one-click flow.
            </p>
            <button
              type="button"
              disabled
              className="mt-4 rounded-lg border border-[#1e293b] bg-[#0f1420] px-3 py-1.5 text-sm font-medium text-[#64748b] cursor-not-allowed"
            >
              Connect with Microsoft 365
            </button>
          </div>

          {/* Other Email Provider card */}
          <div className="rounded-xl border border-[#1e293b] bg-[#0a0e14] p-6">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-[#334155]">
                <svg viewBox="0 0 24 24" className="h-6 w-6 text-[#94a3b8]" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                  <path d="M22 6l-10 7L2 6"/>
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold text-[#e8edf5]">Other Email Provider</h3>
                <span className={`mt-2 inline-block rounded px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[isManualConnected ? (config?.status ?? "CONFIGURED") : "NOT_CONNECTED"]}`}>
                  {STATUS_BADGE[isManualConnected ? (config?.status ?? "CONFIGURED") : "NOT_CONNECTED"]}
                </span>
              </div>
            </div>
            <p className="mt-4 text-sm text-[#64748b]">
              Use this only if your provider is not Google or Microsoft.
            </p>
            <button
              type="button"
              onClick={() => setShowAdvancedSetup(!showAdvancedSetup)}
              className="mt-4 rounded-lg border border-[#334155] px-3 py-1.5 text-sm font-medium text-[#94a3b8] transition hover:border-[#475569] hover:text-[#e8edf5]"
            >
              {showAdvancedSetup ? "Hide" : "Use advanced setup"}
            </button>
          </div>
        </div>
      </section>

      {/* Disconnect confirmation modal */}
      {showDisconnectConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setShowDisconnectConfirm(false)}>
          <div
            className="max-w-md rounded-xl border border-[#1e293b] bg-[#0d111a] p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-semibold text-[#e8edf5]">Disconnect this mailbox?</h3>
            <p className="mt-2 text-sm text-[#94a3b8]">
              Email sync and sending for this tenant may stop.
            </p>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowDisconnectConfirm(false)}
                className="rounded-lg border border-[#334155] px-4 py-2 text-sm font-medium text-[#94a3b8] hover:bg-[#1e293b]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDisconnect}
                disabled={disconnecting}
                className="rounded-lg border border-red-900/50 bg-red-950/30 px-4 py-2 text-sm font-medium text-red-400 hover:bg-red-950/50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {disconnecting ? "Disconnecting…" : "Disconnect"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Section 2 — Gmail: automatic ingestion = definition of done */}
      {isGmailConnected && config && (
        <section className="rounded-xl border border-[#1e293b] bg-[#0a0e14] p-6">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-[#64748b]">Gmail</h2>
          <p className="mb-4 text-sm text-[#94a3b8]">
            Signed in as <span className="text-[#e8edf5]">{config.oauth_account_email || config.email_address}</span>.
            Signing in alone does not mean new mail arrives in TruckERP automatically — see{" "}
            <span className="font-medium text-[#cbd5e1]">Automatic mail</span> below.
          </p>

          <div
            className={`mb-4 rounded-lg border p-4 text-sm ${
              config.gmail_automatic_ingestion_ready
                ? "border-emerald-900/50 bg-emerald-950/20 text-emerald-100/90"
                : "border-amber-900/50 bg-amber-950/15 text-amber-50/90"
            }`}
          >
            <p className="font-semibold text-[#e8edf5]">
              Automatic mail:{" "}
              {config.gmail_automatic_ingestion_ready ? "Live (checks passed)" : "Not complete — action needed"}
            </p>
            <p className="mt-1 text-xs text-[#94a3b8]">
              “Live” means the server can receive new-mail signals from Google and update your inbox without manual Sync.
              OAuth “Connected” is only step one.
            </p>
            {(config.gmail_automatic_ingestion_blockers?.length ?? 0) > 0 && (
              <ul className="mt-3 list-disc space-y-1 pl-5 text-[#fca5a5]">
                {config.gmail_automatic_ingestion_blockers!.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            )}
            {(config.gmail_automatic_ingestion_warnings?.length ?? 0) > 0 && (
              <ul className="mt-3 list-disc space-y-1 pl-5 text-[#fde68a]">
                {config.gmail_automatic_ingestion_warnings!.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="mb-4 grid gap-2 text-sm text-[#94a3b8]">
            <p>
              Google sign-in status:{" "}
              <span className={STATUS_COLORS[config.status] ?? "text-[#94a3b8]"}>
                {STATUS_BADGE[config.status] ?? config.status}
              </span>
              {config.last_tested_at ? ` · Last sign-in test: ${formatLastTested(config.last_tested_at)}` : ""}
            </p>
            {config.last_error_message && (
              <div className="space-y-2">
                <p className="text-red-400">{config.last_error_message}</p>
                {(config.last_error_message.includes("invalid_grant") ||
                  config.last_error_message.includes("token refresh failed") ||
                  config.last_error_message.includes("oauth2.googleapis.com/token")) && (
                  <p className="text-xs leading-relaxed">
                    Use <span className="font-medium text-[#cbd5e1]">Sign in with Google again</span> on the Gmail card
                    above, or ask support to verify Google OAuth credentials in production.
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="mb-4 rounded-lg border border-[#1e293b] bg-[#0d111a] p-4 text-sm">
            <p className="mb-2 font-medium text-[#cbd5e1]">Where we are in the pipeline</p>
            <ul className="space-y-2 text-[#94a3b8]">
              <li>
                Server ready for Google push:{" "}
                <span className="text-[#e8edf5]">{config.gmail_pubsub_topic_configured ? "Yes" : "No (operations)"}</span>
              </li>
              <li>
                Bookmark for changes in Gmail:{" "}
                <span className="text-[#e8edf5]">{config.gmail_history_cursor_present ? "Set" : "Not set"}</span>
              </li>
              <li>
                Automatic alert subscription:{" "}
                <span className="text-[#e8edf5]">
                  {config.gmail_watch_expires_at == null
                    ? "Off"
                    : config.gmail_watch_active
                      ? `On · renew before ${formatLastTested(config.gmail_watch_expires_at)}`
                      : "Expired"}
                </span>
              </li>
              <li>
                Last automatic signal from Google:{" "}
                <span className="text-[#e8edf5]">
                  {config.last_gmail_webhook_at ? formatLastTested(config.last_gmail_webhook_at) : "None yet"}
                </span>
              </li>
              <li>
                Last time TruckERP pulled changes from Gmail:{" "}
                <span className="text-[#e8edf5]">
                  {config.last_inbound_sync_at ? formatLastTested(config.last_inbound_sync_at) : "—"}
                </span>
              </li>
            </ul>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            {config.gmail_pubsub_topic_configured && !config.gmail_automatic_ingestion_ready && (
              <button
                type="button"
                onClick={handleRegisterWatch}
                disabled={registeringWatch || renewingWatch}
                className="rounded-lg border border-emerald-700 bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {registeringWatch ? "Turning on…" : "Turn on automatic new-mail alerts"}
              </button>
            )}
            <button
              type="button"
              onClick={handleConnectGmail}
              className="rounded-lg border border-[#334155] px-3 py-2 text-sm font-medium text-[#94a3b8] hover:border-[#475569] hover:text-[#e8edf5]"
            >
              Sign in with Google again
            </button>
            <button
              type="button"
              onClick={() => setShowDisconnectConfirm(true)}
              disabled={disconnecting}
              className="rounded-lg border border-red-900/50 px-3 py-2 text-sm font-medium text-red-400 hover:bg-red-950/30 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {disconnecting ? "Disconnecting…" : "Disconnect Gmail"}
            </button>
          </div>

          <details
            className="rounded-lg border border-[#1e293b] bg-[#0d111a]"
            onToggle={(e) => setGmailOpsAdvancedOpen((e.target as HTMLDetailsElement).open)}
          >
            <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-[#94a3b8] hover:text-[#e8edf5]">
              Advanced — support & manual tools (not required for normal operation)
            </summary>
            <div className="space-y-4 border-t border-[#1e293b] px-4 py-4 text-sm text-[#94a3b8]">
              <p className="text-xs leading-relaxed text-[#64748b]">
                For troubleshooting or when automatic mail is off. Routine renewal is handled by a scheduled server job
                before Google expires the subscription (about every 7 days).
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleSyncGmail}
                  disabled={syncingGmail}
                  className="rounded-lg border border-sky-900/50 bg-sky-950/30 px-3 py-1.5 text-sm font-medium text-sky-200 hover:bg-sky-950/50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {syncingGmail ? "Working…" : "Fetch new mail once (manual)"}
                </button>
                <button
                  type="button"
                  onClick={handleRegisterWatch}
                  disabled={registeringWatch || renewingWatch}
                  className="rounded-lg border border-emerald-900/50 bg-emerald-950/25 px-3 py-1.5 text-sm font-medium text-emerald-200 hover:bg-emerald-950/40 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {registeringWatch ? "…" : "Subscribe with Google again"}
                </button>
                <button
                  type="button"
                  onClick={() => handleRenewWatch(false)}
                  disabled={registeringWatch || renewingWatch}
                  className="rounded-lg border border-[#1e293b] bg-[#0f1420] px-3 py-1.5 text-sm font-medium text-[#94a3b8] hover:border-[#334155] hover:text-[#e8edf5] disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {renewingWatch ? "…" : "Extend subscription (if due soon)"}
                </button>
                <button
                  type="button"
                  onClick={() => handleRenewWatch(true)}
                  disabled={registeringWatch || renewingWatch}
                  className="rounded-lg border border-amber-900/40 bg-amber-950/20 px-3 py-1.5 text-sm font-medium text-amber-200/90 hover:bg-amber-950/35 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Force extend subscription
                </button>
                <button
                  type="button"
                  onClick={handleTest}
                  disabled={testing}
                  className="rounded-lg border border-[#1e293b] bg-[#0f1420] px-3 py-1.5 text-sm font-medium text-[#94a3b8] hover:border-[#334155] hover:text-[#e8edf5] disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {testing ? "…" : "Test Google sign-in"}
                </button>
              </div>
              <div className="rounded border border-[#1e293b] bg-[#0a0e14] p-3 text-xs leading-relaxed text-[#94a3b8]">
                <p className="mb-2 font-medium text-[#cbd5e1]">End-to-end verification (proof)</p>
                {loadingGmailHealth && <p>Loading checklist…</p>}
                {!loadingGmailHealth && gmailHealth && (
                  <>
                    <p className="mb-2">
                      API says automatic pipeline ready:{" "}
                      <span className="text-[#e8edf5]">{gmailHealth.automatic_ingestion_ready ? "yes" : "no"}</span>
                    </p>
                    <ol className="list-decimal space-y-2 pl-5">
                      {gmailHealth.proof_steps.map((s, i) => (
                        <li key={i}>{s}</li>
                      ))}
                    </ol>
                  </>
                )}
              </div>
            </div>
          </details>
        </section>
      )}

      {isManualConnected && config && !isGmailConnected && (
        <section className="rounded-xl border border-[#1e293b] bg-[#0a0e14] p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-[#64748b]">
            Connected mailbox (Other provider)
          </h2>
          <div className="space-y-3 text-sm">
            <p className="text-[#e8edf5]">
              <span className="text-[#64748b]">Mailbox </span>
              {config.email_address}
              {config.display_name ? ` · ${config.display_name}` : ""}
            </p>
            {config.reply_to && (
              <p className="text-[#94a3b8]">
                Reply-To: <span className="text-[#e8edf5]">{config.reply_to}</span>
              </p>
            )}
            <p className="text-[#94a3b8]">
              IMAP: <span className="text-[#e8edf5]">{config.imap_host}:{config.imap_port}</span> ({config.imap_security || (config.use_ssl ? "ssl" : "starttls")}) · SMTP:{" "}
              <span className="text-[#e8edf5]">{config.smtp_host}:{config.smtp_port}</span> ({config.smtp_security || "starttls"})
            </p>
            <p className="text-[#94a3b8]">
              Connection:{" "}
              <span className={STATUS_COLORS[config.connection_status || config.status] ?? "text-[#94a3b8]"}>
                {STATUS_BADGE[config.connection_status || config.status] || config.connection_status || config.status}
              </span>
            </p>
            <p className="text-[#94a3b8]">
              Last inbound test: {formatLastTested(config.last_inbound_test_at)} · Last outbound test:{" "}
              {formatLastTested(config.last_outbound_test_at)}
            </p>
            <div className="rounded-lg border border-[#1e293b] bg-[#0d111a] p-3">
              <p className="mb-2 font-medium text-[#94a3b8]">IMAP ingestion</p>
              <ul className="space-y-1 text-[#94a3b8]">
                <li>
                  UIDVALIDITY / last UID:{" "}
                  <span className="text-[#e8edf5]">
                    {config.imap_uidvalidity != null ? String(config.imap_uidvalidity) : "—"} /{" "}
                    {config.imap_last_seen_uid != null ? String(config.imap_last_seen_uid) : "—"}
                  </span>
                </li>
                <li>
                  Last sync:{" "}
                  <span className="text-[#e8edf5]">
                    {config.last_inbound_sync_at ? formatLastTested(config.last_inbound_sync_at) : "—"}
                  </span>
                  {config.last_sync_status && (
                    <>
                      {" "}
                      <span className="text-[#64748b]">· status</span>{" "}
                      <span className="text-[#e8edf5]">{config.last_sync_status}</span>
                    </>
                  )}
                </li>
                {config.last_sync_error && (
                  <li className="text-red-400">Sync error: {config.last_sync_error}</li>
                )}
              </ul>
              <p className="mt-2 text-xs text-[#64748b]">
                Operator tool: incremental sync uses server UID state (not Gmail). Production may add a scheduled fallback
                using the same endpoint.
              </p>
            </div>
            {config.last_error_message && (
              <p className="text-sm text-red-400">{config.last_error_message}</p>
            )}
            <div className="flex flex-wrap gap-2 pt-2">
              <button
                type="button"
                onClick={handleTestInbound}
                disabled={testingInbound}
                className="rounded-lg border border-[#1e293b] bg-[#0f1420] px-3 py-1.5 text-sm font-medium text-[#94a3b8] hover:border-[#334155] hover:text-[#e8edf5] disabled:opacity-50"
              >
                {testingInbound ? "Testing…" : "Test inbound (IMAP)"}
              </button>
              <button
                type="button"
                onClick={handleTestOutbound}
                disabled={testingOutbound}
                className="rounded-lg border border-[#1e293b] bg-[#0f1420] px-3 py-1.5 text-sm font-medium text-[#94a3b8] hover:border-[#334155] hover:text-[#e8edf5] disabled:opacity-50"
              >
                {testingOutbound ? "Testing…" : "Test outbound (SMTP)"}
              </button>
              <button
                type="button"
                onClick={handleSyncOther}
                disabled={syncingOther}
                className="rounded-lg border border-sky-900/50 bg-sky-950/30 px-3 py-1.5 text-sm font-medium text-sky-200 hover:bg-sky-950/50 disabled:opacity-50"
              >
                {syncingOther ? "Syncing…" : "Sync new mail (IMAP, operator)"}
              </button>
              <button
                type="button"
                onClick={() => setShowAdvancedSetup(true)}
                className="rounded-lg border border-[#334155] px-3 py-1.5 text-sm font-medium text-[#94a3b8] hover:text-[#e8edf5]"
              >
                Edit settings
              </button>
              <button
                type="button"
                onClick={() => setShowDisconnectConfirm(true)}
                disabled={disconnecting}
                className="rounded-lg border border-red-900/50 px-3 py-1.5 text-sm font-medium text-red-400 hover:bg-red-950/30 disabled:opacity-50"
              >
                Disconnect
              </button>
            </div>
          </div>
        </section>
      )}

      {/* Section 3 — Advanced setup (hidden by default) */}
      {showAdvancedSetup && (
        <section className="rounded-xl border border-[#1e293b] bg-[#0a0e14] p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-[#64748b]">
            Advanced setup
          </h2>
          <p className="mb-6 text-sm text-[#94a3b8]">
            Use this only if your provider is not Google or Microsoft. Configure manual IMAP/SMTP server settings. Use an app password when available.
          </p>
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[#64748b]">Mailbox email</label>
                <input
                  type="email"
                  value={form.email_address}
                  onChange={(e) => setForm((f) => ({ ...f, email_address: e.target.value }))}
                  placeholder="mailbox@example.com"
                  className="w-full rounded-lg border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder-[#475569]"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[#64748b]">From name</label>
                <input
                  type="text"
                  value={form.display_name ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
                  placeholder="Optional"
                  className="w-full rounded-lg border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder-[#475569]"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[#64748b]">Reply-To (optional)</label>
                <input
                  type="text"
                  value={form.reply_to ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, reply_to: e.target.value }))}
                  placeholder="Optional"
                  className="w-full rounded-lg border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder-[#475569]"
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_primary_mailbox"
                checked={form.is_primary ?? true}
                onChange={(e) => setForm((f) => ({ ...f, is_primary: e.target.checked }))}
                className="rounded border-[#1e293b]"
              />
              <label htmlFor="is_primary_mailbox" className="text-sm text-[#94a3b8]">
                Primary mailbox for this workspace
              </label>
            </div>
            <div className="grid gap-6 md:grid-cols-2">
              <div className="rounded-lg border border-[#1e293b] p-4">
                <h3 className="mb-3 text-sm font-semibold text-[#e8edf5]">Inbound (IMAP)</h3>
                <div className="space-y-3">
                  <input
                    type="text"
                    value={form.imap_host ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, imap_host: e.target.value }))}
                    placeholder="IMAP host"
                    className="w-full rounded border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder-[#475569]"
                  />
                  <input
                    type="number"
                    value={form.imap_port ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, imap_port: parseInt(e.target.value, 10) || undefined }))}
                    placeholder="Port"
                    className="w-full rounded border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder-[#475569]"
                  />
                  <input
                    type="text"
                    value={form.imap_username ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, imap_username: e.target.value }))}
                    placeholder="Username"
                    className="w-full rounded border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder-[#475569]"
                  />
                  <input
                    type="password"
                    value={form.imap_password ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, imap_password: e.target.value }))}
                    placeholder="App password (leave blank to keep existing)"
                    className="w-full rounded border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder-[#475569]"
                  />
                  <div>
                    <label className="mb-1 block text-xs text-[#64748b]">IMAP security</label>
                    <select
                      value={form.imap_security ?? "ssl"}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          imap_security: e.target.value,
                          use_ssl: e.target.value === "ssl",
                        }))
                      }
                      className="w-full rounded border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5]"
                    >
                      <option value="ssl">SSL/TLS (e.g. port 993)</option>
                      <option value="starttls">STARTTLS</option>
                      <option value="none">None (not recommended)</option>
                    </select>
                  </div>
                </div>
              </div>
              <div className="rounded-lg border border-[#1e293b] p-4">
                <h3 className="mb-3 text-sm font-semibold text-[#e8edf5]">Outbound (SMTP)</h3>
                <div className="space-y-3">
                  <input
                    type="text"
                    value={form.smtp_host ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, smtp_host: e.target.value }))}
                    placeholder="SMTP host"
                    className="w-full rounded border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder-[#475569]"
                  />
                  <input
                    type="number"
                    value={form.smtp_port ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, smtp_port: parseInt(e.target.value, 10) || undefined }))}
                    placeholder="Port"
                    className="w-full rounded border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder-[#475569]"
                  />
                  <input
                    type="text"
                    value={form.smtp_username ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, smtp_username: e.target.value }))}
                    placeholder="Username"
                    className="w-full rounded border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder-[#475569]"
                  />
                  <input
                    type="password"
                    value={form.smtp_password ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, smtp_password: e.target.value }))}
                    placeholder="App password (leave blank to keep existing)"
                    className="w-full rounded border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder-[#475569]"
                  />
                  <div>
                    <label className="mb-1 block text-xs text-[#64748b]">SMTP security</label>
                    <select
                      value={form.smtp_security ?? "starttls"}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          smtp_security: e.target.value,
                          use_tls: e.target.value === "starttls",
                        }))
                      }
                      className="w-full rounded border border-[#1e293b] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5]"
                    >
                      <option value="ssl">SSL (e.g. port 465)</option>
                      <option value="starttls">STARTTLS (e.g. port 587)</option>
                      <option value="none">None (not recommended)</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handleSaveAdvanced}
                disabled={saving || !form.email_address}
                className="rounded-lg border border-[#3b82f6] bg-[#3b82f6] px-4 py-2 text-sm font-medium text-white transition hover:bg-[#2563eb] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                type="button"
                onClick={handleTestInbound}
                disabled={testingInbound}
                className="rounded-lg border border-[#1e293b] bg-[#0f1420] px-4 py-2 text-sm font-medium text-[#94a3b8] transition hover:border-[#334155] hover:text-[#e8edf5] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {testingInbound ? "Testing…" : "Test inbound"}
              </button>
              <button
                type="button"
                onClick={handleTestOutbound}
                disabled={testingOutbound}
                className="rounded-lg border border-[#1e293b] bg-[#0f1420] px-4 py-2 text-sm font-medium text-[#94a3b8] transition hover:border-[#334155] hover:text-[#e8edf5] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {testingOutbound ? "Testing…" : "Test outbound"}
              </button>
              <button
                type="button"
                onClick={handleTest}
                disabled={testing}
                className="rounded-lg border border-[#1e293b] bg-[#0f1420] px-4 py-2 text-sm font-medium text-[#94a3b8] transition hover:border-[#334155] hover:text-[#e8edf5] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {testing ? "Testing…" : "Test IMAP (legacy)"}
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
