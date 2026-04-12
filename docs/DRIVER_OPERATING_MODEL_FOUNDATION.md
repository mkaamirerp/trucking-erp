# Driver operating Model and dispatch Logic

“Driver assignment behavior depends on driver operating model.”

And that means the system cannot treat every driver as just a generic person with three pickers: driver, truck, trailer.

## First, the real business split

You do not have one driver type. You have operational subtypes.

### 1. Long-haul company driver

- usually has a dedicated truck
- often keeps the same truck continuously
- trailer may vary
- if truck goes to shop, dispatcher may temporarily reassign another truck

### 2. Owner-operator

- effectively dedicated to their own truck
- truck is part of their operating identity
- trailer may vary, depending on business model
- dispatch usually picks the driver and truck comes with them

### 3. City / local driver

- does not permanently own a truck
- truck is assigned per shift / per day / per job
- truck can be released after work
- morning dispatch may choose one truck, night shift may use the same truck later
- here the driver is operationally “orphan” from equipment until assigned

### 4. Shunt / yard driver

- not regular over-the-road dispatch
- often tied to yard moves, terminal moves, trailer repositioning
- equipment logic is different
- may require tractor assignment rules different from linehaul
- may need its own workflow entirely

So yes — this must exist in the system explicitly.

## The key principle

The system needs two separate concepts:

### A. Driver role

Examples:

- DRIVER
- DISPATCHER
- MECHANIC

### B. Driver operating profile

For drivers only:

- LONG_HAUL_COMPANY
- OWNER_OPERATOR
- CITY_LOCAL
- SHUNT_YARD
- STRAIGHT_TRUCK_LOCAL maybe later if you want it separate

The first is HR/security/business role.  
The second is dispatch/equipment behavior.

Without that second layer, dispatch logic will stay messy.

## What should be decided during onboarding/admin approval

When admin approves a driver, they should not only say “this person is a driver.”

They should also define the driver’s operational classification.

### Recommended onboarding fields for driver profile

#### Core driver operation fields

- **driver_operating_type**  
  - long_haul_company  
  - owner_operator  
  - city_local  
  - shunt_yard  
  - optional later: straight_truck_local  

- **employment_model**  
  - company_driver  
  - owner_operator  
  - contractor  

- **default_equipment_mode**  
  - dedicated_power_unit  
  - pooled_power_unit  
  - yard_pool  
  - owner_power_unit  

- **requires_trailer_for_primary_work** — true/false  

- **can_operate_articulated_vehicle** — true/false  

- **dispatch_assignment_pattern**  
  - driver_first  
  - truck_first  
  - shift_based  
  - yard_based  

This gives you real behavior, not just labels.

## License logic must be modeled separately

You are also right that CDL/class logic matters.

For Ontario, simplified:

- **AZ** = can drive tractor-trailer and generally broader heavy vehicle capability  
- **DZ** = straight truck / heavy single-unit, but not typical tractor-trailer combination work  

So license class is not the same as driver subtype, but it constrains what subtype is possible.

### Example

A driver may be marked as city_local, but:

- if they have AZ, they may operate tractor-trailer city work  
- if they have DZ, they may be limited to straight truck local work  

So the system should store:

- license_region  
- license_class_code  
- license_class_normalized  
- can_drive_straight_truck  
- can_drive_tractor_trailer  
- can_do_shunt  
- can_pull_trailer  
- maybe later hazardous or air brake endorsements  

Do not bury all logic inside the raw class text.  
Store the raw value, but also store normalized capability flags.

## Best model: capability-based, not only label-based

Because different places use different license names.

So keep both:

### Raw licensing data

- country  
- province/state  
- class code as written  
- endorsements  
- restrictions  

### Normalized capability layer

- can_operate_straight_truck  
- can_operate_tractor  
- can_operate_tractor_trailer  
- can_operate_yard_shunt  
- can_pull_multi_unit  
- air_brake_qualified maybe later  

That way Ontario AZ/DZ can be mapped properly, and later US CDL A/B/C or other countries can also fit.

## Dispatch logic should change by driver operating type

This is the big part.

The assignment strip should not behave the same for every driver.

### Scenario 1: Owner-operator

Dispatcher selects the driver.

