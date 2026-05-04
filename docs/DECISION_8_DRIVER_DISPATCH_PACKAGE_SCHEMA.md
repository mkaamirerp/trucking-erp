# TruckERP — Decision 8 / Driver dispatch package & financial visibility (design draft)

**Status:** **DRAFT / NOT LOCKED** — pending owner review.  
**Not implementation:** no schema, API, UI, or migrations are prescribed here as deliverables; field names are **conceptual** unless noted.

**Related (locked):** `DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md`, `DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md`, `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`, `PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md`.

---

## Cross-check (Decisions 6 and 7)

| Source | Rule |
|--------|------|
| **Decision 6** | **Assign & Send** creates/sends a **versioned driver dispatch package** (composite action with save, assignment, package, send, audit). |
| **Decision 7** | **Package send** does **not** start **active execution** and does **not** set **`Trip.status = in_progress`** by itself. |

---

## A. Purpose

**Decision 8** defines the **Driver Dispatch Package**.

**Plain meaning:** When the dispatcher is on the **canonical Load Workspace / Load Verification** screen and clicks **Assign & Send**, the system sends the driver a package with the **operational** information needed to execute the trip/load.

**This package is not the same as:**

- `Trip.status`
- `Load.status`
- A custody event
- A pickup event
- A payroll event
- An accounting event

It is a **driver communication** package.

**Assign & Send means (conceptually):**

- Save verified load/trip info
- Create/update trip if needed
- Assign driver/truck/trailer
- Create a **versioned package snapshot**
- Send that package to the driver

**Assign & Send does NOT mean:**

- Driver started moving
- Pickup happened
- Custody started
- Load delivered
- Payroll started
- Dispatch board rewritten
- Broker rate was shown to the driver (see **§K**)

---

## B. Versioned package snapshot

The **Driver Dispatch Package** must be a **versioned snapshot**.

**Meaning:** The package records **what was sent to the driver at that time**.

**Example:** Package v1 sent at 8:00 PM includes pickup appointment 9:00 AM, pickup number PU123, trailer 53012, delivery appointment next day 7:00 AM. At 9:30 PM the dispatcher changes pickup appointment to 11:00 AM. Then **v1** must be marked **outdated** or **superseded**, and the system must prepare/send **Package v2**.

**Required versioning concepts (design labels — do not implement as DB columns yet):**

- `package_version`
- `sent_at`
- `sent_by_user_id`
- `driver_recipient_id`
- `viewed_at` (later)
- `accepted_at` (later, if supported)
- `superseded_by_package_id` or `outdated` flag (later)
- Reason for resend/update (later)
- Package snapshot payload (structured)

**Important:** Do **not** implement fields yet. This section is **design only**.

---

## C. Trip number rule — primary operational identifier

The **trip number** is the **most important** identifier in the driver package.

- **Trip number** belongs to the **`Trip` only.**
- **One trip = one trip number.**

**Do NOT** create a **new** trip number for:

- Second pickup
- Second delivery
- Added stop
- Added load inside the same trip
- Stop sequence
- Pickup number
- PO number

**Example:**

**Trip Number:** `IKL10001`

**Stop 1 — Pickup** — Pickup #: PU123, PO #: PO555, appointment May 6 9:00 AM, Boston, MA  
**Stop 2 — Pickup** — Pickup #: PU789, PO #: PO888, appointment May 6 2:00 PM, Worcester, MA  
**Stop 3 — Delivery** — Delivery #: DEL456, PO #: PO555 / PO888, appointment May 7 8:00 AM, Toronto, ON  

All stops remain under **Trip Number IKL10001**. There is **no** new trip number for the second pickup.

*(Aligned with **master index** §4 — Trip number rule and **`DISPATCH_TRIP_NUMBER_RULE.md`**.)*

---

## D. Trip header fields

Driver package **header** should include:

- `trip_number`
- Driver (identity/display)
- Truck
- Trailer
- `package_version`
- `sent_at` / sent time
- Assigned by / sent by (dispatcher)

**Reason:** Driver needs a clear **operational** header.

**Example:**

| Field | Value |
|-------|--------|
| Trip | IKL10001 |
| Driver | Mohammad |
| Truck | 788 |
| Trailer | 53012 |
| Package | v1 |
| Sent | 2026-05-04 8:00 PM |
| Sent by | Dispatcher Name |

---

## E. Trailer context / hook instructions

Trailer information must be **context-aware**.

**Reason:** Sometimes the driver is **at home** and must know **which trailer to hook**. Sometimes the driver is **already at the lane** with an **empty trailer attached** and does not need yard hook instructions.

**Conceptual instruction / context types** (not an implementation enum yet):

