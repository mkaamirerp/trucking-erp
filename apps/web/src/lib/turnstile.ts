/** Load Cloudflare Turnstile (explicit render). */

export type TurnstileRenderOptions = {
  sitekey: string;
  callback?: (token: string) => void;
  "error-callback"?: () => void;
  "expired-callback"?: () => void;
};

declare global {
  interface Window {
    turnstile?: {
      render: (container: HTMLElement, options: TurnstileRenderOptions) => string;
      remove: (widgetId: string) => void;
      reset: (widgetId: string) => void;
    };
  }
}

const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

let scriptPromise: Promise<void> | null = null;

export function loadTurnstileScript(): Promise<void> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Turnstile requires a browser"));
  }
  if (window.turnstile) {
    return Promise.resolve();
  }
  if (scriptPromise) {
    return scriptPromise;
  }
  scriptPromise = new Promise((resolve, reject) => {
    const prev = document.querySelector('script[src*="challenges.cloudflare.com/turnstile"]');
    if (prev) {
      prev.addEventListener("load", () => resolve(), { once: true });
      prev.addEventListener("error", () => reject(new Error("Turnstile script failed")), { once: true });
      return;
    }
    const s = document.createElement("script");
    s.src = SCRIPT_SRC;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Turnstile script failed"));
    document.head.appendChild(s);
  });
  return scriptPromise;
}
