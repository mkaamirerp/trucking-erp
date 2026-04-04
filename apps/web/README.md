# Web app (Vite + React)

## Development (live reload — no rebuild)

So that **code changes reflect immediately** without running `npm run build`:

1. Start the API on port **8000** (your normal stack). For **optional local** iteration with bind mounts / `.env`, some engineers use the dev overlay — see repo root `docker-compose.dev.yml` and `./scripts/dev-up.sh`.  
   **Standard deployment / production-like:**  
   ```bash
   docker compose -f docker-compose.yml up -d
   ```
2. From repo root, run the Vite dev server:
   ```bash
   ./scripts/dev-web.sh
   ```
   Or: `cd apps/web && npm run dev`
3. Open **http://localhost:5173**. Edits in `src/` will hot-reload.

The dev server proxies `/api` to `http://127.0.0.1:8000`. Override with `API_PROXY_TARGET` if your API runs elsewhere.

## Production build

For deployment or when serving via nginx from built assets:

```bash
cd apps/web && npm run build
```

Output is in `dist/`. On production compose, **`dist` is copied into the nginx image** at image build time — use **`reload_nginx_web.sh`** (build + `docker compose build` + `up -d` for `truckerp-nginx`), not **`restart` only**. See **`docs/FRONTEND_DEPLOY.md`**.