- `use_current_attached_trailer`
- `hook_trailer_at_yard`
- `pickup_empty_trailer_at_location`
- `bobtail_to_pickup`
- `trailer_unknown_dispatcher_will_update`

**Example A — driver at home:** Trip IKL10001, Truck 788, **Trailer to hook:** 53012, **Trailer location:** Yard / Mississauga, Pickup Boston 8:00 AM.

**Example B — driver in lane with trailer:** Trip IKL10001, Truck 788, **Trailer:** current attached 53012, **Instruction:** use current empty trailer, Pickup Boston 8:00 AM.

**Important:** Driver-visible trailer instruction should be generated from **assignment/equipment context** and later **configurable disclosure rules**. **Do not implement** this now; **design only**.

---

## F. Load/reference fields the driver may need

The driver package should support **operational references** the driver may need.

**Include conceptually (subject to disclosure — §I–J):**

**Load-level references:**

- Broker/customer name — **if allowed** by policy
- Broker load number
- PO number
- Pickup number
- Delivery number (if any)
- Additional references as needed
- Commodity
- Weight
- Equipment type
- Trailer type/size
- Temperature (reefer)
- Hazmat flag (later, if needed)

**PO / reference rule:**

- If the load already has a **PO number** field, use it as the source for **load-level** PO.
- **Future design** must allow references at **both** load level and **stop** level.

**Example:**

- **Load-level PO** = main commercial/customer PO
- **Stop-level pickup number** = pickup facility check-in reference
- **Stop-level delivery number** = delivery facility reference

**Do not confuse:**

| Identifier | Role |
|------------|------|
| Trip number | One per trip container |
| Broker load number | Broker/customer load id |
| PO number | Purchase order / commercial ref |
| Pickup number | Pickup-site reference |
| Delivery number | Delivery-site reference |
| Stop sequence number | Order of stops on the trip |

They are **different** identifiers.

---

## G. Stop details

For **every** pickup and delivery stop, the driver package should support:

- Stop sequence number
- Stop type: pickup / delivery / terminal / yard (yard later)
- Facility name
- Full address
- Appointment date
- Appointment time or **appointment window**
- Pickup number (if pickup)
- Delivery number (if delivery)
- PO number (if relevant)
- Contact name
- Contact phone
- Check-in notes
- Loading/unloading instructions
- Required documents
- Special instructions

**Example (abbreviated):**

**Stop 1 — Pickup** — ABC Warehouse, 123 Main St Boston MA; appointment May 6 2026 9:00–10:00 AM; Pickup # PU123; PO PO555; Contact John / 555-111-2222; Instructions: check in door 4, bring pickup number.

**Stop 2 — Delivery** — XYZ Receiver, 500 Industrial Rd Toronto ON; appointment May 7 2026 8:00 AM; Delivery # DEL456; PO PO555; Instructions: call receiver 30 minutes before arrival.

---

## H. Cross-border / special instructions

When applicable, the driver package should support:

- Customs broker name
- Customs broker phone/email
- PARS/PAPS or customs reference (later)
- Border crossing notes
- Seal number / seal instructions
- Temperature instructions
- Lumper/check-in instructions
- Safety/compliance notes
- Special handling notes

**Canada/US trucking:** important operationally; remain **package content design** only until implemented.

---

## I. Internal full snapshot vs driver-visible view

**Critical split:**

1. **Internal package snapshot** — Full system/audit record of what was prepared/sent; may include operational proof, **financial references**, document references, audit metadata, correction history, **hidden** fields.
2. **Driver-visible package view** — What the driver **actually sees** in the driver app.

The driver does **not** automatically see everything stored internally.

**Hidden by default from driver** (non-exhaustive; disclosure rules may narrow further):

- Broker gross rate
- Rate confirmation price
- Customer pricing
- Company margin
- Factoring/quick-pay details
- Internal audit notes
- Admin-only correction notes
- Broker negotiation notes
- AI/parsing diagnostics
- Internal confidence scores
- Payroll calculations — unless explicitly configured to show
- Settlement basis — unless explicitly configured to show
- Sensitive admin/compliance notes not meant for driver

**Reason:** The package is for **executing the trip safely**, not for exposing all internal company/accounting information.

---

## J. Configurable disclosure by driver type / relationship

**Driver-visible** content must be **configurable** by **driver type** / **driver relationship**.

**Examples of types** (product vocabulary TBD):

- Company driver
- Owner-operator
- Contractor
- Team driver
- Future partner/carrier driver

**Admin/config** should decide which fields each driver type **may** see.

The **full internal snapshot** can exist; the **driver-visible view** is **generated** from **disclosure rules**.

