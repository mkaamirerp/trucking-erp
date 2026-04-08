import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import EmailProviderSelector from "../components/email-config/EmailProviderSelector";
import GmailProviderPanel from "../components/email-config/GmailProviderPanel";
import MicrosoftProviderPanel from "../components/email-config/MicrosoftProviderPanel";
import OtherMailProviderPanel from "../components/email-config/OtherMailProviderPanel";
import {
  isGmailConnected,
  isManualMailboxConnected,
  isMicrosoft365Connected,
  type ActiveProvider,
} from "../components/email-config/types";
import { emailModalBtnFocus } from "../components/email-config/focusStyle";
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
  renewMicrosoftSubscription,
  syncMicrosoftNow,
  getMicrosoftOAuthStatus,
  EmailConfig,
  EmailConfigUpdatePayload,
} from "../api";

export default function AdminEmailConfigPage() {
  const disconnectTitleId = useId();
  const disconnectModalRef = useRef<HTMLDivElement>(null);
  const disconnectPrevFocusRef = useRef<HTMLElement | null>(null);
  const oauthNavLockRef = useRef(false);

  const [searchParams, setSearchParams] = useSearchParams();
  const [config, setConfig] = useState<EmailConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false);
  const [syncingGmail, setSyncingGmail] = useState(false);
  const [registeringWatch, setRegisteringWatch] = useState(false);
  const [renewingWatch, setRenewingWatch] = useState(false);
  const [testingInbound, setTestingInbound] = useState(false);
  const [testingOutbound, setTestingOutbound] = useState(false);
  const [syncingOther, setSyncingOther] = useState(false);
  const [renewingMs, setRenewingMs] = useState(false);
  const [syncingMs, setSyncingMs] = useState(false);

  const [activeProvider, setActiveProvider] = useState<ActiveProvider>("gmail");
  const userPickedProviderRef = useRef(false);
  const [panelFlash, setPanelFlash] = useState<{
    provider: ActiveProvider;
    variant: "success" | "error";
    message: string;
  } | null>(null);
  const [microsoftOAuthConfigured, setMicrosoftOAuthConfigured] = useState<boolean | null>(null);

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

  const refreshConfig = useCallback(async () => {
    const data = await getPrimaryEmailConfig();
    setConfig(data ?? null);
    return data;
  }, []);

  const notifyRefreshFailedAfterOAuth = useCallback(() => {
    setError("Signed in, but the latest mailbox status could not be loaded. Reload this page to confirm your connection.");
  }, []);

  useEffect(() => {
    const gmail = searchParams.get("gmail");
    const ms = searchParams.get("microsoft365");
    const err = searchParams.get("error");
    const msErr = searchParams.get("ms_error");
    const clearQ = () => setSearchParams({}, { replace: true });

    if (gmail === "connected") {
      userPickedProviderRef.current = true;
      setActiveProvider("gmail");
      const watchFailed = searchParams.get("gmail_watch") === "failed";
      setError(null);
      setSuccess(null);
      setPanelFlash({
        provider: "gmail",
        variant: "success",
        message: watchFailed
          ? "Signed in with Google. Automatic new-mail alerts could not be turned on — see Automatic mail below or Advanced."
          : "Signed in with Google. Confirm Automatic mail shows Live in this panel before relying on intake.",
      });
      clearQ();
      void refreshConfig().catch(() => notifyRefreshFailedAfterOAuth());
      return;
    }
    if (gmail === "degraded") {
      userPickedProviderRef.current = true;
      setActiveProvider("gmail");
      const watchFailed = searchParams.get("gmail_watch") === "failed";
      let msg =
        "Google saved your sign-in, but the mailbox is not fully linked yet (for example, no inbox address). Reconnect or contact support.";
      if (watchFailed) {
        msg += " Automatic new-mail alerts could not be turned on — see Automatic mail below.";
      }
      setError(null);
      setSuccess(null);
      setPanelFlash({ provider: "gmail", variant: "success", message: msg });
      clearQ();
      void refreshConfig().catch(() => notifyRefreshFailedAfterOAuth());
      return;
    }
    if (ms === "connected") {
      userPickedProviderRef.current = true;
      setActiveProvider("microsoft365");
      setError(null);
      setSuccess(null);
      setPanelFlash({
        provider: "microsoft365",
        variant: "success",
        message:
          "Signed in with Microsoft 365. Review Automatic mail and subscription details in this panel.",
      });
      clearQ();
      void refreshConfig().catch(() => notifyRefreshFailedAfterOAuth());
      return;
    }
    if (err) {
      userPickedProviderRef.current = true;
      setActiveProvider("gmail");
      const messages: Record<string, string> = {
        missing_params: "Google sign-in failed: missing parameters.",
        invalid_state: "Google sign-in failed: session expired or invalid. Please try again.",
        tenant_required: "Google sign-in failed: tenant context required.",
        unauthorized: "You must be logged in as an admin.",
        token_exchange_failed: "Google sign-in failed: could not complete authorization.",
        no_refresh_token: "Google sign-in failed: no refresh token. Please try again.",
        userinfo_failed: "Google sign-in failed: could not fetch account info.",
      };
      setError(null);
      setSuccess(null);
      setPanelFlash({
        provider: "gmail",
        variant: "error",
        message: messages[err] || `Google connection failed: ${err}`,
      });
      clearQ();
      return;
    }
    if (msErr) {
      userPickedProviderRef.current = true;
      setActiveProvider("microsoft365");
      const messages: Record<string, string> = {
        missing_params: "Microsoft sign-in failed: missing parameters.",
        invalid_state: "Microsoft sign-in failed: session expired or invalid. Please try again.",
        unauthorized: "Microsoft sign-in failed: you must be logged in as an admin.",
        token_exchange_failed: "Microsoft sign-in failed: could not complete authorization.",
        no_refresh_token: "Microsoft sign-in failed: no refresh token. Please try again.",
      };
      setError(null);
      setSuccess(null);
      setPanelFlash({
        provider: "microsoft365",
        variant: "error",
        message: messages[msErr] || `Microsoft connection failed: ${msErr}`,
      });
      clearQ();
    }
  }, [searchParams, setSearchParams, refreshConfig, notifyRefreshFailedAfterOAuth]);

  useEffect(() => {
    if (userPickedProviderRef.current) return;
    if (!config) {
      setActiveProvider("gmail");
      return;
    }
    if (isGmailConnected(config)) {
      setActiveProvider("gmail");
    } else if (isMicrosoft365Connected(config)) {
      setActiveProvider("microsoft365");
    } else if (isManualMailboxConnected(config)) {
      setActiveProvider("other");
    } else {
      setActiveProvider("gmail");
    }
  }, [config]);

  useEffect(() => {
    let cancelled = false;
    refreshConfig()
      .then((data) => {
        if (cancelled || !data) return;
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
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || "Failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshConfig]);

  useEffect(() => {
    let cancelled = false;
    getMicrosoftOAuthStatus()
      .then((r) => {
        if (!cancelled) setMicrosoftOAuthConfigured(!!r.oauth_configured);
      })
      .catch(() => {
        if (!cancelled) setMicrosoftOAuthConfigured(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectProvider = (p: ActiveProvider) => {
    userPickedProviderRef.current = true;
    setPanelFlash((f) => (f && f.provider !== p ? null : f));
    setActiveProvider(p);
  };

  const dismissPanelFlash = () => setPanelFlash(null);

  const handleRegisterWatch = async () => {
    setRegisteringWatch(true);
    setError(null);
    setSuccess(null);
    try {
      const r = await registerGmailWatch();
      setSuccess(
        `Gmail watch registered. Expires: ${r.gmail_watch_expires_at ? new Date(r.gmail_watch_expires_at).toLocaleString() : "—"}.`,
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
        setSuccess(
          `Watch still valid until ${r.gmail_watch_expires_at ? new Date(r.gmail_watch_expires_at).toLocaleString() : "—"} (renew within ${r.renew_within_hours ?? "?"}h).`,
        );
      } else {
        setSuccess(
          `Watch renewed. Expires: ${r.gmail_watch_expires_at ? new Date(r.gmail_watch_expires_at).toLocaleString() : "—"}.`,
        );
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
        `Ingestion: ${r.threads_scanned} Gmail thread(s) with changes, ${r.messages_upserted} message row(s), ${r.attachments_upserted} attachment row(s), history pages ${r.history_pages ?? 0}.${when}`,
      );
      await refreshConfig();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gmail sync failed");
    } finally {
      setSyncingGmail(false);
    }
  };

  const handleConnectGmail = () => {
    if (oauthNavLockRef.current) return;
    oauthNavLockRef.current = true;
    setError(null);
    window.location.href = "/api/v1/admin/email-config/gmail/authorize";
  };

  const handleConnectMicrosoft = async () => {
    if (oauthNavLockRef.current) return;
    setError(null);
    let ok = microsoftOAuthConfigured;
    if (ok !== true) {
      try {
        const st = await getMicrosoftOAuthStatus();
        ok = !!st.oauth_configured;
        setMicrosoftOAuthConfigured(ok);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not verify Microsoft sign-in availability.");
        return;
      }
    }
    if (!ok) {
      setError(
        "Microsoft 365 sign-in is not configured on this server. An administrator must set MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET (and related URLs) in the API environment, then restart the API.",
      );
      return;
    }
    oauthNavLockRef.current = true;
    window.location.href = "/api/v1/admin/email-config/microsoft/authorize";
  };

  const handleRenewMicrosoft = async (force: boolean) => {
    setRenewingMs(true);
    setError(null);
    setSuccess(null);
    try {
      const r = await renewMicrosoftSubscription(force);
      setSuccess(r.renewed ? "Microsoft Graph subscription renewed." : "Microsoft subscription renew skipped (not due or unchanged).");
      await refreshConfig();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Renew subscription failed");
    } finally {
      setRenewingMs(false);
    }
  };

  const handleSyncMicrosoft = async () => {
    setSyncingMs(true);
    setError(null);
    setSuccess(null);
    try {
      const r = await syncMicrosoftNow(25);
      setSuccess(
        `Microsoft delta: ${r.messages_processed} message(s), ${r.delta_pages} page(s), cursor advanced: ${r.delta_cursor_advanced ? "yes" : "no"}.`,
      );
      await refreshConfig();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Microsoft sync failed");
    } finally {
      setSyncingMs(false);
    }
  };

  const handleDisconnect = async () => {
    setShowDisconnectConfirm(false);
    setError(null);
    setSuccess(null);
    const tab = activeProvider;
    setDisconnecting(true);
    try {
      await disconnectPrimaryEmailConfig();
      setConfig(null);
      setPanelFlash({
        provider: tab,
        variant: "success",
        message:
          tab === "gmail"
            ? "Gmail has been disconnected from TruckERP."
            : tab === "microsoft365"
              ? "Microsoft 365 has been disconnected from TruckERP."
              : "This mailbox has been disconnected from TruckERP.",
      });
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

  useEffect(() => {
    if (!showDisconnectConfirm) return;
    disconnectPrevFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusFirst = () => {
      const root = disconnectModalRef.current;
      const btn = root?.querySelector<HTMLButtonElement>('[data-disconnect-cancel="true"]');
      btn?.focus();
    };
    const t = window.setTimeout(focusFirst, 0);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setShowDisconnectConfirm(false);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener("keydown", onKey);
      const el = disconnectPrevFocusRef.current;
      if (el?.isConnected) el.focus();
    };
  }, [showDisconnectConfirm]);

  if (loading) {
    return (
      <div className="flex justify-center py-12 text-[#94a3b8]" role="status" aria-live="polite" aria-busy="true">
        Loading email settings…
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-['Barlow_Condensed'] text-3xl font-bold tracking-tight text-[#e8edf5]">
          Email Configuration
        </h1>
        <p className="mt-1 text-sm text-[#64748b]">
          Connect the mailbox your company uses for inbound and outbound load-related email. Pick a provider, then use the
          section below for that provider only.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-4 text-red-400" role="alert">
          {error}
        </div>
      )}
      {success && (
        <div
          className="rounded-lg border border-emerald-900/50 bg-emerald-950/20 p-4 text-emerald-400"
          role="status"
          aria-live="polite"
        >
          {success}
        </div>
      )}

      <EmailProviderSelector active={activeProvider} onSelect={selectProvider} config={config} />

      <div
        className="min-h-[20rem] rounded-xl border border-[#1e293b]/70 bg-[#06080d]/40 p-1 sm:min-h-[28rem] sm:p-1.5 lg:min-h-[32rem]"
        aria-label="Email provider details"
      >
        <div key={activeProvider} className="animate-email-panel-in">
          {activeProvider === "gmail" && (
            <GmailProviderPanel
              config={config}
              testing={testing}
              disconnecting={disconnecting}
              registeringWatch={registeringWatch}
              renewingWatch={renewingWatch}
              syncingGmail={syncingGmail}
              panelFlash={
                panelFlash?.provider === "gmail"
                  ? { variant: panelFlash.variant, message: panelFlash.message }
                  : null
              }
              onDismissPanelFlash={dismissPanelFlash}
              onConnectGmail={handleConnectGmail}
              onDisconnectClick={() => setShowDisconnectConfirm(true)}
              onTest={handleTest}
              onRegisterWatch={handleRegisterWatch}
              onRenewWatch={handleRenewWatch}
              onSyncGmail={handleSyncGmail}
            />
          )}
          {activeProvider === "microsoft365" && (
            <MicrosoftProviderPanel
              config={config}
              microsoftOAuthConfigured={microsoftOAuthConfigured}
              disconnecting={disconnecting}
              renewingMs={renewingMs}
              syncingMs={syncingMs}
              panelFlash={
                panelFlash?.provider === "microsoft365"
                  ? { variant: panelFlash.variant, message: panelFlash.message }
                  : null
              }
              onDismissPanelFlash={dismissPanelFlash}
              onConnectMicrosoft={handleConnectMicrosoft}
              onDisconnectClick={() => setShowDisconnectConfirm(true)}
              onRenewSubscription={handleRenewMicrosoft}
              onSyncNow={handleSyncMicrosoft}
            />
          )}
          {activeProvider === "other" && (
            <OtherMailProviderPanel
              config={config}
              form={form}
              setForm={setForm}
              saving={saving}
              testing={testing}
              testingInbound={testingInbound}
              testingOutbound={testingOutbound}
              syncingOther={syncingOther}
              disconnecting={disconnecting}
              panelFlash={
                panelFlash?.provider === "other"
                  ? { variant: panelFlash.variant, message: panelFlash.message }
                  : null
              }
              onDismissPanelFlash={dismissPanelFlash}
              onSave={handleSaveAdvanced}
              onTest={handleTest}
              onTestInbound={handleTestInbound}
              onTestOutbound={handleTestOutbound}
              onSyncOther={handleSyncOther}
              onDisconnectClick={() => setShowDisconnectConfirm(true)}
            />
          )}
        </div>
      </div>

      <p className="text-xs leading-relaxed text-[#64748b]">
        Automatic Gmail ingestion uses Google push notifications when configured on the server. Microsoft 365 uses Graph
        subscriptions when the webhook URL is configured. Other mail uses IMAP polling / manual sync. Contact support if you
        are unsure which option matches your IT setup.
      </p>

      {showDisconnectConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
          onClick={() => setShowDisconnectConfirm(false)}
          role="presentation"
        >
          <div
            ref={disconnectModalRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={disconnectTitleId}
            className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border border-[#1e293b] bg-[#0d111a] p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id={disconnectTitleId} className="font-semibold text-[#e8edf5]">
              Disconnect this mailbox?
            </h3>
            <p className="mt-2 text-sm text-[#94a3b8]">Email sync and sending for this tenant may stop.</p>
            <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                data-disconnect-cancel="true"
                onClick={() => setShowDisconnectConfirm(false)}
                className={`min-h-[44px] rounded-lg border border-[#334155] px-4 py-2.5 text-sm font-medium text-[#94a3b8] hover:bg-[#1e293b] ${emailModalBtnFocus}`}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDisconnect}
                disabled={disconnecting}
                className={`min-h-[44px] rounded-lg border border-red-900/50 bg-red-950/30 px-4 py-2.5 text-sm font-medium text-red-400 hover:bg-red-950/50 disabled:cursor-not-allowed disabled:opacity-50 ${emailModalBtnFocus}`}
              >
                {disconnecting ? "Disconnecting…" : "Disconnect"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
