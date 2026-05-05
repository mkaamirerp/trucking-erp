# TruckERP — Decision 13 / Trip exception, recovery, repower workflow and payroll guard

**Status:** **LOCKED** — business model and payroll guard for operational exceptions after assignment or during **`in_progress`** execution; **not** schema or UI implementation.

**Related:** `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`, **Decisions 8–12**, `PHASE3L_D_OWNER_DECISION_CHECKLIST.md`, `PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md`, `PAYROLL_TRIP_TRACING.md`.

---

## A. Purpose

**Decision 13** defines how TruckERP handles **operational exceptions** after a trip is **assigned** or already **`in_progress`**.

**Examples:**

- Truck breakdown  
- Driver unavailable  
- Driver refusal  
- Accident  
- Trailer issue  
- Border / customs delay  
- Repower required  
- Recovery driver required  
- Broker/customer cancels after dispatch  
- Load must return to **planning queue**  
- Load must continue on **another trip**  

This decision **separates**:

1. **Trip** exception / recovery **truth**  
2. **Load** commercial **truth**  
3. **Custody / handoff** **truth**  
4. **Payroll / settlement review** **truth**  

This is **not** implementation. This is the **locked business model**.

---

## B. Core principle

- A **trip exception** does **not** automatically **cancel** the **load**.  
- A **load** remains the **same** commercial/broker/customer load unless **broker/customer cancellation** truly happens.  
- If an **assigned** trip **cannot finish** its assigned responsibility, the system **must preserve** the **original trip** and create **explicit** recovery / handoff / repower **facts**.  
- **Do not** silently overwrite the **original** driver/truck/trailer **assignment** on the original trip.  
- **Do not** replace the **original trip** driver with the **recovery** driver on the **same** trip row.

---

## C. Base dispatcher recovery options

When something happens, the dispatcher should have these **base recovery options** (**locked**):

1. **Repower / reassign** load to **another trip**  
2. **Drop / handoff** at terminal or safe location  
3. **Return** load to **Ready / Unassigned Load Planning Queue**  
4. **Cancel load** with broker/customer  
5. Put load/trip on **Issue / Recovery Hold**  

**Meaning:**

1. **Repower / reassign:** same commercial load continues; **original trip preserved**; **recovery trip** gets a **new trip number**; custody/handoff **links** the chain.  
2. **Drop / handoff:** freight/trailer handed to terminal, yard, shop, safe parking, or other **structured** location; **custody event required**.  
3. **Return to planning queue:** load remains valid; dispatch has not assigned replacement yet; load returns to planning pool **explicitly** (**Decision 9**).  
4. **Cancel with broker/customer:** commercial load is **truly** cancelled; **`Load.status`** may become **`cancelled`** per **Decision 11** — **not** the same thing as “trip exception” alone.  
5. **Issue / Recovery Hold:** dispatcher needs time to decide; **no** false delivery/cancellation; requires **visible** issue/recovery state in a **later** implementation.

---

## D. Original trip vs recovery trip

**Locked:**

If a **new** driver/truck/trailer is sent to **recover** or **finish** the freight, create a **new `Trip`** with a **new Trip Number**.

- **Do not** edit the **original** trip and silently replace the original driver/truck/trailer.  
- **Original trip** keeps its **original trip number**.  
- **Recovery trip** gets its **own** trip number.  
- The **same Load** can continue across **both** trips through **`TripLoad`** membership and custody/handoff **history**.

**Example — good vs bad:**

| | |
|--|--|
| **Bad** | Trip **IKL10001** driver changed from original O/O to company driver on the **same** trip row. |
| **Good** | Trip **IKL10001** remains the **original** failed/incomplete trip (original driver/equipment **preserved** on that trip). Trip **IKL10002** is the **recovery** trip. Load links across both via **`TripLoad`** + custody events. |

**Illustrative narrative:**

- **Trip A:** IKL10001 — owner-operator commission driver, truck 788, Toronto yard → Boston delivery, assigned amount $1,000.  
- **Problem:** breakdown near Albany.  
- **Commercial load:** same broker/customer load, still **active**, not cancelled, not delivered yet.  
- **Recovery:** **Trip B:** IKL10002 — company driver or other O/O; action: recover at Albany, deliver Boston; **`assigned` → `in_progress` → `completed`**.  

