# Web app (Vite + React)

## Development (live reload — no rebuild)

So that **code changes reflect immediately** without running `npm run build`:

1. Start the API (e.g. with dev stack so API is on port 8000):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
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

Output is in `dist/`. With `docker-compose.dev.yml`, nginx serves `./apps/web/dist`; update it by rebuilding after changes if you are not using the Vite dev server.
