# TruckERP WhatsApp Driver Messaging Design

**Status:** Design checkpoint — no implementation yet.  
**Date:** 2026-09-25  
**Purpose:** Preserve the agreed TruckERP WhatsApp driver-messaging direction so it can be implemented later without repeating the design discussion.

---

# 1. Core decision

TruckERP should **not build its own messaging system**.

WhatsApp already provides the transport layer:

```text
message delivery
phone / WhatsApp identity
inbound replies
outbound delivery
message status
read / delivered events
media
images
PDF / documents
location
buttons / interactive replies
templates
webhooks
```

TruckERP should only build the trucking/business integration around that existing platform.

Preferred production direction:

```text
TruckERP backend
    ↓
Meta WhatsApp Cloud API (direct)
    ↓
Driver WhatsApp
```

Inbound:

```text
Driver WhatsApp
    ↓
Meta webhook
    ↓
TruckERP backend
    ↓
validate driver + tenant + load/trip context
    ↓
store message / perform approved domain action
```

**TruckERP remains the authority. WhatsApp is only another input/output channel.**

---

# 2. Direct Cloud API vs intermediary

Current preference is **direct Meta WhatsApp Cloud API** rather than putting another provider between TruckERP and WhatsApp.

Reason:

- Meta already provides the actual WhatsApp messaging platform.
- Direct integration avoids an extra per-message intermediary fee.
- TruckERP only needs a thin API/webhook integration.
- We do not need to recreate chat transport, retry protocols, mobile messaging infrastructure, or another driver messenger.

An intermediary such as Twilio may still be useful later for SMS fallback or if operational simplicity outweighs cost, but it is not required for the primary WhatsApp path.

---

# 3. Channel strategy

Preferred hierarchy:

```text
PRIMARY
    WhatsApp

FALLBACK
    SMS
```

TruckERP should be channel-neutral at the business-event level:

```text
TruckERP event
    ↓
notification / messaging service
    ↓
channel
    ├── WhatsApp
    ├── SMS
    ├── Driver App push
    └── Email
```

Example fallback behavior:

```text
send through WhatsApp
    ↓
if driver has no usable WhatsApp destination
or delivery policy requires fallback
    ↓
send SMS
```

The same trucking rule must not be reimplemented separately for every channel.

---

# 4. Initial TruckERP use cases

WhatsApp can be used for operational driver communication such as:

```text
load assigned
pickup reminder
delivery reminder
pickup / delivery appointment
address / location instructions
load instructions
fuel authorization / fuel-related notice
document request
POD request
settlement ready
maintenance reminder
exception / delay communication
```

Driver responses can include:

```text
ARRIVED
LOADED
DEPARTED
DELIVERED
DELAYED
text reply
photo
PDF / document
current location
voice note (future)
```

---

# 5. Messaging is not business authority

A WhatsApp message must never directly bypass TruckERP rules.

Example:

```text
Driver sends:
ARRIVED

Meta webhook
    ↓
TruckERP identifies sender
    ↓
find active load / trip / expected stop
    ↓
validate ARRIVED is legal for that stop
    ↓
call existing TruckERP domain service
    ↓
update stop/trip state
    ↓
write audit record
```

Possible resulting domain state:

```text
trip_stop.status = ARRIVED
arrived_at = current timestamp
arrived_by = driver
source = WHATSAPP
```

The webhook handler should call existing domain/business services. It should not contain a parallel set of trucking rules and should not perform arbitrary direct database mutations.

---

# 6. Driver commands and safe interpretation

Initial operational commands discussed:

```text
ARRIVED
LOADED
DEPARTED
DELIVERED
DELAYED
```

Preferred safety policy:

```text
exact recognized command
    -> validate context
    -> execute allowed domain action

common misspelling / strong intent
    -> do not blindly change state
    -> confirm when needed

uncertain text
    -> ask driver for confirmation

random conversation
    -> save as message only
```

Examples of possible ARRIVED intent:

```text
arrived
arrive
arive
arived
arrvd
at pickup
at shipper
here
reached
```

These are only intent candidates. TruckERP still validates the active load/trip/stop.

Example confirmation:

```text
Did you mean ARRIVED at ABC Foods for Load 45821?

[ YES ] [ NO ]
```

If TruckERP cannot safely identify the load or stop, **no state change** should occur.

---

# 7. Interactive buttons are preferred over typed commands

Buttons remove spelling ambiguity and reduce driver effort.

Example load message:

```text
Load 45821
Pickup: ABC Foods
Appointment: 2:00 PM

[ ARRIVED ] [ DELAYED ] [ CALL DISPATCH ]
```

Later stages may present:

```text
[ LOADED ]
[ DEPARTED ]
[ DELIVERED ]
[ SEND POD ]
```