---

## E. Albany breakdown example

**Scenario:** Driver leaves **Toronto yard** with a **trip number** going to **Boston** (O/O on commission or company driver on miles). Halfway near **Albany**, an exception occurs: breakdown, trailer issue, accident, driver unavailable, or similar.

**Dispatch may:** send a new driver/truck from nearby; send equipment from Toronto terminal; hold/recover later.

**System behavior (locked):**

- **Original trip** is **preserved** with **original trip number**.  
- **Original driver assignment** remains on the **original trip**.  
- If a **recovery** driver is sent, create a **new trip** with **new trip number**.  
- The **commercial load** is **not** cancelled unless broker/customer cancels it.  
- **Custody/handoff** event links original trip to recovery state or recovery trip.  
- **Payroll** for the **original** driver on the **original** trip is **`review_required`** if assigned responsibility was **not** completed (**§F**).

---

## F. Payroll guard — critical rule

**Locked:**

If a driver does **not** complete the **assigned responsibility** for **that trip** because of exception, repower, breakdown, refusal, accident, trailer issue, recovery event, or other operational problem:

- Payroll/settlement for **that trip** must be flagged **`review_required`**.  
- It **cannot** be processed as “normal complete” until **admin/payroll** resolves it.  
- The system must **not** automatically pay the **full** agreed amount.  
- The system must **not** automatically pay **zero** without review.  
- **Block** payroll processing for that trip’s settlement line until **admin/payroll** decides adjustment.

**Possible admin/payroll outcomes** (illustrative — not final enum):

- No pay  
- Pay deadhead only  
- Pay loaded miles completed  
- Pay partial miles  
- Pay flat recovery/attempt amount  
- Pay partial agreed amount  
- Pay full agreed amount **by approval**  
- Other manual adjustment  
- Hold for investigation  

**Required future payroll review facts** (design sketch — **do not implement** now):

- `original_trip_id`, `original_trip_number`  
- `driver_id`  
- Driver type / pay policy snapshot  
- `reason_code`  
- `exception_event_id`  
- `recovery_trip_id` (if any)  
- Miles completed (if available)  
- Deadhead/recovery miles (if available)  
- Original agreed amount / settlement basis (if applicable)  
- Admin decision + reason  
- `decided_by_user_id`, `decided_at`  
- Audit event  

---

## G. Planned handoff vs failed/incomplete assignment

**This distinction is locked.**

**Payroll block** is **not** based only on whether the **Load** is finally **delivered** to the receiver.

**Payroll block** is based on whether the **trip** driver **completed that trip’s assigned responsibility**.

### Case A — Planned handoff / terminal linehaul

Driver was assigned to bring freight **Boston → terminal** (or similar). City driver delivers **later**. Load is **not** finally delivered to **final receiver**, but **original** driver **completed** what they were assigned.

**System meaning:**

- **Trip A** **`completed`** normally (per assignment scope).  
- **Load** may remain **active** / at terminal / awaiting next trip.  
- **Custody/handoff** event **required**.  
- Payroll is **not** automatically blocked **solely** because load is not delivered to final receiver.

**Example:** O/O linehaul **Boston → Mississauga terminal**; drops loaded trailer or stages freight; city driver delivers next day. **Original O/O** completed **his** assignment.

### Case B — Failed / incomplete assignment

Driver was assigned **Toronto → Boston final delivery**. Truck breaks down near **Albany**; another driver finishes delivery on **Trip B**.

**System meaning:**

- **Trip A** = exception / **incomplete** assignment relative to **stated** final-delivery responsibility.  
- **Load** continues through **Trip B**.  
- Payroll/settlement for **Trip A** driver = **`review_required`**.  
- **Trip B** payroll is calculated **separately** per **Trip B** driver’s pay policy.

This distinction **must** stay clear in docs and future product (see **§H** — future “assignment responsibility” concept).

---

## H. Assignment responsibility type / completion expectation

The **future** system needs to know **what** the driver was assigned to complete.

**Possible concept names** (not locked strings): `trip_completion_policy`, `assigned_responsibility_type`, `assignment_goal`, `responsibility_scope`.

**Examples of scopes:**

- `final_delivery_required`  
- `terminal_handoff_required`  
- `yard_drop_required`  
- `recovery_segment`  
- `linehaul_segment`  
- `city_delivery_segment`  

