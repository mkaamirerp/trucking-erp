# Workspace Redesign — Design & Implementation Plan

> **STATUS: SUPERSEDED FOR CURRENT DISPATCH PRODUCT OWNERSHIP (2026-08-28).**  
> This file remains a historical implementation record for the legacy `DeprecatedDispatchPage` UI. Its statements describing `/dispatch` / `DeprecatedDispatchPage` as the active dispatch workspace are superseded by [`000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md`](./000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md): **Trip page = Trip Container = Dispatch Control Center**. The legacy page is visual salvage / compatibility only; do not add new operational business logic here.

**As of 2026-04:** This document mixes original design notes with a post-implementation summary. **Routing and shell names below match `apps/web/src/App.tsx` and the components at that historical point.**

## A. Current components / pages (historical snapshot)

### App shell & routing
- **`App.tsx`** — `/dispatch` is wrapped in **`Layout`** (same as dashboard, loads, fleet, etc.). There is **no** separate “dispatch without layout” route.
- **`Layout.tsx`** — Full-width shell: **`TopNav`** + scrollable `<main>` (not `SidebarNav`; that component does not exist in this repo).
- **`DeprecatedDispatchPage.tsx`** — Legacy dispatch workspace snapshot: ribbon tabs, **table** or **board** view, driver column, load cards/columns. Uses **`getDispatchBoard`**, **`listTrucks`**, **`listDrivers`**, **`listTrailers`**. **Unassigned** loads navigate to **`LoadWorkspacePage`** at `/loads/:id?dispatchAssign=1` (canonical load workspace + assignment). Other statuses open an **in-page summary modal** with a button to **Edit load** → same **`LoadWorkspacePage`**. **New load** → `/loads/new` (`LoadWorkspacePage` without id).
- **`LoadsListPage.tsx`** — `listLoads` with search/pagination; row navigation uses **`OPS.LOAD_DETAIL`** → **`LoadWorkspacePage`** (`/loads/:id`). **New** uses **`OPS.LOAD_NEW`**.
- **`LoadWorkspacePage.tsx`** — Canonical create/edit/assign workspace for loads (replaces any legacy “load detail page” naming in older docs).
- **`listLoads`** — Supports `status`, `page`, `size`, `search`, etc. (see `apps/web/src/api.ts`).
- **`getDispatchBoard`** — Returns `Record<status, Load[]>`.
- **`useMe`** — `user_id`, tenant, roles for UI gates.
- **`useWorkspaceLayout`** (`apps/web/src/hooks/useWorkspaceLayout.ts`) — Persists `table` | `board` per `(workspaceId, userId)` under prefix `truckerp_workspace_layout_*` (see implementation for exact key).

### Implemented behavior (high level)
- Ribbon filters table + board; **Delivered** is a tab, not a permanent board column.
- Table columns include **Load #**, **Trip #** (read-only from load), **Route**, **Status** (see `DeprecatedDispatchPage.tsx`).

### Where layout switcher and modal live
- **Layout switcher** — Top toolbar on `DeprecatedDispatchPage` (List/Board), backed by **`useWorkspaceLayout("dispatch", me?.user_id, defaultMode)`**. First-time default for the hook argument is **`"board"`** in code (user override stored in `localStorage` once set).
- **Quick summary** — `selectedLoad` modal for non-unassigned row/card clicks; deep editing is delegated to **`LoadWorkspacePage`**.

### User preference persistence
- **Storage**: `localStorage`, keys via `storageKey(workspaceId, userId)` in `useWorkspaceLayout.ts` (prefix `truckerp_workspace_layout`).
- **Values**: `"table"` | `"board"`.
- Backend user-preferences API: not implemented; local only.

---

## B. Ribbon Tab → Status Mapping

| Ribbon Tab    | Statuses Shown                                           |
|---------------|----------------------------------------------------------|
| Active        | unassigned, assigned, dispatched                         |
| In Transit    | arrived_pickup, in_transit, arrived_delivery             |
| At Pickup     | arrived_pickup                                           |
| At Delivery   | arrived_delivery                                         |
| Delivered     | delivered                                                |
| Problem/Hold  | issue_hold                                               |

Selected tab filters both table and board views.

---

## C. Table View (Layout C)

