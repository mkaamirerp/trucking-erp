# Load numbering — owner decision (Amir, 2026-10-24)

**Status:** Product / load commercial contract (documentation lock). **No implementation** in this document.

**Authority:** Operator identifier rules align with [`.cursor/rules/owner-product-rules.mdc`](../../.cursor/rules/owner-product-rules.mdc) (“Load identifiers — do not mix”). Architecture and migration work must still respect [`load_trip/MASTER.md`](./MASTER.md) and tenant migration locks.

**Related investigation:** [`LOAD_NUMBERING_READ_ONLY_REPORT_2026-10-24.md`](./LOAD_NUMBERING_READ_ONLY_REPORT_2026-10-24.md).

---

## 1. Internal load number format

- **Pattern:** `<Mon>-<YY>-<NNNN>` — English three-letter month abbreviation (`Jan` `Feb` `Mar` `Apr` `May` `Jun` `Jul` `Aug` `Sep` `Oct` `Nov` `Dec`), two-digit year, hyphen, then a numeric suffix.
- **Examples:** `Oct-26-0001`, then `Oct-26-0002` for the same tenant and period.
- **Minimum width:** four digits for the suffix (`0001` … `9999`).
- **Overflow:** if a tenant mints more than `9999` loads in one calendar month, the suffix **grows** to five (or more) digits — **never truncate**, **never reuse** a number.

## 2. Which month and year

- Month and year on the formatted number are derived from the load row’s **creation time** in the **company time zone** (default **Toronto** / `America/Toronto`), **not** pickup date or stop dates.

## 3. Counter scope and concurrency

- Counter is **per tenant** and **per calendar month** (in that company time zone).
- Counter **resets** each month: first load in November 2026 is `Nov-26-0001`, not a continuation of October’s sequence.
- Numbers are minted **race-safely** (two dispatchers creating loads at the same instant get **different** numbers), using the same **database row lock + increment in one transaction** pattern as trip numbering (`mint_next_trip_number`).

## 4. One rule for every new load

- **Single minter** for all paths that create a new `loads` row:
  - Workspace **Create load** (promote),
  - **Email intake** linked load creation,
  - **Manual** `POST /api/v1/loads` (and any other commercial insert that today defaults `DRAFT-*` / `INT-*`).
- **Stop generating** `DRAFT-xxxx` and `INT-xxxx` for **new** loads after implementation.
- **Existing** loads **keep** their current `load_number` values — **no backfill**, **no renumbering**.

## 5. Internal vs broker reference

- **`load_number`** = TruckERP **internal** carrier load id (operator-facing “load number” in UI copy per owner product rules).
- **`broker_load_reference`** (“Broker load # / PO #”) = the **broker’s** reference from the rate confirmation or intake — **never** substitute one for the other.
- The **parser must not write** `load_number` (remains a TruckERP-owned field; broker refs stay on `broker_load_reference` / operational references).

---

## 6. Out of scope for this decision doc

- Trip numbering prefix admin (`tenant_dispatch_numbering`) — unchanged.
- Whether operators may **override** minted `load_number` on create/update — see read-only report §6; owner approval required before implementation.