System should then:

- auto-lock or strongly default the truck to the owner’s truck  
- trailer can remain selectable if business allows  
- truck picker may be hidden or read-only unless override is permitted  

**UX**

- Driver: searchable  
- Truck: auto-filled from owner truck, normally locked  
- Trailer: suggested / optional  
- Assign  

Here the true operational object is almost “unit + driver together.”

### Scenario 2: Long-haul company driver

Dispatcher selects the driver.

System should:

- strongly suggest their dedicated truck  
- allow override when truck is in shop or unavailable  
- trailer usually separate  

**UX**

- Driver: searchable  
- Truck: auto-filled from dedicated truck  
- Trailer: suggested or optional  
- warning if override from dedicated truck  

### Scenario 3: City/local driver

This is different.

The driver does not carry a dedicated truck.

So here:

- selecting driver should not auto-assume a truck  
- dispatcher may pick truck based on shift/day availability  
- trailer may or may not apply depending on local operation  

**UX**

Still same strip, but logic changes:

- Driver: searchable  
- Truck: required or strongly expected for this profile  
- Trailer: optional depending on equipment/job  
- no fake auto-fill unless there is a current shift assignment  

This is where your “driver is orphan” statement is exactly right.

### Scenario 4: Shunt driver

Potentially a different workflow.

They may:

- use terminal tractor / yard truck  
- move trailers, not linehaul loads  
- sometimes should not even use the standard freight load flow  

So I would be careful not to force shunt into the same load-assignment workflow as long-haul freight. It may fit later under trailer moves / yard jobs.

## So what should the assign strip do?

Not three dumb fields.

It should be policy-driven fields.

### Proposed behavior

**If no driver selected yet**

Show empty fields.

**When driver selected**

System reads:

- driver operating type  
- license capability  
- dedicated/default equipment relationship  
- current active shift assignment  
- availability/conflicts  

Then it decides how the form behaves.

### Example rules

- **owner_operator** — auto-fill truck from owned truck; truck read-only by default; trailer optional / suggested  
- **long_haul_company** — auto-fill dedicated truck if one exists; allow override; trailer suggested if recent/current attachment exists  
- **city_local** — no automatic truck assumption unless active shift assignment exists; require dispatcher to choose truck; trailer only if job requires  
- **shunt_yard** — probably redirect to different operation flow or show yard-equipment rules  

## Important distinction: permanent relationship vs temporary assignment

This is where many systems get messy.

You need both.

### Permanent / semi-permanent equipment relationship

Examples:

- owner-operator owns truck 104  
- long-haul driver usually runs truck 320  

This should live in something like:

- driver default unit  
- driver primary truck  
- owner_person_id on truck  
- dedicated assignment record  

### Temporary operational assignment

Examples:

- city driver got truck 205 for morning shift today  
- truck 205 released at 4 pm  
- night shift got same truck after that  

This must be stored separately, probably as:

- equipment_assignment_sessions  
- or driver_shift_equipment_assignments  

Fields like:

- driver_id  
- truck_id  
- trailer_id nullable  
- start_time  
- end_time nullable  
- assignment_reason  
- dispatch_assigned_by  
- status  

That is the only clean way to model city-driver reality.

## The system should know whether equipment is “sticky” or “shift-based”

For each driver profile, define:

**equipment_binding_mode**

- dedicated  
- owner_bound  
- shift_based  
- pooled  

This one field alone can guide a lot.

- **dedicated** — Long-haul company driver  
- **owner_bound** — Owner-operator  
- **shift_based** — City/local  
- **pooled / yard** — Shunt or special operations  

## Recommended design for onboarding/admin approval

When admin approves a driver, add a Driver Operations section.

**Driver Operations**

- Driver subtype: Long-haul company / Owner-operator / City/local / Shunt/yard  
- Equipment binding mode: Dedicated / Owner-bound / Shift-based / Pooled  
- Default truck  
- Default trailer if relevant  
- Home terminal / yard  
- Straight truck only? yes/no  
- Tractor-trailer capable? yes/no  
- Yard-only? yes/no  

**License & capability**

- License region  
- License class  
- Endorsements  
- Normalized capability flags  

That is where dispatch behavior starts, not later as a hack.