**Example — company driver (illustrative):**

- Visible: trip number, truck/trailer instruction, stops, appointments, pickup/delivery numbers, PO where allowed, driver-facing notes, allowed documents
- Hidden by default: broker rate, company margin

**Example — owner-operator / commission (illustrative):**

- Same operational fields
- **May optionally** show agreed trip amount or settlement basis **if** company policy allows
- Broker gross / ratecon amount remains **hidden by default** unless explicitly configured

**Important:** Do **not** implement disclosure config yet. **Save the design.**

---

## K. Financial visibility and rate fields — business rule

**Do not** force broker rate / ratecon price into the **driver package**.

**By default:**

- Broker gross / ratecon price → **hidden** from driver package view
- Company margin → **hidden**
- Internal accounting fields → **hidden**

**Reason:** In the industry, many carriers **do not** disclose true broker rate to O/O/drivers. TruckERP must remain **usable** in that market. The system should preserve **accounting truth internally** without **forcing** that disclosure in the dispatch package.

**However — do not corrupt accounting truth.**

Official broker/ratecon amount must remain **true internally**.

**Example:** Broker ratecon = **$1800**. Dispatcher tells O/O **$1500**. TruckERP must **not** edit the official **1800** down to **1500**.

**Future design direction (conceptual):**

| Layer | Concept |
|-------|---------|
| **Accounting / AR truth** | `broker_gross_amount` / `ratecon_amount` = e.g. 1800 |
| **Driver/payroll truth (O/O or commission)** | `driver_agreed_amount` / `settlement_basis_amount` = e.g. 1500 |

- Accounting can use **1800**.
- Payroll/settlement can use **1500** if that is company **pay policy** / agreed basis.

**Do not** implement these schema fields now unless they already exist in the product. **Design only.**

---

## L. Two pay branches (preserve for future docs)

Decision 8 **preserves** two driver/pay **concepts**; **full O/O settlement design is deferred.**

### Branch 1 — Regular / company driver

- No separate **driver-agreed load rate** required by default.
- Payroll from rules: miles, hours, salary, flat trip pay, accessorials, reimbursements, deductions, etc.
- Broker gross/ratecon stays **accounting/AR truth** only.
- Broker rate **hidden** from driver package by default.

### Branch 2 — Owner-operator / commission driver

- Later: distinct concepts **(a)** official broker/accounting amount **(b)** driver agreed / settlement basis.
- Payroll/settlement may use **driver_agreed_amount** while accounting uses **broker_gross_amount**.
- **Do not** overwrite broker gross to match driver agreed.
- Driver package **may optionally** show agreed trip amount per **driver type / pay policy**.
- Broker gross **hidden by default.**

**Current instruction:** Keep accounting truth simple: if ratecon says **1800**, internally it is **1800**. **No** fake editing or overwriting behavior. **No** O/O pay logic implementation until trip/dispatch decisions are further complete.

---

## M. UI field examples (future — not implemented now)

**Load Workspace** top actions remain (**Decision 6**): Save Draft, Save Ready, Assign, Assign & Send.

When **Assign & Send** uses a **driver package preview** (future), UI **may** include:

**Header:** Trip number, driver, truck, trailer, trailer instruction, package version, sent by, sent time.

**Sections/tabs (ideas):**

1. **Stops** — dates/times, facility/address, pickup/delivery numbers, PO, contacts, notes  
2. **References** — broker load number, PO, pickup/delivery numbers, other refs  
3. **Documents** — rate confirmation **internal**; driver-visible docs per disclosure; customs/border if applicable  
4. **Driver instructions** — check-in, trailer hook/bobtail/current trailer, temperature/seal/special handling, border/customs  
5. **Visibility / disclosure** — driver type, policy used, admin summary of hidden fields, **driver-visible preview**

**Financial UI rule:**

- Broker gross/ratecon **must not** appear in **driver-visible** preview **by default**.
- If an **agreed driver** amount is shown later, label **Agreed Trip Amount** or **Driver Settlement Basis** — **not** “Broker Rate.”
- Do **not** show pay fields until pay policy/disclosure config supports it.

---

## N. Hard boundaries

**Decision 8** package send (**design scope**) must **NOT** (by itself):

- Start **active execution** (**Decision 7**)
- Set **`Trip.status = in_progress`**
- Mark pickup arrived/loaded
- Start custody
- Mark delivered
- Trigger payroll
- Change accounting state
- Change broker gross amount
- Rewrite dispatch board
- Create a **second trip number** for a second pickup (or any stop)
- Expose **hidden financial/internal** fields to the driver **by default** (**§I–J**)

---

*End of Decision 8 draft — driver dispatch package & financial visibility.*
