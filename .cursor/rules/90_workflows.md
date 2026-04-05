# Workflows (DO THIS EVERY TIME)

## Workflow A: Safe change
1) Restate goal + affected modules/files.
2) Identify DB context (platform vs tenant).
3) Make minimal patch.
4) Run smallest check (single test / lint / endpoint smoke).
5) Summarize changes + risks + rollback.

## Workflow B: Debug a 500
1) Ask for exact endpoint + payload + recent logs (e.g. last 120 lines).
2) Identify which DB session the route uses.
3) Locate traceback line and root cause.
4) Patch minimal; add regression check if possible.