## Your Ontario example

A clean way to think about it:

### Ontario AZ

Likely allowed:

- tractor-trailer linehaul  
- city/local heavy work  
- shunt, depending on company policy  
- straight truck too  

### Ontario DZ

Likely allowed:

- straight truck  
- heavy single-unit local work  
- not standard tractor-trailer combination work  
- likely not normal shunt if articulated combination required  

So dispatch should not only know “this is a driver.”  
It should know:

- this driver is city_local  
- this driver is straight_truck_only  
- therefore do not offer tractor-trailer loads/equipment combinations  

That is the real business protection.

## Load assignment should maybe be equipment-first in some cases

You also made a very important point:

> Lets say i assign a load to unit 104 now the system must know what kind of driver this is so we dont need to select a truck and then select the driver for it

Exactly.

For some operations, the real anchor is the truck/unit, not the person.

### Example

Unit 104 is a dedicated long-haul tractor  
That unit usually has one driver or a narrow driver pool  
Dispatcher may think in terms of “give this load to unit 104”  

Then the system should:

- know what driver model applies to that unit  
- suggest compatible driver(s)  
- maybe auto-pick the dedicated driver if valid  

So later you may want two assignment modes:

**Driver-first mode**

Best for:

- owner-operators  
- long-haul driver-centric workflows  

**Equipment-first mode**

Best for:

- city operations  
- pooled equipment  
- truck-based planning  

You do not need to build both right this second, but the model should allow it.

## My recommendation for Phase 1

Do not overbuild the UI yet.  
But lock the model now.

### Lock these concepts now

**Driver profile additions**

- driver_operating_type  
- equipment_binding_mode  
- license_class_normalized  
- capability flags  

**Equipment relationship concepts**

- dedicated/default truck relationship  
- temporary shift-based assignment records  

**Assignment policy rules**

- owner operator = driver-first, truck auto-bound  
- long haul = driver-first, truck strongly suggested  
- city = truck required, driver may be chosen from pool, no permanent truck assumption  
- shunt = separate workflow or stricter specialized flow  

### What I would change in the current dispatch strip

Right now it sounds generic. I would evolve it into:

**Context-sensitive strip**

After selecting a driver, show:

- driver subtype  
- license class/capabilities  
- equipment mode  
- recommended truck behavior  

Example chips:

- Long Haul / Dedicated Unit / AZ / Tractor-Trailer Eligible  

Or:

- City Local / Shift-Based Unit / DZ / Straight Truck Only  

Then the strip can guide behavior.

## Strong recommendation on architecture

Do not hardcode all this only in the frontend.

The backend should expose assignment policy hints.

Something like:

- driver_operating_type  
- equipment_binding_mode  
- suggested_truck_id  
- suggested_trailer_id  
- truck_required  
- trailer_required  
- can_override_truck  
- can_dispatch_tractor_trailer  
- warnings  

That way the UI is driven by backend truth, not scattered logic.

## My conclusion

You are correct: this is deep logic and should be designed now as part of:

- driver onboarding  
- driver profile model  
- license normalization  
- equipment relationship model  
- dispatch assignment behavior  

The real fix is not “improve three fields.”  
The real fix is:

**different driver operating models must produce different dispatch assignment behavior.**

### Clean foundation I would lock

- A driver has both a business role and an operational subtype.  
- License class must be normalized into capability flags.  
- Equipment relationship must distinguish dedicated vs temporary shift assignment.  
- Dispatch assignment UI must change behavior based on driver subtype and capability.  
- City/local drivers should not be treated like dedicated long-haul drivers.  
- Owner-operators should be truck-bound by default.  
- Shunt should likely become its own operational path or at least its own strict subtype.  

The next best step is to turn this into a formal decision spec with:

- data model fields  
- allowed enums  
- dispatch behavior matrix  
- onboarding/admin workflow  
- validation rules  

## Team Driver Logic

Team driving is not one single model. The system must distinguish between at least two business cases because the operational setup may look similar, but the payment relationship is very different.

### 1. Company-driver team

In this model, both drivers are company drivers within the carrier’s operation.

