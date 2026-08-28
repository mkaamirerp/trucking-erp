# TruckERP documentation archive

This directory contains historical snapshots, completed handoffs, superseded implementation reports, and one-off forensic/proof documents that are still useful for history but are **not authoritative current guidance**.

## Rules

- Do not use archived files as the source of truth for current production behavior.
- Prefer current architecture locks, runbooks, `.cursor/rules/`, generated schema, and active design documents under `docs/`.
- When an archived document contains a still-valid permanent rule, that rule should also exist in the current canonical document before the historical file is moved here.
- Do not archive fixtures, generated schema artifacts, contracts, or active parser/load/trip design documents merely because they are old.

## Why archive instead of delete

TruckERP has accumulated implementation reports and handoff notes that explain why certain safety boundaries exist. Keeping those records preserves useful history while preventing them from competing with current documentation.

## Current archived snapshots

- `codex-notes-2026-01-01.txt` — historical development snapshot; explicitly not the production runbook.
