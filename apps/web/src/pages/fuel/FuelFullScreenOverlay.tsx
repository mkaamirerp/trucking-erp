import type { ReactNode } from "react";
import "./fuel-fullscreen-overlay.css";

type Props = {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  testId?: string;
  closeLabel?: string;
};

export default function FuelFullScreenOverlay({
  open,
  title,
  subtitle,
  onClose,
  children,
  testId,
  closeLabel = "Close",
}: Props) {
  if (!open) return null;

  return (
    <div className="fuel-fullscreen-overlay" data-testid={testId} role="dialog" aria-modal="true">
      <header className="fuel-fullscreen-overlay__header">
        <div className="min-w-0">
          <h1 className="text-sm font-semibold text-[var(--trk-text)]">{title}</h1>
          {subtitle ? (
            <p className="text-xs text-[var(--trk-text-muted)]">{subtitle}</p>
          ) : null}
        </div>
        <button
          type="button"
          className="fuel-fullscreen-overlay__close"
          onClick={onClose}
          data-testid="fuel-overlay-close"
          aria-label={closeLabel}
        >
          ✕ {closeLabel}
        </button>
      </header>
      <div className="fuel-fullscreen-overlay__body">{children}</div>
    </div>
  );
}
