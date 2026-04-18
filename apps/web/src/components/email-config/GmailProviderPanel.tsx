import { clsx } from "clsx";
import { useEffect, useState, type ReactNode } from "react";
import {
  getGmailIngestionHealth,
  type EmailConfig,
  type GmailIngestionHealth,
} from "../../api";
import { STATUS_BADGE, STATUS_COLORS, formatLastTested } from "./constants";
import { isGmailConnected } from "./types";
import ProviderPanelFlash from "./ProviderPanelFlash";
import { emailBtnFocus, emailModalBtnFocus } from "./focusStyle";

export type GmailProviderPanelProps = {
  config: EmailConfig | null;
  testing: boolean;
  disconnecting: boolean;
  registeringWatch: boolean;
  renewingWatch: boolean;
  syncingGmail: boolean;
  panelFlash?: { variant: "success" | "error"; message: string } | null;
  onDismissPanelFlash?: () => void;
  onConnectGmail: () => void;
  onDisconnectClick: () => void;
  onTest: () => void;
  onRegisterWatch: () => void;
  onRenewWatch: (force: boolean) => void;
  onSyncGmail: () => void;
};

function CheckRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-start gap-2 text-sm text-[var(--trk-text-muted)]">
      <span className={`mt-0.5 shrink-0 font-medium ${ok ? "text-emerald-400" : "text-[var(--trk-text-muted)]"}`} aria-hidden="true">
        {ok ? "✓" : "—"}
      </span>
      <span>{label}</span>
    </li>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">{children}</h3>;
}

