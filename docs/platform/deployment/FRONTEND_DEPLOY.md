# Frontend deploy (production tenants)

## Canonical deploy (new JS/CSS in the nginx image)

The SPA is copied into the image at build time (`infra/nginx/Dockerfile` → `COPY apps/web/dist/`). **Restarting the container alone does not update assets.**

Run:

```bash
/home/admin/trucking_erp/scripts/reload_nginx_web.sh
```

Equivalent manual steps:

```bash
cd /home/admin/trucking_erp/apps/web && npm run build
cd /home/admin/trucking_erp
docker compose -f docker-compose.yml build truckerp-nginx \
  && docker compose -f docker-compose.yml up -d truckerp-nginx
```

## Nginx **config** only (no `dist` change)

`default.conf` is bind-mounted in `docker-compose.yml`. After editing `infra/nginx/default.conf`:

```bash
cd /home/admin/trucking_erp
docker compose -f docker-compose.yml exec truckerp-nginx nginx -s reload
# or: docker compose -f docker-compose.yml restart truckerp-nginx
```

No image rebuild required for config-only changes.

## Cache behavior (why tenants do not need a hard refresh)

| Resource | Cache-Control | Reason |
|----------|---------------|--------|
| `/index.html` | `no-cache, no-store, must-revalidate` | Shell must not be reused from cache without a fresh fetch; it references current hashed `/assets/*` URLs. |
| `/assets/*` (Vite hashed JS/CSS) | `public, max-age=31536000, immutable` | Filename includes content hash; new deploy ⇒ new URLs ⇒ browsers fetch new files. Old files become unreachable from the new shell. |
| Other paths under `/` (SPA fallback, favicon, etc.) | Same as shell (no-store family) | Avoid stale non-hashed files; keeps behavior predictable. |

Flow after deploy:

1. Tenant opens or revisits the app → browser requests `/` or a client route → nginx serves `index.html` with **no-store** → always current script/link tags.
2. Browser loads `/assets/index-<newhash>.js` with **immutable** caching.
3. No service worker is registered for the web app (no `vite-plugin-pwa` / workbox in this repo).

## Verify in DevTools

1. **Document:** Network → reload page → select `index.html` (or first document) → **Response Headers** must include `Cache-Control: no-cache, no-store, must-revalidate`.
2. **Bundle:** Select `index-*.js` under `/assets/` → **Response Headers** must include `Cache-Control: public, max-age=31536000, immutable`.

## Service worker

There is **no** production service worker for `apps/web` (no registration in source, no PWA plugin). Stale shells are not caused by SW caching in this project.

## Cursor / local rules

`.cursor/` is gitignored; operators should treat **`docs/FRONTEND_DEPLOY.md`** and **`scripts/reload_nginx_web.sh`** as the maintained source of truth for deploy + cache behavior.
