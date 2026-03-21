# Workspace Redesign — Design & Implementation Plan

## A. Existing Components/Pages Found

### Reusable
- **DispatchPage.tsx** — Full dispatch board; uses getDispatchBoard, updateLoad, createLoad, listTrucks, listDrivers, listTrailers, LoadNote API. Has LoadCard, StatusColumn, right drawer, header.
- **Layout.tsx** + **SidebarNav.tsx** — App shell (dark sidebar). Dispatch is standalone (no Layout).
- **LoadsListPage.tsx** — Uses Table, Card, listLoads; navigates to LoadDetailPage.
- **listLoads** API — Supports `status`, `page`, `size` filters. Can drive table view.
- **getDispatchBoard** API — Returns `Record<status, Load[]>`.
- **useMe** — Provides `user_id`, `tenant_id`, `roles` for preference keying.

### What Will Change
- DispatchPage shell and layout (table default, board optional).
- Header: add top-right user area (menu + layout switcher).
- Main content: ribbon tabs → table (default) or board (optional).
- Board: remove Delivered from columns; move to ribbon tab.
- Rows/cards: exactly 3 fields (Load #, Route, Status).
- Right drawer: keep; detail lives there.

### Where Layout Switcher and Drawer Live
- **Layout switcher** — In WorkspaceHeader (top-right), persisted via `useWorkspaceLayout(userId)`.
- **Drawer** — Same pattern as now: `drawerOpen`, `selectedLoad`; opens on row/card click.

### User Preference Persistence
- **Storage**: `localStorage`, key `truckerp_workspace_dispatch_layout_${userId}`.
- **Values**: `"table"` | `"board"`.
- **Default**: `"table"`.
- Backend API can be added later for cross-device sync.

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

## C. Table View (Layout C — Default)

- **Columns**: Load #, Route, Status (3 only).
- **Grouping**: By status within selected ribbon (e.g. Active → Unassigned, Assigned, Dispatched groups).
- **Row click**: Opens right drawer with full details.
- **Style**: Dark theme, compact, enterprise feel.

---

## D. Board View (Layout B — Optional)

- **Columns**: Only statuses in current ribbon. Delivered is never a column.
- **Cards**: 3 fields — Load #, Route, Status. Assign controls in card footer.
- **Row/card click**: Opens right drawer.

---

## E. File Change Summary (Planned)

| File                          | Action                                                |
|-------------------------------|-------------------------------------------------------|
| `apps/web/src/hooks/useWorkspaceLayout.ts` | New — persist layout preference                    |
| `apps/web/src/components/WorkspaceShell.tsx` | New — header, user area, layout switcher, slots |
| `apps/web/src/pages/DispatchPage.tsx`      | Major refactor — table default, ribbon, drawer    |
| `apps/web/src/App.tsx`                     | Possibly wrap Dispatch in Layout (TBD)            |

---

## F. Implementation Order

1. Add `useWorkspaceLayout` hook.
2. Add `WorkspaceShell` with header, user area, layout switcher.
3. Refactor DispatchPage: ribbon tabs, table view (default), board view (optional).
4. Remove Delivered from board columns; add Delivered ribbon tab.
5. Enforce 3 fields in table rows and board cards.
6. Wire layout preference into WorkspaceShell.

---

## G. Final Report (Post-Implementation)

### What Changed

- **DispatchPage.tsx** — Complete redesign:
  - Layout C (table) as default; Layout B (board) as optional.
  - Ribbon tabs: Active, In Transit, At Pickup, At Delivery, Delivered, Problem/Hold.
  - Table view: 3 columns only (Load #, Route, Status); grouped by status.
  - Board view: columns only for statuses in selected ribbon; **Delivered removed from columns** (tab only).
  - Right detail drawer unchanged; opens on row/card click.
  - Top-right: List/Board switcher + user menu (Profile, Settings, Sign out).
  - Dark theme (enterprise/operational feel).

- **useWorkspaceLayout.ts** — New hook for persisting layout preference per user.

- **docs/WORKSPACE_REDESIGN_PLAN.md** — Design plan and final report.

### What Was Reused

- All API calls: `getDispatchBoard`, `updateLoad`, `createLoad`, `listTrucks`, `listDrivers`, `listTrailers`, `getLoadNotes`, `addLoadNote`.
- Load model, types, handlers (assign, dispatch, status change).
- Right drawer structure and load detail content.
- Undo toast for status changes.

### Layout B Alternate View

- Included. User can switch via List/Board buttons in top-right.
- Board shows columns for statuses in the selected ribbon only.
- When "Delivered" tab is selected, board shows a single Delivered column (list-like).
- When "Active" tab is selected, board shows Unassigned, Assigned, Dispatched columns.

### User Preference Storage

- **Key**: `truckerp_workspace_layout_dispatch_${userId}` in `localStorage`.
- **Values**: `"table"` | `"board"`.
- **Default**: `"table"`.
- Persists per user (keyed by `me.user_id`). Same device/browser.

### Delivered Removal

- Delivered is **not** a permanent board column.
- It appears as a ribbon tab. When selected, only delivered loads are shown (table or single-column board).

### Limitations / Follow-up

- User menu "Settings" links to admin company profile; non-admins may get blocked (role guard).
- Profile link goes to Dashboard; a dedicated profile page can be added later.
- No backend user-preferences API; localStorage only. Cross-device sync would need an endpoint.
- WorkspaceShell not extracted as reusable component; logic is inline in DispatchPage. Can be extracted for settlements, onboarding review, etc.