export default function GmailProviderPanel({
  config,
  testing,
  disconnecting,
  registeringWatch,
  renewingWatch,
  syncingGmail,
  panelFlash,
  onDismissPanelFlash,
  onConnectGmail,
  onDisconnectClick,
  onTest,
  onRegisterWatch,
  onRenewWatch,
  onSyncGmail,
}: GmailProviderPanelProps) {
  const [gmailOpsAdvancedOpen, setGmailOpsAdvancedOpen] = useState(false);
  const [gmailHealth, setGmailHealth] = useState<GmailIngestionHealth | null>(null);
  const [loadingGmailHealth, setLoadingGmailHealth] = useState(false);

  const connected = isGmailConnected(config);

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

  if (!connected || !config) {
    return (
      <div className="rounded-xl border border-[var(--trk-border)] bg-[var(--trk-bg)] p-6">
        <h2 className="mb-1 text-xl font-semibold tracking-tight text-[#f1f5f9]">Gmail</h2>
        <p className="mb-5 text-sm text-[var(--trk-text-muted)]">Connect Google to send and receive load mail from Gmail or Google Workspace.</p>
        {panelFlash && onDismissPanelFlash && (
          <ProviderPanelFlash variant={panelFlash.variant} message={panelFlash.message} onDismiss={onDismissPanelFlash} />
        )}
        <p className="mb-4 text-sm text-[var(--trk-text-muted)]">
          After you sign in, TruckERP can keep your inbox in sync automatically once automatic mail is turned on.
        </p>
        <button
          type="button"
          onClick={onConnectGmail}
          className={clsx(
            emailBtnFocus,
            "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[#3b82f6] bg-[#3b82f6] px-4 py-2.5 text-sm font-semibold text-white shadow-[0_2px_8px_rgba(59,130,246,0.4)] transition hover:bg-[#2563eb]",
          )}
        >
          Connect with Google
        </button>
      </div>
    );
  }

  const connLabel = STATUS_BADGE[config.status] ?? config.status;
  const connPillClass = STATUS_COLORS[config.status] ?? STATUS_COLORS.NOT_CONNECTED;

  const autoLive = !!config.gmail_automatic_ingestion_ready;
  const renewalDue =
    config.gmail_watch_expires_at && config.gmail_watch_active
      ? formatLastTested(config.gmail_watch_expires_at)
      : config.gmail_watch_expires_at
        ? formatLastTested(config.gmail_watch_expires_at)
        : null;

  const pushReady = !!config.gmail_pubsub_topic_configured;
  const trackingReady = !!config.gmail_history_cursor_present;
  const subActive = !!config.gmail_watch_active && config.gmail_watch_expires_at != null;

  return (
    <div className="rounded-xl border border-[var(--trk-border)] bg-[var(--trk-bg)] p-6">
      <h2 className="mb-1 text-xl font-semibold tracking-tight text-[#f1f5f9]">Gmail</h2>
      <p className="mb-5 text-sm text-[var(--trk-text-muted)]">Google sign-in, automatic mail, and optional advanced tools.</p>

      {panelFlash && onDismissPanelFlash && (
        <ProviderPanelFlash variant={panelFlash.variant} message={panelFlash.message} onDismiss={onDismissPanelFlash} />
      )}

      <div className="mb-6 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] p-4">
        <SectionTitle>Connection</SectionTitle>
        <p className="text-sm text-[var(--trk-text-muted)]">
          Signed in as: <span className="font-medium text-[var(--trk-text)]">{config.oauth_account_email || config.email_address}</span>
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-[var(--trk-text-muted)]">Status</span>
          <span className={`rounded-md px-2.5 py-1 text-xs font-semibold ${connPillClass}`}>{connLabel}</span>
          {config.last_tested_at && (
            <span className="text-xs text-[var(--trk-text-muted)]">Last checked {formatLastTested(config.last_tested_at)}</span>
          )}
        </div>
        {config.last_error_message && (
          <div className="mt-3 space-y-2 text-sm">
            <p className="text-red-400">{config.last_error_message}</p>
            {(config.last_error_message.includes("invalid_grant") ||
              config.last_error_message.includes("token refresh failed") ||
              config.last_error_message.includes("oauth2.googleapis.com/token")) && (
              <p className="text-xs leading-relaxed text-[var(--trk-text-muted)]">
                Try <span className="font-medium text-[#cbd5e1]">Reconnect / Sign in again</span> below, or contact support
                if this keeps happening.
              </p>
            )}
          </div>
        )}
      </div>

      <div
        className={`mb-6 rounded-lg border p-4 ${
          autoLive
            ? "border-emerald-900/45 bg-emerald-950/15"
            : "border-amber-900/45 bg-amber-950/10"
        }`}
      >
        <SectionTitle>Automatic mail</SectionTitle>
        <p className={`text-lg font-semibold ${autoLive ? "text-emerald-200" : "text-amber-100"}`}>
          {autoLive ? "Live" : "Not ready yet"}
        </p>
        <p className="mt-1 text-sm text-[var(--trk-text-muted)]">
          {autoLive
            ? "New messages from Google can flow into TruckERP without running a manual sync."
            : "Sign-in is only the first step. Finish the steps below or use “Turn on automatic new-mail alerts” when available."}
        </p>
        <dl className="mt-4 space-y-2 text-sm text-[var(--trk-text-muted)]">
          <div className="flex flex-wrap gap-x-2 gap-y-1">
            <dt className="text-[var(--trk-text-muted)]">Last Google signal</dt>
            <dd className="text-[var(--trk-text)]">
              {config.last_gmail_webhook_at ? formatLastTested(config.last_gmail_webhook_at) : "None yet"}
            </dd>
          </div>
          <div className="flex flex-wrap gap-x-2 gap-y-1">
            <dt className="text-[var(--trk-text-muted)]">Last sync into TruckERP</dt>
            <dd className="text-[var(--trk-text)]">
              {config.last_inbound_sync_at ? formatLastTested(config.last_inbound_sync_at) : "—"}
            </dd>
          </div>
          <div className="flex flex-wrap gap-x-2 gap-y-1">
            <dt className="text-[var(--trk-text-muted)]">Renewal due</dt>
            <dd className="text-[var(--trk-text)]">{renewalDue ?? "—"}</dd>
          </div>
        </dl>
        {(config.gmail_automatic_ingestion_blockers?.length ?? 0) > 0 && (
          <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-[#fca5a5]">
            {config.gmail_automatic_ingestion_blockers!.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        )}
        {(config.gmail_automatic_ingestion_warnings?.length ?? 0) > 0 && (
          <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-[#fde68a]">
            {config.gmail_automatic_ingestion_warnings!.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="mb-6 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] p-4">
        <SectionTitle>System checks</SectionTitle>
        <p className="mb-3 text-xs text-[var(--trk-text-muted)]">Background requirements for automatic mail — you usually do not need to act on these.</p>
        <ul className="space-y-2">
          <CheckRow ok={pushReady} label="Push endpoint ready (server can receive alerts from Google)" />
          <CheckRow ok={trackingReady} label="Change tracking ready (Gmail bookmark in place)" />
          <CheckRow ok={subActive} label="Inbox subscription active (alerts turned on with Google)" />
        </ul>
      </div>

      <div className="mb-6 space-y-3">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onTest}
            disabled={testing}
            className={clsx(
              emailBtnFocus,
              "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[#3b82f6]/60 bg-[#3b82f6]/15 px-3 py-2 text-sm font-semibold text-[#93c5fd] hover:bg-[#3b82f6]/25 disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            {testing ? "Testing…" : "Test connection"}
          </button>
          {pushReady && !autoLive && (
            <button
              type="button"
              onClick={onRegisterWatch}
              disabled={registeringWatch || renewingWatch}
              className={clsx(
                emailBtnFocus,
                "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-emerald-700 bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {registeringWatch ? "Turning on…" : "Turn on automatic new-mail alerts"}
            </button>
          )}
          <button
            type="button"
            onClick={onConnectGmail}
            className={clsx(
              emailBtnFocus,
              "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[var(--trk-border-strong)] bg-[#0f1420] px-3 py-2 text-sm font-medium text-[var(--trk-text-muted)] hover:border-[var(--trk-text-muted)] hover:text-[var(--trk-text)]",
            )}
          >
            Reconnect / Sign in again
          </button>
        </div>
        <div className="border-t border-[var(--trk-border)] pt-3">
          <button
            type="button"
            onClick={onDisconnectClick}
            disabled={disconnecting}
            className={clsx(
              emailBtnFocus,
              "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-red-900/60 bg-red-950/20 px-3 py-2 text-sm font-medium text-red-300 hover:bg-red-950/35 disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            {disconnecting ? "Disconnecting…" : "Disconnect Gmail"}
          </button>
        </div>
      </div>

      <details
        className="rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)]"
        onToggle={(e) => setGmailOpsAdvancedOpen((e.target as HTMLDetailsElement).open)}
      >
        <summary
          className={clsx(
            emailModalBtnFocus,
            "cursor-pointer rounded-lg px-4 py-3 text-sm font-medium text-[var(--trk-text-muted)] hover:text-[var(--trk-text)]",
          )}
        >
          Advanced — manual sync & subscription tools
        </summary>
        <div className="space-y-4 border-t border-[var(--trk-border)] px-4 py-4 text-sm text-[var(--trk-text-muted)]">
          <p className="text-xs leading-relaxed text-[var(--trk-text-muted)]">
            For troubleshooting. Routine renewal is handled automatically in production where possible.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onSyncGmail}
              disabled={syncingGmail}
              className={clsx(
                emailBtnFocus,
                "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-sky-900/50 bg-sky-950/30 px-3 py-2 text-sm font-medium text-sky-200 hover:bg-sky-950/50 disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {syncingGmail ? "Working…" : "Fetch new mail once (manual)"}
            </button>
            <button
              type="button"
              onClick={onRegisterWatch}
              disabled={registeringWatch || renewingWatch}
              className={clsx(
                emailBtnFocus,
                "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-emerald-900/50 bg-emerald-950/25 px-3 py-2 text-sm font-medium text-emerald-200 hover:bg-emerald-950/40 disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {registeringWatch ? "…" : "Subscribe with Google again"}
            </button>
            <button
              type="button"
              onClick={() => onRenewWatch(false)}
              disabled={registeringWatch || renewingWatch}
              className={clsx(
                emailBtnFocus,
                "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[var(--trk-border)] bg-[#0f1420] px-3 py-2 text-sm font-medium text-[var(--trk-text-muted)] hover:border-[var(--trk-border-strong)] hover:text-[var(--trk-text)] disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {renewingWatch ? "…" : "Extend subscription (if due soon)"}
            </button>
            <button
              type="button"
              onClick={() => onRenewWatch(true)}
              disabled={registeringWatch || renewingWatch}
              className={clsx(
                emailBtnFocus,
                "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-sm font-medium text-amber-200/90 hover:bg-amber-950/35 disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              Force extend subscription
            </button>
          </div>
          <div className="rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] p-3 text-xs leading-relaxed text-[var(--trk-text-muted)]">
            <p className="mb-2 font-medium text-[#cbd5e1]">Support checklist</p>
            {loadingGmailHealth && <p>Loading…</p>}
            {!loadingGmailHealth && gmailHealth && (
              <>
                <p className="mb-2 text-[var(--trk-text-muted)]">
                  Automatic pipeline:{" "}
                  <span className="text-[var(--trk-text)]">{gmailHealth.automatic_ingestion_ready ? "ready" : "not ready"}</span>
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
    </div>
  );
}