- **Columns**: Load #, Trip #, Route, Status (see live `DeprecatedDispatchPage.tsx`).
- **Grouping**: By status within selected ribbon (e.g. Active → Unassigned, Assigned, Dispatched groups).
- **Row click**: Unassigned → **`LoadWorkspacePage`** with dispatch-assign query; other statuses → summary modal (link into workspace for edits).
- **Style**: Dark theme, compact, enterprise feel.

---

## D. Board View (Layout B — Optional)

- **Columns**: Only statuses in current ribbon. Delivered is not a permanent multi-column lane set (handled via ribbon / single delivered column pattern).
- **Cards**: Broker headline, load + **trip** line, route, miles pills, meta, status; assigned/unassigned footers per design in `DeprecatedDispatchPage.tsx`.
- **Row/card click**: Same routing/modal behavior as table rows.

---

## E. File inventory (implemented vs optional extraction)

| File | Status |
|------|--------|
| `apps/web/src/hooks/useWorkspaceLayout.ts` | **Implemented** — shared hook for dispatch (and reusable for other workspaces). |
| `apps/web/src/components/WorkspaceShell.tsx` | **Not extracted** — header/switcher/modal logic lives **inside** `DeprecatedDispatchPage.tsx`. |
| `apps/web/src/pages/DeprecatedDispatchPage.tsx` | **Implemented legacy surface** — ribbon, table/board, modal, navigation to `LoadWorkspacePage`; not the current operational product foundation. |
| `apps/web/src/pages/LoadWorkspacePage.tsx` | **Implemented** — canonical load editor / assignment surface. |
| `apps/web/src/App.tsx` | **Dispatch uses `Layout`** — same shell as other operational pages. |

---

## F. Implementation order (historical checklist)

Completed in tree: `useWorkspaceLayout`, `DeprecatedDispatchPage` ribbon + table/board, Delivered handling, `LoadWorkspacePage` integration, `App.tsx` layout wrap. Optional future step: extract **`WorkspaceShell`** if another surface needs the same header/switcher pattern.

---

## G. Final Report (Post-Implementation)

### What changed (summary)

- **DeprecatedDispatchPage.tsx** — Ribbon (Active, In Transit, At Pickup, At Delivery, Delivered, Problem/Hold), **table** and **board** modes, trip-aware display, driver column; **navigation** to **`LoadWorkspacePage`** for deep edits and unassigned assignment; quick-read **modal** for other statuses.
- **useWorkspaceLayout.ts** — Persists table/board preference per user and workspace id (`dispatch`).
- **Layout + TopNav** — Dispatch is a normal routed page under the shared app chrome.

### What was reused / boundaries

- **Read-heavy dispatch APIs:** `getDispatchBoard`, `listTrucks`, `listDrivers`, `listTrailers`.
- **Load mutations** (save, assign, dispatch transitions, notes, etc.) live in **`LoadWorkspacePage`** and related API helpers — not as a scattered set of `updateLoad`/`createLoad` calls inside `DeprecatedDispatchPage` (verify `apps/web/src/pages/LoadWorkspacePage.tsx` and `api.ts` for the exact methods).
- **Load types** from `@/api` / backend `LoadResponse` (including **`trip_number`** read model).

### Layout B Alternate View

- Included. User can switch via List/Board buttons in top-right.
- Board shows columns for statuses in the selected ribbon only.
- When "Delivered" tab is selected, board shows a single Delivered column (list-like).
- When "Active" tab is selected, board shows Unassigned, Assigned, Dispatched columns.

### User preference storage

- **Key pattern**: `truckerp_workspace_layout_dispatch_${userId}` (see `storageKey()` in `useWorkspaceLayout.ts` — includes workspace id + user id, with `"anon"` when logged-in id not yet available).
- **Values**: `"table"` | `"board"`.
- **Hook default argument** in `DeprecatedDispatchPage.tsx`: `"board"` until/unless user has a stored preference.
- Same-device/browser only until a backend prefs API exists.

### Delivered Removal

- Delivered is **not** a permanent board column.
- It appears as a ribbon tab. When selected, only delivered loads are shown (table or single-column board).

### Limitations / Follow-up

- User menu "Settings" links to admin company profile; non-admins may get blocked (role guard).
- Profile link goes to Dashboard; a dedicated profile page can be added later.
- No backend user-preferences API; localStorage only. Cross-device sync would need an endpoint.
- WorkspaceShell not extracted as reusable component; logic is inline in DeprecatedDispatchPage. Can be extracted for settlements, onboarding review, etc.
