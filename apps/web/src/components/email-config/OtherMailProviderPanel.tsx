import { clsx } from "clsx";
import type { Dispatch, SetStateAction } from "react";
import type { EmailConfig, EmailConfigUpdatePayload } from "../../api";
import { STATUS_BADGE, STATUS_COLORS, formatLastTested } from "./constants";
import { isManualMailboxConnected } from "./types";
import ProviderPanelFlash from "./ProviderPanelFlash";
import { emailBtnFocus, emailFieldFocus } from "./focusStyle";

export type OtherMailProviderPanelProps = {
  config: EmailConfig | null;
  form: EmailConfigUpdatePayload;
  setForm: Dispatch<SetStateAction<EmailConfigUpdatePayload>>;
  saving: boolean;
  testing: boolean;
  testingInbound: boolean;
  testingOutbound: boolean;
  syncingOther: boolean;
  disconnecting: boolean;
  panelFlash?: { variant: "success" | "error"; message: string } | null;
  onDismissPanelFlash?: () => void;
  onSave: () => void;
  onTest: () => void;
  onTestInbound: () => void;
  onTestOutbound: () => void;
  onSyncOther: () => void;
  onDisconnectClick: () => void;
};

export default function OtherMailProviderPanel({
  config,
  form,
  setForm,
  saving,
  testing,
  testingInbound,
  testingOutbound,
  syncingOther,
  disconnecting,
  panelFlash,
  onDismissPanelFlash,
  onSave,
  onTest,
  onTestInbound,
  onTestOutbound,
  onSyncOther,
  onDisconnectClick,
}: OtherMailProviderPanelProps) {
  const manualConnected = isManualMailboxConnected(config);
  const showConnectedSummary = manualConnected && !!config;

  return (
    <div className="rounded-xl border border-[var(--trk-border)] bg-[var(--trk-bg)] p-6">
      <h2 className="mb-1 text-xl font-semibold tracking-tight text-[var(--trk-text)]">Other Mail</h2>
      <p className="mb-5 text-sm text-[var(--trk-text-muted)]">
        For Yahoo, Zoho, cPanel mail, or any host that gives you IMAP and SMTP — same first-class setup flow as the OAuth
        providers.
      </p>

      {panelFlash && onDismissPanelFlash && (
        <ProviderPanelFlash variant={panelFlash.variant} message={panelFlash.message} onDismiss={onDismissPanelFlash} />
      )}

      {!manualConnected && (
        <div className="mb-6 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] p-4 text-sm text-[var(--trk-text-muted)]">
          <p className="font-medium text-[var(--trk-text)]">Status: Not connected</p>
          <p className="mt-1 leading-relaxed">
            Enter your mailbox and server details below, save, then run the tests to confirm inbound and outbound mail.
          </p>
        </div>
      )}

      {showConnectedSummary && config && (
        <div className="mb-6 rounded-lg border border-emerald-900/40 bg-emerald-950/10 p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">Connection</h3>
          <div className="space-y-3 text-sm">
            <p className="text-[var(--trk-text)]">
              <span className="text-[var(--trk-text-muted)]">Mailbox </span>
              {config.email_address}
              {config.display_name ? ` · ${config.display_name}` : ""}
            </p>
            {config.reply_to && (
              <p className="text-[var(--trk-text-muted)]">
                Reply-To: <span className="text-[var(--trk-text)]">{config.reply_to}</span>
              </p>
            )}
            <p className="text-[var(--trk-text-muted)]">
              IMAP: <span className="text-[var(--trk-text)]">{config.imap_host}:{config.imap_port}</span> (
              {config.imap_security || (config.use_ssl ? "ssl" : "starttls")}) · SMTP:{" "}
              <span className="text-[var(--trk-text)]">
                {config.smtp_host}:{config.smtp_port}
              </span>{" "}
              ({config.smtp_security || "starttls"})
            </p>
            <p className="text-[var(--trk-text-muted)]">
              Connection:{" "}
              <span className={STATUS_COLORS[config.connection_status || config.status] ?? "text-[var(--trk-text-muted)]"}>
                {STATUS_BADGE[config.connection_status || config.status] || config.connection_status || config.status}
              </span>
            </p>
            <p className="text-[var(--trk-text-muted)]">
              Last inbound test: {formatLastTested(config.last_inbound_test_at)} · Last outbound test:{" "}
              {formatLastTested(config.last_outbound_test_at)}
            </p>
            <div className="rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] p-3">
              <p className="mb-2 font-medium text-[var(--trk-text-muted)]">IMAP ingestion</p>
              <ul className="space-y-1 text-[var(--trk-text-muted)]">
                <li>
                  UIDVALIDITY / last UID:{" "}
                  <span className="text-[var(--trk-text)]">
                    {config.imap_uidvalidity != null ? String(config.imap_uidvalidity) : "—"} /{" "}
                    {config.imap_last_seen_uid != null ? String(config.imap_last_seen_uid) : "—"}
                  </span>
                </li>
                <li>
                  Last sync:{" "}
                  <span className="text-[var(--trk-text)]">
                    {config.last_inbound_sync_at ? formatLastTested(config.last_inbound_sync_at) : "—"}
                  </span>
                  {config.last_sync_status && (
                    <>
                      {" "}
                      <span className="text-[var(--trk-text-muted)]">· status</span>{" "}
                      <span className="text-[var(--trk-text)]">{config.last_sync_status}</span>
                    </>
                  )}
                </li>
                {config.last_sync_error && <li className="text-red-400">Sync error: {config.last_sync_error}</li>}
              </ul>
              <p className="mt-2 text-xs text-[var(--trk-text-muted)]">
                Incremental sync uses server UID state. Production may add a scheduled fallback using the same endpoint.
              </p>
            </div>
            {config.last_error_message && <p className="text-sm text-red-400">{config.last_error_message}</p>}
            <div className="flex flex-wrap gap-2 pt-2">
              <button
                type="button"
                onClick={onTestInbound}
                disabled={testingInbound}
                className={clsx(
                  emailBtnFocus,
                  "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[#3b82f6]/40 bg-[#3b82f6]/10 px-3 py-2 text-sm font-semibold text-[var(--trk-accent)] hover:bg-[#3b82f6]/20 disabled:opacity-50",
                )}
              >
                {testingInbound ? "Testing…" : "Test inbound (IMAP)"}
              </button>
              <button
                type="button"
                onClick={onTestOutbound}
                disabled={testingOutbound}
                className={clsx(
                  emailBtnFocus,
                  "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[var(--trk-border-strong)] bg-[var(--trk-surface)] px-3 py-2 text-sm font-medium text-[var(--trk-text-muted)] hover:border-[var(--trk-text-muted)] hover:text-[var(--trk-text)] disabled:opacity-50",
                )}
              >
                {testingOutbound ? "Testing…" : "Test outbound (SMTP)"}
              </button>
              <button
                type="button"
                onClick={onSyncOther}
                disabled={syncingOther}
                className={clsx(
                  emailBtnFocus,
                  "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-sky-900/50 bg-sky-950/30 px-3 py-2 text-sm font-medium text-sky-200 hover:bg-sky-950/50 disabled:opacity-50",
                )}
              >
                {syncingOther ? "Syncing…" : "Sync new mail (IMAP)"}
              </button>
            </div>
            <div className="mt-3 border-t border-emerald-900/30 pt-3">
              <button
                type="button"
                onClick={onDisconnectClick}
                disabled={disconnecting}
                className={clsx(
                  emailBtnFocus,
                  "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-red-900/60 bg-red-950/20 px-3 py-2 text-sm font-medium text-red-300 hover:bg-red-950/35 disabled:opacity-50",
                )}
              >
                {disconnecting ? "Disconnecting…" : "Disconnect mailbox"}
              </button>
            </div>
          </div>
        </div>
      )}

      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">Server settings (IMAP & SMTP)</h3>
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">Mailbox email</label>
            <input
              type="email"
              value={form.email_address}
              onChange={(e) => setForm((f) => ({ ...f, email_address: e.target.value }))}
              placeholder="mailbox@example.com"
              className={clsx(
                emailFieldFocus,
                "w-full min-h-[44px] rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] placeholder-[var(--trk-text-muted)]",
              )}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">From name</label>
            <input
              type="text"
              value={form.display_name ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
              placeholder="Optional"
              className={clsx(
                emailFieldFocus,
                "w-full min-h-[44px] rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] placeholder-[var(--trk-text-muted)]",
              )}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-[var(--trk-text-muted)]">Reply-To (optional)</label>
            <input
              type="text"
              value={form.reply_to ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, reply_to: e.target.value }))}
              placeholder="Optional"
              className={clsx(
                emailFieldFocus,
                "w-full min-h-[44px] rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] placeholder-[var(--trk-text-muted)]",
              )}
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="is_primary_mailbox_other"
            checked={form.is_primary ?? true}
            onChange={(e) => setForm((f) => ({ ...f, is_primary: e.target.checked }))}
            className={clsx(emailFieldFocus, "h-5 w-5 rounded border-[var(--trk-border)]")}
          />
          <label htmlFor="is_primary_mailbox_other" className="text-sm text-[var(--trk-text-muted)]">
            Primary mailbox for this workspace
          </label>
        </div>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="rounded-lg border border-[var(--trk-border)] p-4">
            <h3 className="mb-3 text-sm font-semibold text-[var(--trk-text)]">Inbound (IMAP)</h3>
            <div className="space-y-3">
              <input
                type="text"
                value={form.imap_host ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, imap_host: e.target.value }))}
                placeholder="IMAP host"
                className={clsx(
                  emailFieldFocus,
                  "w-full min-h-[44px] rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] placeholder-[var(--trk-text-muted)]",
                )}
              />
              <input
                type="number"
                value={form.imap_port ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, imap_port: parseInt(e.target.value, 10) || undefined }))}
                placeholder="Port"
                className={clsx(
                  emailFieldFocus,
                  "w-full min-h-[44px] rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] placeholder-[var(--trk-text-muted)]",
                )}
              />
              <input
                type="text"
                value={form.imap_username ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, imap_username: e.target.value }))}
                placeholder="Username"
                className={clsx(
                  emailFieldFocus,
                  "w-full min-h-[44px] rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] placeholder-[var(--trk-text-muted)]",
                )}
              />
              <input
                type="password"
                value={form.imap_password ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, imap_password: e.target.value }))}
                placeholder="App password (leave blank to keep existing)"
                className={clsx(
                  emailFieldFocus,
                  "w-full min-h-[44px] rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] placeholder-[var(--trk-text-muted)]",
                )}
              />
              <div>
                <label className="mb-1 block text-xs text-[var(--trk-text-muted)]">IMAP security</label>
                <select
                  value={form.imap_security ?? "ssl"}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      imap_security: e.target.value,
                      use_ssl: e.target.value === "ssl",
                    }))
                  }
                  className={clsx(
                    emailFieldFocus,
                    "w-full min-h-[44px] rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)]",
                  )}
                >
                  <option value="ssl">SSL/TLS (e.g. port 993)</option>
                  <option value="starttls">STARTTLS</option>
                  <option value="none">None (not recommended)</option>
                </select>
              </div>
            </div>
          </div>
          <div className="rounded-lg border border-[var(--trk-border)] p-4">
            <h3 className="mb-3 text-sm font-semibold text-[var(--trk-text)]">Outbound (SMTP)</h3>
            <div className="space-y-3">
              <input
                type="text"
                value={form.smtp_host ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, smtp_host: e.target.value }))}
                placeholder="SMTP host"
                className={clsx(
                  emailFieldFocus,
                  "w-full min-h-[44px] rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] placeholder-[var(--trk-text-muted)]",
                )}
              />
              <input
                type="number"
                value={form.smtp_port ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, smtp_port: parseInt(e.target.value, 10) || undefined }))}
                placeholder="Port"
                className={clsx(
                  emailFieldFocus,
                  "w-full min-h-[44px] rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] placeholder-[var(--trk-text-muted)]",
                )}
              />
              <input
                type="text"
                value={form.smtp_username ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, smtp_username: e.target.value }))}
                placeholder="Username"
                className={clsx(
                  emailFieldFocus,
                  "w-full min-h-[44px] rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] placeholder-[var(--trk-text-muted)]",
                )}
              />
              <input
                type="password"
                value={form.smtp_password ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, smtp_password: e.target.value }))}
                placeholder="App password (leave blank to keep existing)"
                className={clsx(
                  emailFieldFocus,
                  "w-full min-h-[44px] rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] placeholder-[var(--trk-text-muted)]",
                )}
              />
              <div>
                <label className="mb-1 block text-xs text-[var(--trk-text-muted)]">SMTP security</label>
                <select
                  value={form.smtp_security ?? "starttls"}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      smtp_security: e.target.value,
                      use_tls: e.target.value === "starttls",
                    }))
                  }
                  className={clsx(
                    emailFieldFocus,
                    "w-full min-h-[44px] rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)]",
                  )}
                >
                  <option value="ssl">SSL (e.g. port 465)</option>
                  <option value="starttls">STARTTLS (e.g. port 587)</option>
                  <option value="none">None (not recommended)</option>
                </select>
              </div>
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onSave}
              disabled={saving || !form.email_address}
              className={clsx(
                emailBtnFocus,
                "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[#3b82f6] bg-[#3b82f6] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#2563eb] disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {saving ? "Saving…" : "Save settings"}
            </button>
            <button
              type="button"
              onClick={onTestInbound}
              disabled={testingInbound}
              className={clsx(
                emailBtnFocus,
                "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[var(--trk-border-strong)] bg-[var(--trk-surface)] px-4 py-2 text-sm font-medium text-[var(--trk-text-muted)] transition hover:border-[var(--trk-text-muted)] hover:text-[var(--trk-text)] disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {testingInbound ? "Testing…" : "Test inbound"}
            </button>
            <button
              type="button"
              onClick={onTestOutbound}
              disabled={testingOutbound}
              className={clsx(
                emailBtnFocus,
                "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[var(--trk-border-strong)] bg-[var(--trk-surface)] px-4 py-2 text-sm font-medium text-[var(--trk-text-muted)] transition hover:border-[var(--trk-text-muted)] hover:text-[var(--trk-text)] disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {testingOutbound ? "Testing…" : "Test outbound"}
            </button>
            <button
              type="button"
              onClick={onTest}
              disabled={testing}
              className={clsx(
                emailBtnFocus,
                "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[var(--trk-border-strong)] bg-[var(--trk-surface)] px-4 py-2 text-sm font-medium text-[var(--trk-text-muted)] transition hover:border-[var(--trk-text-muted)] hover:text-[var(--trk-text)] disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {testing ? "Testing…" : "Test IMAP (legacy)"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