Button clicks still go through backend validation before TruckERP changes operational state.

---

# 8. Media, documents and location

WhatsApp should be treated as a useful document/input channel, not only text chat.

Supported future use cases:

```text
POD photo
BOL photo
signed document
seal photo
damage photo
trailer photo
lumper receipt
scale ticket
maintenance photo
PDF document
```

Example:

```text
Driver sends POD photo
    ↓
Meta webhook
    ↓
TruckERP identifies driver + active delivery context
    ↓
store media through TruckERP storage abstraction
    ↓
attach document to correct load/trip
    ↓
show in Dispatch / Load document history
```

## Location

Current/static location sharing is useful for:

- arrival confirmation;
- identifying a pickup/delivery location;
- exception reporting;
- assisting dispatch.

Continuous/live vehicle tracking should remain an ELD / telematics / Driver App responsibility rather than using WhatsApp as a tracking platform.

---

# 9. WhatsApp Flows — later phase

WhatsApp Flows can later provide mini forms inside WhatsApp.

Potential TruckERP flows:

```text
Report Delay
Report Damage
Submit Lumper
Submit Scale Ticket
Trailer Inspection
Load Problem
Detention Check-In
Document Missing
Maintenance Request
```

Example:

```text
Report Delay

Reason
○ Traffic
○ Shipper
○ Receiver
○ Mechanical
○ Weather
○ Other

Estimated delay
[ 30 min ]

Notes
[ ... ]

[ SUBMIT ]
```

Flows are not required for v1. First prove normal outbound messages, inbound webhook handling, buttons, media, and message persistence.

---

# 10. TruckERP message storage

TruckERP should keep its own business/audit record of relevant messages. Do not rely on Meta as TruckERP's permanent system of record.

Suggested message data:

```text
id
tenant_id
channel = WHATSAPP
direction = OUTBOUND | INBOUND
driver_id
phone_number / WhatsApp destination id
message_text
provider_message_id
template_name nullable
message_type
related_load_id nullable
related_trip_id nullable
related_stop_id nullable
sent_at
delivered_at
read_at
failed_at
status
error_code nullable
reply_to_message_id nullable
attachment references nullable
provider metadata / raw event reference where useful
created_at
```

Exact schema is not locked yet. Reuse existing TruckERP notification/audit/storage patterns where possible before creating new tables.

Important requirements:

- tenant-safe mapping;
- driver identity mapping;
- message idempotency;
- load/trip context;
- delivery/read/failure status;
- audit source;
- no duplicated business logic.

---

# 11. Webhook behavior

Inbound flow:

```text
Meta webhook
    ↓
verify webhook/authenticity
    ↓
deduplicate provider message/event id
    ↓
resolve tenant + WhatsApp number + driver
    ↓
save inbound message/event
    ↓
identify command/button/media/location intent
    ↓
validate business context
    ↓
call existing domain service if action is authorized
    ↓
write resulting audit trail
```

Webhook retries must be idempotent. The same Meta message/event must not cause duplicate ARRIVED, DELIVERED, document, or other operational actions.

---

# 12. Outbound template strategy

Because TruckERP will use the direct Cloud API, TruckERP creates and submits its own templates to Meta for review.

Templates may be created through:

```text
Meta API / message_templates endpoint
or
WhatsApp Manager manually
```

Preferred template category for normal TruckERP operational notifications:

```text
UTILITY
```

Wording should remain transactional/operational rather than promotional.

Good style:

```text
Load 45821 has been assigned to you.
Pickup: ABC Foods.
Appointment: 2:00 PM.
```

Avoid marketing-style wording such as:

```text
Great loads available today!
Reply now to make more money!
```

Meta may reclassify a template if the content is promotional.

Template names should use lowercase letters/numbers/underscores, for example:

```text
load_assignment_v1
pickup_reminder_v1
document_request_v1
settlement_ready_v1
```

Dynamic values use numbered variables such as:

```text
{{1}}
{{2}}
{{3}}
```

Provide valid sample/example values when submitting templates for approval.

---

# 13. Initial template set

Keep v1 small.

## load_assignment_v1

```text
Load {{1}} has been assigned to you.
Pickup: {{2}}
Appointment: {{3}}
Delivery: {{4}}
```

## pickup_reminder_v1

```text
Reminder for Load {{1}}.
Pickup appointment: {{2}}
Location: {{3}}
```

## document_request_v1

```text
Please send the {{1}} for Load {{2}}.
```

## settlement_ready_v1

```text
Your settlement for period {{1}} is ready.
```

Templates should contain only the information necessary for the driver action. Sensitive business or personal information should not be placed into messages unnecessarily.

---

# 14. Pricing direction discussed

The design discussion concluded that WhatsApp appears attractive compared with Canadian SMS for routine driver communication, particularly because SMS can be billed per segment while WhatsApp messages do not have the same 160-character segmentation model.

