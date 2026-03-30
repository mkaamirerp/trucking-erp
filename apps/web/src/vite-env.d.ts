/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  readonly VITE_TENANT_ID?: string;
  readonly VITE_PUBLIC_API_BASE?: string;
  /** Cloudflare Turnstile site key (public). Required when login returns verification-required after abuse streak. */
  readonly VITE_TURNSTILE_SITE_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
