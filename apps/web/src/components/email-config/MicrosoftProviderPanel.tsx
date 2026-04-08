import { clsx } from "clsx";
import type { EmailConfig } from "../../api";
import { STATUS_BADGE, STATUS_COLORS, formatLastTested } from "./constants";
import { isMicrosoft365Connected } from "./types";
import ProviderPanelFlash from "./ProviderPanelFlash";
import { emailBtnFocus } from "./focusStyle";

export type MicrosoftProviderPanelProps = {
  config: EmailConfig | null;
  /** null = still loading status from API */
  microsoftOAuthConfigured: boolean | null;
  disconnecting: boolean;
  renewingMs: boolean;
  syncingMs: boolean;
  panelFlash?: { variant: "success" | "error"; message: string } | null;
  onDismissPanelFlash?: () => void;
  onConnectMicrosoft: () => void;
  onDisconnectClick: () => void;
  onRenewSubscription: (force: boolean) => void;
  onSyncNow: () => void;
};

function SectionTitle({ children }: { children: string }) {
  return <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-[#64748b]">{children}</h3>;
}

function msAutomaticMailSummary(config: EmailConfig): {
  headline: string;
  body: string;
  tone: "live" | "amber" | "muted";
} {
  const st = (config.ms_graph_subscription_status || "").toLowerCase();
  const syncErr = (config.ms_graph_last_sync_error || "").toLowerCase();
  const hasSubId = !!(config.ms_graph_subscription_id && String(config.ms_graph_subscription_id).trim());
  const exp = config.ms_graph_subscription_expiration_at;
  const expDate = exp ? new Date(exp) : null;
  const expFuture = !!(expDate && !Number.isNaN(expDate.getTime()) && expDate.getTime() > Date.now());

  const webhookBlocked =
    st.includes("skipped_no_notification") ||
    st.includes("notification_url") ||
    syncErr.includes("webhook") ||
    syncErr.includes("notification_url");

  if (webhookBlocked) {
    return {
      headline: "Automatic mail not connected yet",
      body:
        "Your server team must configure the Microsoft webhook URL before new mail can arrive automatically. You can still pull mail with “Sync now” below.",
      tone: "amber",
    };
  }

  if (!hasSubId) {
    return {
      headline: "Automatic mail: subscription not active",
      body:
        "You are signed in, but inbox notifications are not registered yet. Try “Sign in with Microsoft again”, or contact support if this persists.",
      tone: "amber",
    };
  }

  if (!exp) {
    return {
      headline: "Automatic mail: almost there",
      body:
        "A subscription is registered. Renewal timing will show here once Microsoft returns an expiration — you can still use Sync now anytime.",
      tone: "muted",
    };
  }

  if (!expFuture) {
    return {
      headline: "Subscription needs renewal",
      body:
        "The Graph notification subscription may be expired. Use renew actions below or sign in again so TruckERP can re-register.",
      tone: "amber",
    };
  }

  return {
    headline: "Automatic mail: On",
    body: "Microsoft can notify TruckERP when new mail arrives, and changes sync through Microsoft Graph.",
    tone: "live",
  };
}

export default function MicrosoftProviderPanel({
  config,
  microsoftOAuthConfigured,
  disconnecting,
  renewingMs,
  syncingMs,
  panelFlash,
  onDismissPanelFlash,
  onConnectMicrosoft,
  onDisconnectClick,
  onRenewSubscription,
  onSyncNow,
}: MicrosoftProviderPanelProps) {
  const connected = isMicrosoft365Connected(config);
  const oauthDisabled = microsoftOAuthConfigured === false;

  if (!connected || !config) {
    return (
      <div className="rounded-xl border border-[#1e293b] bg-[#0a0e14] p-6">
        <h2 className="mb-1 text-xl font-semibold tracking-tight text-[#f1f5f9]">Microsoft 365</h2>
        <p className="mb-5 text-sm text-[#64748b]">
          First-class option for Outlook and Microsoft 365 — same idea as Gmail: sign in once, then sync and optional
          automatic intake.
        </p>
        {panelFlash && onDismissPanelFlash && (
          <ProviderPanelFlash variant={panelFlash.variant} message={panelFlash.message} onDismiss={onDismissPanelFlash} />
        )}
        {microsoftOAuthConfigured === null && (
          <p className="mb-4 text-xs text-[#64748b]" role="status" aria-live="polite">
            Checking whether Microsoft sign-in is enabled on this server…
          </p>
        )}
        {oauthDisabled && (
          <div
            className="mb-5 rounded-lg border border-amber-900/50 bg-amber-950/15 p-4 text-sm"
            role="status"
            aria-live="polite"
          >
            <p className="font-medium text-amber-100">Microsoft sign-in is not configured on this deployment</p>
            <p className="mt-2 leading-relaxed text-[#94a3b8]">
              The API needs a Microsoft Entra (Azure AD) app registration and environment variables on the server,
              including <span className="font-mono text-xs text-[#e8edf5]">MICROSOFT_CLIENT_ID</span> and{" "}
              <span className="font-mono text-xs text-[#e8edf5]">MICROSOFT_CLIENT_SECRET</span>, plus callback and
              webhook URLs as documented for your environment. After values are set, restart the API and refresh this
              page.
            </p>
          </div>
        )}
        {!oauthDisabled && (
          <div className="mb-5 rounded-lg border border-[#1e293b] bg-[#0d111a] p-4 text-sm text-[#94a3b8]">
            <p className="font-medium text-[#cbd5e1]">Before you connect</p>
            <p className="mt-2 leading-relaxed">
              Your administrator must register redirect URIs in Microsoft Entra for this TruckERP host. If anything is
              missing, sign-in will fail after you leave this page.
            </p>
          </div>
        )}
        <button
          type="button"
          onClick={onConnectMicrosoft}
          disabled={oauthDisabled}
          className={clsx(
            emailBtnFocus,
            "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[#00a4ef] bg-[#0078d4] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#006cbd] disabled:cursor-not-allowed disabled:opacity-40",
          )}
        >
          Connect with Microsoft 365
        </button>
      </div>
    );
  }

  const connLabel = STATUS_BADGE[config.status] ?? config.status;
  const connPillClass = STATUS_COLORS[config.status] ?? STATUS_COLORS.NOT_CONNECTED;
  const auto = msAutomaticMailSummary(config);

  const subStatusRaw = config.ms_graph_subscription_status || config.connection_status;
  const subStatusDisplay = subStatusRaw
    ? subStatusRaw.replace(/_/g, " ")
    : "Not reported yet";

  const borderAuto =
    auto.tone === "live"
      ? "border-emerald-900/45 bg-emerald-950/15"
      : auto.tone === "amber"
        ? "border-amber-900/45 bg-amber-950/10"
        : "border-[#1e293b] bg-[#0d111a]";

  const textAutoHead =
    auto.tone === "live"
      ? "text-emerald-200"
      : auto.tone === "amber"
        ? "text-amber-100"
        : "text-[#e8edf5]";

  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#0a0e14] p-6">
      <h2 className="mb-1 text-xl font-semibold tracking-tight text-[#f1f5f9]">Microsoft 365</h2>
      <p className="mb-5 text-sm text-[#64748b]">Outlook and Microsoft 365 mail through Microsoft Graph.</p>

      {panelFlash && onDismissPanelFlash && (
        <ProviderPanelFlash variant={panelFlash.variant} message={panelFlash.message} onDismiss={onDismissPanelFlash} />
      )}

      <div className="mb-6 rounded-lg border border-[#1e293b] bg-[#0d111a] p-4">
        <SectionTitle>Connection</SectionTitle>
        <p className="text-sm text-[#94a3b8]">
          Signed in as:{" "}
          <span className="font-medium text-[#e8edf5]">{config.oauth_account_email || config.email_address}</span>
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-[#64748b]">Status</span>
          <span className={`rounded-md px-2.5 py-1 text-xs font-semibold ${connPillClass}`}>{connLabel}</span>
        </div>
        {config.last_error_message && <p className="mt-3 text-sm text-red-400">{config.last_error_message}</p>}
      </div>

      <div className={`mb-6 rounded-lg border p-4 ${borderAuto}`}>
        <SectionTitle>Automatic mail</SectionTitle>
        <p className={`text-lg font-semibold ${textAutoHead}`}>{auto.headline}</p>
        <p className="mt-1 text-sm text-[#94a3b8]">{auto.body}</p>
        <dl className="mt-4 space-y-2 text-sm text-[#94a3b8]">
          <div className="flex flex-wrap gap-x-2 gap-y-1">
            <dt className="text-[#64748b]">Last Microsoft signal</dt>
            <dd className="text-[#e8edf5]">
              {config.ms_graph_last_notification_at ? formatLastTested(config.ms_graph_last_notification_at) : "None yet"}
            </dd>
          </div>
          <div className="flex flex-wrap gap-x-2 gap-y-1">
            <dt className="text-[#64748b]">Last sync into TruckERP</dt>
            <dd className="text-[#e8edf5]">
              {config.ms_graph_last_delta_sync_at
                ? formatLastTested(config.ms_graph_last_delta_sync_at)
                : config.last_inbound_sync_at
                  ? formatLastTested(config.last_inbound_sync_at)
                  : "—"}
            </dd>
          </div>
          <div className="flex flex-wrap gap-x-2 gap-y-1">
            <dt className="text-[#64748b]">Subscription renew by</dt>
            <dd className="text-[#e8edf5]">
              {config.ms_graph_subscription_expiration_at
                ? formatLastTested(config.ms_graph_subscription_expiration_at)
                : "—"}
            </dd>
          </div>
        </dl>
      </div>

      <div className="mb-6 rounded-lg border border-[#1e293b] bg-[#0d111a] p-4">
        <SectionTitle>Mailbox & subscription details</SectionTitle>
        <p className="mb-3 text-xs text-[#64748b]">
          Technical detail for admins. If a line shows “—”, nothing has been recorded yet — that is normal right after
          setup.
        </p>
        <ul className="space-y-2 text-sm text-[#94a3b8]">
          <li>
            <span className="text-[#64748b]">Inbox subscription </span>
            <span className="text-[#e8edf5]">
              {config.ms_graph_subscription_id ? "Registered" : "Not registered yet"}
            </span>
          </li>
          <li>
            <span className="text-[#64748b]">Subscription state </span>
            <span className="text-[#e8edf5]">{subStatusDisplay}</span>
          </li>
          <li>
            <span className="text-[#64748b]">Change tracking (delta) </span>
            <span className="text-[#e8edf5]">{config.ms_graph_delta_cursor_present ? "Ready" : "Not set yet"}</span>
          </li>
          {(config.ms_graph_last_sync_status || config.ms_graph_last_sync_error) && (
            <li>
              <span className="text-[#64748b]">Last sync note </span>
              <span className="text-[#e8edf5]">
                {config.ms_graph_last_sync_status ?? "—"}
                {config.ms_graph_last_sync_error ? ` — ${config.ms_graph_last_sync_error}` : ""}
              </span>
            </li>
          )}
        </ul>
      </div>

      <div className="mb-2 space-y-3">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onSyncNow}
            disabled={syncingMs}
            className={clsx(
              emailBtnFocus,
              "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[#00a4ef]/50 bg-[#0078d4]/20 px-3 py-2 text-sm font-semibold text-[#7dd3fc] hover:bg-[#0078d4]/30 disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            {syncingMs ? "Syncing…" : "Sync now"}
          </button>
          <button
            type="button"
            onClick={() => onRenewSubscription(false)}
            disabled={renewingMs}
            className={clsx(
              emailBtnFocus,
              "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[#334155] bg-[#0f1420] px-3 py-2 text-sm font-medium text-[#94a3b8] hover:border-[#475569] hover:text-[#e8edf5] disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            {renewingMs ? "…" : "Renew subscription (if due)"}
          </button>
          <button
            type="button"
            onClick={() => onRenewSubscription(true)}
            disabled={renewingMs}
            className={clsx(
              emailBtnFocus,
              "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-sm font-medium text-amber-200/90 hover:bg-amber-950/35 disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            Force renew subscription
          </button>
          <button
            type="button"
            onClick={onConnectMicrosoft}
            disabled={oauthDisabled}
            className={clsx(
              emailBtnFocus,
              "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[#334155] bg-[#0f1420] px-3 py-2 text-sm font-medium text-[#94a3b8] hover:border-[#475569] hover:text-[#e8edf5] disabled:cursor-not-allowed disabled:opacity-40",
            )}
          >
            Sign in with Microsoft again
          </button>
        </div>
        <div className="border-t border-[#1e293b] pt-3">
          <button
            type="button"
            onClick={onDisconnectClick}
            disabled={disconnecting}
            className={clsx(
              emailBtnFocus,
              "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-red-900/60 bg-red-950/20 px-3 py-2 text-sm font-medium text-red-300 hover:bg-red-950/35 disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            {disconnecting ? "Disconnecting…" : "Disconnect Microsoft 365"}
          </button>
        </div>
      </div>
    </div>
  );
}