Working pricing assumption discussed for **direct Meta Cloud API** around the October 2026 pricing change:

```text
North America utility/service message estimate: about USD $0.0034 per delivered message
incoming driver messages: no message charge
first 1,000 service messages per business phone number/month: discussed as free allowance
```

Example discussed:

```text
100 utility template messages
4,900 service replies
5,000 outbound total

100 × $0.0034 = $0.34
first 1,000 service messages = $0.00 under discussed allowance
3,900 × $0.0034 = $13.26
approximate total = $13.60 USD/month
```

Canadian SMS was discussed as materially higher per outbound segment, making WhatsApp a good primary candidate and SMS a fallback.

**IMPORTANT PRICING LOCK:** These numbers are a planning snapshot from the September 2026 discussion, **not permanent implementation constants**. Before production launch, verify current pricing, category definitions, service-window rules, free allowances, template rules, and country rates against Meta's official WhatsApp Business pricing/policy documentation. Do not hardcode pricing assumptions into TruckERP business logic.

---

# 15. 24-hour service conversation behavior

The discussion recognized two separate concepts that must not be confused:

1. whether TruckERP is allowed to send free-form/service messages after the driver has messaged the business;
2. whether those outbound messages are free or billable under the pricing schedule in effect at the time.

TruckERP must follow the current Meta service-window/template rules at implementation time.

Do not assume that "inside 24 hours" automatically means "free" without checking the current pricing policy.

---

# 16. Security and identity requirements

Before any operational command can affect TruckERP:

```text
verify Meta webhook authenticity
resolve WhatsApp destination to exactly one tenant context
resolve sender to exactly one driver/person relationship
verify driver is authorized for the load/trip/stop
validate action is legal for current state
ensure provider message/event id is not already processed
write audit trail
```

Never trust a phone number alone as sufficient authority for a money-sensitive or status-sensitive action.

Driver opt-in / consent requirements and current Meta messaging policies must be handled during onboarding/configuration.

---

# 17. Recommended v1 implementation scope

Implement only the useful minimum:

```text
1. Direct Meta Cloud API connection
2. Business phone / WABA configuration
3. Approved utility templates
4. Send template message from backend
5. Receive inbound webhook
6. Save inbound/outbound business message history
7. Map WhatsApp sender to driver
8. Associate message with load/trip when determinable
9. Quick-reply buttons
10. ARRIVED / DELAYED first operational actions
11. Context validation before state changes
12. Delivery/read/failure status handling
13. Photo/document intake
14. Current/static location intake
15. SMS fallback later or when required
```

Do not begin by building a large messaging platform.

---

# 18. Things TruckERP explicitly does NOT need to build

```text
custom chat transport protocol
custom phone messaging network
custom delivery infrastructure
custom read-receipt transport
custom driver messenger app just for chat
continuous WhatsApp GPS tracking
separate trucking rules inside webhook handlers
AI authority to change load/trip state without validation
```

Meta handles the messaging transport. TruckERP handles trucking context and business actions.

---

# 19. Implementation principle

The locked conceptual boundary is:

```text
                    TruckERP Backend
                    /      |       \
                   /       |        \
            Web Admin   Driver App   WhatsApp
```

All interfaces call the same backend/domain rules.

For example, ARRIVED from:

```text
Driver App button
WhatsApp button
Dispatch admin action
```

should ultimately use the same TruckERP arrival/status service and the same validation rules, with only the action source differing.

---

# 20. Future implementation checklist

Before writing production code, verify these items:

```text
[ ] current Meta Cloud API version
[ ] current WhatsApp Business pricing
[ ] current template-category rules
[ ] current service-window rules
[ ] WABA / business account setup
[ ] production WhatsApp phone number
[ ] webhook verification/signing requirements
[ ] driver opt-in capture
[ ] tenant/driver phone mapping
[ ] existing TruckERP notification/message models that can be reused
[ ] existing TruckERP load/trip/stop domain services for ARRIVED etc.
[ ] attachment storage path
[ ] idempotency model for provider message/event ids
[ ] delivery/read/failure status persistence
[ ] SMS fallback provider and trigger rules
```

---

# 21. Final design summary

```text
Use WhatsApp as the primary driver messaging channel.
Use direct Meta Cloud API.
Do not build our own messaging transport.
Use SMS as fallback.
Create a small set of operational UTILITY templates.
Use buttons whenever possible.
Use webhooks for replies/status/media/location.
Store relevant message history in TruckERP.
Map every action back to driver + tenant + load/trip context.
Backend remains authoritative.
Fuzzy text never bypasses validation.
Reuse the same TruckERP domain services used by Driver App/Admin UI.
Verify Meta pricing/policy again immediately before production implementation.
```
