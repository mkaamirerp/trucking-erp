import { useId, type KeyboardEvent, type ReactNode } from "react";
import { STATUS_BADGE, STATUS_COLORS } from "./constants";
import { emailSelectorFocus } from "./focusStyle";
import type { ActiveProvider } from "./types";
import type { EmailConfig } from "../../api";
import { isGmailConnected, isManualMailboxConnected, isMicrosoft365Connected } from "./types";

const PROVIDER_ORDER: ActiveProvider[] = ["gmail", "microsoft365", "other"];

type Props = {
  active: ActiveProvider;
  onSelect: (p: ActiveProvider) => void;
  config: EmailConfig | null;
};

function GmailIcon() {
  return (
    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-white" aria-hidden="true">
      <svg viewBox="0 0 24 24" className="h-6 w-6" aria-hidden="true" focusable="false">
        <path
          fill="#4285F4"
          d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
        />
        <path
          fill="#34A853"
          d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        />
        <path
          fill="#FBBC05"
          d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
        />
        <path
          fill="#EA4335"
          d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        />
      </svg>
    </div>
  );
}

function MicrosoftIcon() {
  return (
    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[#00a4ef]" aria-hidden="true">
      <svg viewBox="0 0 24 24" className="h-6 w-6 text-white" aria-hidden="true" focusable="false">
        <path fill="currentColor" d="M11.4 24H0L12 12 24 0h-4.2L8.4 12 11.4 24zm12.6 0h-4.2L12 12 4.2 24H0L12 0l12 24z" />
      </svg>
    </div>
  );
}

function MailIcon() {
  return (
    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[var(--trk-border-strong)]" aria-hidden="true">
      <svg viewBox="0 0 24 24" className="h-6 w-6 text-[var(--trk-text-muted)]" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" focusable="false">
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
        <path d="M22 6l-10 7L2 6" />
      </svg>
    </div>
  );
}

export default function EmailProviderSelector({ active, onSelect, config }: Props) {
  const headingId = useId();
  const gmailOn = isGmailConnected(config);
  const msOn = isMicrosoft365Connected(config);
  const otherOn = isManualMailboxConnected(config);

  const gmailBadgeKey = gmailOn ? config?.status ?? "CONNECTED" : "NOT_CONNECTED";
  const msBadgeKey = msOn ? config?.status ?? "CONNECTED" : "NOT_CONNECTED";
  const otherBadgeKey = otherOn ? config?.status ?? "CONFIGURED" : "NOT_CONNECTED";

  const cards: {
    id: ActiveProvider;
    title: string;
    icon: ReactNode;
    badgeKey: string;
    hint: string;
    tag?: string;
  }[] = [
    {
      id: "gmail",
      title: "Gmail",
      icon: <GmailIcon />,
      badgeKey: gmailBadgeKey,
      hint: "Google Workspace and consumer Gmail.",
      tag: "Recommended",
    },
    {
      id: "microsoft365",
      title: "Microsoft 365",
      icon: <MicrosoftIcon />,
      badgeKey: msBadgeKey,
      hint: "Outlook and Microsoft 365 mailboxes.",
    },
    {
      id: "other",
      title: "Other Mail",
      icon: <MailIcon />,
      badgeKey: otherBadgeKey,
      hint: "IMAP/SMTP or providers without OAuth here.",
    },
  ];

  return (
    <section aria-label="Email provider">
      <h2 id={headingId} className="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">
        Choose provider
      </h2>
      <div
        role="radiogroup"
        aria-labelledby={headingId}
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 lg:items-stretch"
      >
        {cards.map(({ id, title, icon, badgeKey, hint, tag }) => {
          const isActive = active === id;
          const badgeText = STATUS_BADGE[badgeKey] ?? badgeKey;
          const focusSibling = (next: ActiveProvider) => {
            onSelect(next);
            queueMicrotask(() => document.getElementById(`email-provider-option-${next}`)?.focus());
          };
          const onRadioKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
            const idx = PROVIDER_ORDER.indexOf(id);
            if (idx < 0) return;
            if (e.key === "ArrowRight" || e.key === "ArrowDown") {
              e.preventDefault();
              focusSibling(PROVIDER_ORDER[(idx + 1) % PROVIDER_ORDER.length]);
            } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
              e.preventDefault();
              focusSibling(PROVIDER_ORDER[(idx - 1 + PROVIDER_ORDER.length) % PROVIDER_ORDER.length]);
            } else if (e.key === "Home") {
              e.preventDefault();
              focusSibling(PROVIDER_ORDER[0]);
            } else if (e.key === "End") {
              e.preventDefault();
              focusSibling(PROVIDER_ORDER[PROVIDER_ORDER.length - 1]);
            }
          };
          return (
            <button
              key={id}
              id={`email-provider-option-${id}`}
              type="button"
              role="radio"
              aria-checked={isActive}
              tabIndex={isActive ? 0 : -1}
              aria-label={`${title}, ${badgeText}. ${isActive ? "Selected; details are below." : "Show setup for this provider."}`}
              onClick={() => onSelect(id)}
              onKeyDown={onRadioKeyDown}
              className={[
                emailSelectorFocus,
                "relative flex h-full min-h-[158px] w-full flex-col rounded-xl border p-4 text-left transition-all duration-200 ease-out",
                isActive
                  ? "border-[#3b82f6] bg-[#0f1828] shadow-[0_0_0_2px_rgba(59,130,246,0.28),0_12px_40px_rgba(0,0,0,0.45)] ring-2 ring-[var(--trk-accent)]/35"
                  : "border-[var(--trk-border)] bg-[var(--trk-bg)] hover:border-[var(--trk-border-strong)] hover:bg-[#0c1018]",
              ].join(" ")}
            >
              {tag && id === "gmail" && (
                <span className="absolute right-2 top-2 rounded bg-[#3b82f6]/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-accent)]">
                  {tag}
                </span>
              )}
              <div className="flex min-h-0 flex-1 flex-col justify-between gap-3 pr-10">
                <div className="flex items-start gap-3">
                  {icon}
                  <div className="min-w-0 flex-1">
                    <span
                      className={
                        isActive ? "text-base font-semibold text-[#f8fafc]" : "text-base font-semibold text-[var(--trk-text-muted)]"
                      }
                      aria-hidden="true"
                    >
                      {title}
                    </span>
                    <span
                      className={`mt-2 inline-block rounded px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[badgeKey] ?? STATUS_COLORS.NOT_CONFIGURED}`}
                      aria-hidden="true"
                    >
                      {badgeText}
                    </span>
                    {isActive && (
                      <p className="mt-1.5 text-[10px] font-bold uppercase tracking-wide text-[var(--trk-accent)]" aria-hidden="true">
                        Selected · panel below
                      </p>
                    )}
                  </div>
                </div>
                <p className="text-xs leading-snug text-[var(--trk-text-muted)]" aria-hidden="true">
                  {hint}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