**Not** implementation now — **preserve** the need.

**Rule:**

- If the driver **completed** the **assigned responsibility**, payroll can proceed **normally** (subject to usual policy).  
- If the driver **did not** complete assigned responsibility due to **exception/recovery**, payroll **review** is **required** (**§F**).

---

## I. Recovery trip payroll

**Recovery** driver/trip payroll is **separate** from **original** trip payroll.

- **Recovery company driver:** miles (loaded/empty), accessorials, hourly/flat per policy.  
- **Recovery O/O:** separate agreed amount / commission / recovery contract — **not** auto-tied to original O/O’s **$1,000** (or other) assignment.  

**Do not** force **one load → one payroll outcome** when **multiple trips/drivers** touched it.

---

## J. Relationship to Decision 12 custody

**Cross-check Decision 12:**

Recovery/repower **must** create **explicit** custody/handoff **facts** (append-only chain), e.g.:

- Breakdown reported  
- Recovery requested  
- Trailer handed off at Albany  
- Replacement driver hooked trailer  
- Terminal handoff  
- Trailer-to-trailer transfer  
- Recovery trip assigned  

**Do not** model recovery as **only** a status string. **Do not** lose the **custody chain**.

---

## K. Relationship to Decision 11 (`Load.status`)

**Cross-check Decision 11:**

- **`Load.status`** = commercial/readiness — **not** trip exception diary.  
- A trip exception does **not** automatically set **`Load.status = cancelled`**.  
- **`Load.status = cancelled`** only when broker/customer commercial load is **truly** cancelled (or company retires the load per policy).  
- If load stays valid but original trip failed, keep commercial load **active** and choose recovery/repower/planning action.

---

## L. Relationship to Decision 10 scheduling guard

**Cross-check Decision 10:**

Recovery trip **assignment** must still respect **scheduling/resource conflict** rules unless **supervisor override** with reason and audit.

**Emergency recovery** may require override, e.g.:

- Nearby truck already has **future** trip assigned → dispatcher **overrides** to recover breakdown  
- Trailer swap / team / emergency  

Override **must** be **reason-coded** and **audited**.

---

## M. Relationship to Decision 8 / O/O financial branch

**Cross-check Decision 8** (**draft** until locked):

- Original driver is **O/O** on commission/agreed amount; **does not** complete assigned responsibility → payroll **must not** blindly pay **full** agreed amount.  
- **Example:** $1,000 trip; breakdown near Albany; company driver **recovers** and delivers → original O/O settlement **`review_required`**; admin decides partial/no/full/manual.  
- **Driver package** financial visibility remains **separate** and configurable; **do not** expose internal broker gross/ratecon by default.

---

## N. What Decision 13 does **NOT** do

Decision 13 **does not**:

- Implement exception tables  
- Implement payroll review tables  
- Implement recovery UI  
- Implement trip assignment endpoint  
- Implement custody events  
- Implement settlement calculation  
- Define final **reason-code** enum  
- Define full **RBAC**  
- Rewrite dispatch board  
- Change **`Load.status`** or **`Trip.status`** **schema**  

It **locks** the **business model** and **payroll guard**.

---

## O. Open implementation items (after Decision 13)

Remain **open** (non-exhaustive):

- Exact exception **event** table/schema  
- Exact **reason-code** enum  
- Exact **recovery action** API  
- Exact **recovery** UI  
- Exact **payroll review** table/schema  
- Exact **payroll block** mechanism  
- Exact **admin adjustment** UX  
- Exact **RBAC** for override/recovery/payroll decision  
- Exact **custody** event linkage  
- Exact **ELD/miles** evidence integration  
- Exact **settlement/payrun** integration  
- Exact **notifications** to driver  
- Exact **board/timeline** display  

**No longer “open” as principles** (now **locked** by Decision 13):

- Whether **original trip** is preserved vs mutating assignment in place  
- Whether **recovery trip** gets a **new trip number**  
- Whether load is **automatically** cancelled on exception  
- Whether payroll should be **blocked** on incomplete assignment  
- Whether **planned terminal handoff** differs from **failed** assignment  

---

*End of Decision 13 — trip exception, recovery, repower workflow and payroll guard.*
