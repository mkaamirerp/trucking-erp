import type { EmailConfig } from "../../api";

export type ActiveProvider = "gmail" | "microsoft365" | "other";

export function isGmailConnected(config: EmailConfig | null): boolean {
  return config?.mailbox_type === "gmail" && config?.connection_mode === "oauth";
}

export function isMicrosoft365Connected(config: EmailConfig | null): boolean {
  return config?.mailbox_type === "microsoft365" && config?.connection_mode === "oauth";
}

export function isOtherManualMailboxType(t: string | undefined): boolean {
  return t === "other" || t === "imap";
}

export function isManualMailboxConnected(config: EmailConfig | null): boolean {
  if (!config) return false;
  return (
    config.connection_mode === "manual" &&
    !!config.email_address &&
    isOtherManualMailboxType(config.mailbox_type)
  );
}