They may be assigned to the same truck as a team, may alternate driving and sleeper time, and may both be associated with the same load or trip for operational purposes. Miles, trip activity, stop activity, and other dispatch-facing facts may be shared across the team arrangement, but payroll is still handled by the company according to its own pay rules.

In this scenario, the company pays the drivers directly. Team structure affects dispatch, trip planning, availability, compliance, and payroll calculations.

This means the system should eventually understand that two drivers can operate as one team unit for dispatch purposes; that both drivers may be attached to the same truck, load, or trip; that operational miles and trip events may be shared at the trip level; and that pay allocation between the two company drivers is a separate payroll rule problem and must not be assumed to be automatic or always equal.

### 2. Owner-operator team

In this model, the owner-operator is the business payee. The owner may have one or more drivers working with them, including a team-driving arrangement, but the carrier does not pay those drivers directly.

Operationally, those drivers still matter. They may need to appear in the system, be classified, be available for dispatch visibility, and be associated with loads, trucks, trips, and compliance records. Their miles, duty context, and trip participation may still matter operationally. However, from a settlement and pay perspective, the carrier pays the owner-operator, not the individual team driver.

This is a very important distinction. The system must not confuse “driver listed in the database” with “driver paid directly by the company.”

In this owner-operator team scenario, the team driver or co-driver may still exist in the database. The system may still track operational participation, assignment, miles, and compliance-related facts. The carrier settlement is still made to the owner-operator. The owner-operator handles payment to their own driver outside the carrier’s direct payroll relationship.

### Recurring teams, load-level assignment, and primary driver

Team pairing may be recurring, but dispatch must retain the ability to change team composition when assigning a specific load. The system should therefore avoid assuming that a team pairing is always permanently fixed for every dispatch decision.

Within a team arrangement, one driver may need to be designated as the primary driver. This is important operationally and also for insurance, liability, and responsibility tracking. The second driver remains part of the team and trip, but primary-driver identity must remain explicit.

Even where the carrier does not pay an individual driver directly, that driver must still exist in the system if they operate equipment or participate in the trip. This is required not only for dispatch visibility, but also for insurance, liability, compliance, and historical operational records. In owner-operator arrangements, the carrier may pay the owner-operator while still needing to track the co-driver as a real operational person in the system.

### Core planning principle

The system must separate who is operating the truck, who is associated to the trip or load operationally, who is paid by the carrier, and who is paid indirectly through an owner-operator relationship. These are not always the same thing.

A driver can be operationally active on the trip, visible in dispatch and records, and relevant for miles and trip history, but not a direct payroll payee of the carrier.

### Why this matters

Without this distinction, the system will eventually make payroll and settlement mistakes.

For example, a co-driver under an owner-operator could accidentally be treated like a company-payroll driver. A team trip could incorrectly create direct pay items for both drivers. Dispatch may understand the team correctly, but finance may not.

This is why team-driver logic must be tied not only to dispatch and trip participation, but also to the underlying business relationship.

### Planning direction

The document should make clear that future team-driver logic must account for at least company-paid team drivers and owner-operator team arrangements where the carrier pays only the owner-operator. It must keep operational participation distinct from pay relationship. Trip and load association for multiple drivers on one truck must be first-class. Later pay rule decisions for splitting or allocating mileage, revenue, or compensation in company-driver scenarios will sit on top of that separation—not the other way around.

### Important boundary

At this stage, this should remain a design topic only.

The document should not yet lock final payroll formulas, final settlement formulas, final database schema, final trip-to-driver allocation rules, or final UI behavior for team dispatching.

But it should explicitly lock the principle that team-driver logic is not one model, and that owner-operator team arrangements must remain separate from company-driver payroll logic.

### Team Driver Logic and Future Rate/Pay Rules

Team-driver operations will eventually interact with compensation rules, but those rules are not yet defined here. The current planning point is only that operational participation and payment relationship must be separated. This is especially important where owner-operators bring their own drivers: those drivers may appear in operations and tracking, while carrier payment still goes only to the owner-operator.

---

**Note for Cursor (and future editors):** Keep this section in the same deep explanatory style as the main document. Do not collapse it into bullets only. Preserve the distinction between operational participation and direct pay relationship. This is intentional: it prevents a future mistake where the system assumes every recorded driver is a payroll payee.
