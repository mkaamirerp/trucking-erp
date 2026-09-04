"""Approved static semantic field_rules for Load / Rate Confirmation OpenAI handoff.

Designed intelligence only — response schema compatibility does NOT dictate this set.
Do not add rule groups without explicit approval.
Do not hardcode broker or tenant identities.
"""

from __future__ import annotations

from typing import Any

# Approved static instruction set (Option 1). Keys must match exactly.
LOAD_RATE_CON_FIELD_RULES: dict[str, Any] = {
    "profile": "rate_confirmation",
    "version": "load_rate_con_field_rules_v1",
    "rules": {
        "broker_load_reference": {
            "product_fields": ["broker_load_reference"],
            "meaning": "The broker/customer's principal identifier for this shipment/load.",
            "possible_labels_examples": [
                "Load #",
                "Load Number",
                "Load ID",
                "Order #",
                "Order Number",
                "PO #",
                "PO Number",
                "Confirmation #",
                "Confirmation Number",
                "Freight Bill #",
                "Shipment #",
                "Reference #",
            ],
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Choose the principal shipment/load identifier by business meaning, "
                "prominence, and document context. Do not use a rigid static label-priority list."
            ),
            "rules": [
                "A primary broker load reference is not simply the first reference-like value found.",
                "Preserve other meaningful identifiers separately in references[].",
                "Stop-level references, audit identifiers, signature/audit IDs, and secondary shipment "
                "references should not replace the principal load identifier unless the document "
                "clearly establishes them as primary.",
                "Return only the identifier value in broker_load_reference.",
                "Labels such as Load #, Load Number, Order #, Confirmation #, and PO # are discovery "
                "labels only; do not include the label or prefix text in the value.",
                "If the principal identifier is genuinely ambiguous, return null rather than inventing a choice.",
            ],
        },
        "broker_company": {
            "product_fields": ["broker_name_snapshot"],
            "meaning": (
                "The freight broker/company that tendered, arranged, or issued this load to our carrier."
            ),
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Determine the freight broker semantically from the document and transaction context."
            ),
            "rules": [
                "Never return a party matching tenant_identity_exclusion as the broker.",
                "Broker company is a company/entity, not the individual agent handling the load.",
                "Do not confuse the freight broker with the shipper, receiver, consignee, factoring "
                "company, payment/QuickPay provider, insurer, customs broker, carrier, tenant, or a "
                "stop-level business.",
                "A document may contain the word broker in another context, such as customs broker; "
                "use transaction context rather than keyword matching.",
                "If the freight broker is unsupported or ambiguous, return null rather than selecting "
                "an unrelated company.",
            ],
        },
        "broker_authority": {
            "product_fields": [
                "broker_mc_number_snapshot",
                "broker_dot_number_snapshot",
            ],
            "meaning": (
                "The MC/USDOT authority numbers belonging to the freight broker/company that "
                "tendered, arranged, or issued this load to our carrier."
            ),
            "possible_labels_examples": [
                "MC",
                "MC Number",
                "MC #",
                "Motor Carrier",
                "USDOT",
                "US DOT",
                "DOT",
                "DOT Number",
                "DOT #",
            ],
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Associate each authority number with the company/entity it actually belongs to. "
                "Prefer authority shown in the broker's company or corporate-information block, "
                "or otherwise clearly tied to the selected broker company. Do not assign ownership "
                "from proximity to a person or contact heading."
            ),
            "rules": [
                "Authority numbers must belong to the selected broker company, not merely be nearby numbers.",
                "Never return MC/DOT values belonging to tenant_identity_exclusion.",
                "Never return the carrier/tenant's MC/DOT as broker authority.",
                "If broker and carrier authorities both appear, associate each authority with its "
                "actual company/entity.",
                "Prefer authority shown in the broker's company/corporate-information block or "
                "otherwise clearly tied to the broker company.",
                "Do not transfer an MC/DOT to the broker merely because it appears near a broker "
                "contact/person.",
                "A load-information/contact section may contain carrier/tenant authority nearby; "
                "proximity alone does not establish ownership.",
                "Normalize supported MC/USDOT values to identifying digits.",
                "If broker MC is supported but broker USDOT is absent, return MC and leave DOT null.",
                "If authority ownership is ambiguous, return null rather than selecting another "
                "party's number.",
            ],
        },
        "broker_contact": {
            "product_fields": [
                "broker_contact_name_snapshot",
                "broker_contact_phone_snapshot",
                "broker_contact_email_snapshot",
            ],
            "meaning": "The individual broker/agent/representative handling this specific load.",
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Prefer a named person-specific broker contact when the document supports one. "
                "Phone and email should belong to that person when supported."
            ),
            "rules": [
                "Do not return tenant/carrier contacts as broker contacts.",
                "Do not return driver contacts as broker contacts.",
                "Do not substitute shipper or receiver contacts.",
                "Do not substitute after-hours numbers, general corporate numbers, tracking contacts, "
                "claims contacts, accounts payable contacts, QuickPay contacts, payment contacts, or "
                "generic carrier-relations contacts when a person-specific broker contact exists.",
                "Exact tenant emails and company-owned tenant email domains in tenant_identity_exclusion "
                "must not be returned as broker contact information.",
                "Public mailbox domains by themselves do not establish company ownership.",
                "Strong broker-contact evidence includes headings and phrases such as "
                "'FOR LOAD INFORMATION', 'Agent Name', 'Please Sign and Email to <person>', and "
                "'For specific information about this load, contact <person>'.",
                "A person-specific email on the broker company's domain is strong contact evidence.",
                "Repeated name/email/phone evidence tied to the same load strengthens the same "
                "person-specific broker contact.",
                "A broker contact may appear next to carrier/tenant MC/DOT information.",
                "Contact identity and authority ownership must be evaluated separately.",
                "Do not reject a valid broker contact merely because carrier authority numbers "
                "are nearby.",
                "Still never return tenant/carrier people as broker contacts.",
                "If no supported person-specific broker contact exists, return null rather than "
                "assigning an unrelated general contact.",
                "When a named broker contact/person is selected, broker_contact_phone_snapshot "
                "must be that person's direct phone.",
                "Do not populate broker_contact_phone_snapshot with the broker company's main phone, "
                "corporate phone, general office number, carrier-relations line, after-hours line, "
                "tracking line, or claims/AP/payment line.",
                "If only a company or corporate number is supported, return null for "
                "broker_contact_phone_snapshot.",
                "When a named person is selected, broker_contact_email_snapshot must belong to that person.",
                "Generic company mailboxes such as carriers@, dispatch@, info@, operations@, billing@, "
                "accounting@, and support@ must not populate a named person's email merely because they "
                "use the broker's domain.",
                "A matching broker-company email domain proves company association, not person association.",
                "If only a generic or company mailbox is supported, return null for "
                "broker_contact_email_snapshot.",
            ],
        },
        "rate_broker_pay": {
            "product_fields": ["rate"],
            "meaning": (
                "The total compensation the broker agreed to pay our carrier for performing this "
                "specific load."
            ),
            "possible_labels_examples": [
                "Total Carrier Pay",
                "Carrier Pay",
                "Agreed Rate",
                "Total",
                "Total USD",
                "Rate",
                "Line Haul",
                "Linehaul",
                "Charge",
                "Freight Pay",
            ],
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Use business meaning and document context to identify the total broker-to-carrier "
                "compensation for this load."
            ),
            "rules": [
                "Prefer an explicit total carrier compensation amount.",
                "If an authorized pay breakdown contains multiple components and a stated total "
                "carrier pay is shown, use the stated total.",
                "Do not choose an amount merely because it is the largest dollar amount in the document.",
                "Do not treat detention as the load rate.",
                "Do not treat layover as the load rate.",
                "Do not treat TONU as the load rate.",
                "Do not treat late fees, fines, penalties, or claims amounts as the load rate.",
                "Do not treat QuickPay fees or percentages as the load rate.",
                "Do not treat EFS fees as the load rate.",
                "Do not treat advances as the load rate.",
                "Do not treat conditional reimbursements or policy limits as the load rate.",
                "Do not treat rate reductions as the original agreed load rate.",
                "Do not treat informational per-mile values as the total load rate.",
                "If total broker-to-carrier compensation is unsupported, return null.",
            ],
        },
        "customer_rate_guardrail": {
            "product_fields": ["customer_rate"],
            "meaning": (
                "A separate charge to the broker's customer, if the document explicitly provides one."
            ),
            "examples_not_exhaustive": True,
            "rules": [
                "Do not automatically copy rate into customer_rate.",
                "A carrier rate confirmation usually shows broker-to-carrier compensation, not the "
                "broker's customer charge.",
                "Leave customer_rate null unless a separate customer charge is explicitly and "
                "unambiguously supported by the document.",
            ],
        },
        "stops": {
            "product_fields": ["stops"],
            "meaning": (
                "A stop is a distinct physical route location the truck must visit to perform this "
                "shipment."
            ),
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Build the route from physical shipment visits in order. Do not infer stops from "
                "keyword counts or from the presence of addresses alone."
            ),
            "rules": [
                "Create one stop per distinct physical visit.",
                "Preserve actual route order.",
                "Multiple pickups and multiple deliveries are valid.",
                "Do not assume exactly one pickup and one delivery.",
                "Do not create duplicate stops from repeated mentions of the same location.",
                "Do not count broker offices as route stops.",
                "Do not count tenant/carrier addresses as route stops.",
                "Do not count factoring, billing, payment, corporate, legal, audit, invoice-mailing, "
                "or general customs-broker addresses as route stops unless the truck must physically "
                "visit that location for the shipment.",
                "Do not create stops from references, instructions, signatures, audit trails, payment "
                "sections, or legal terms.",
                "Stop count is the length of the normalized physical route stop list.",
            ],
        },
        "pickup_semantics": {
            "product_fields": ["stops[].stop_type"],
            "meaning": "A pickup is a physical route stop where freight is loaded or collected.",
            "possible_labels_examples": [
                "Pickup",
                "Pick-up",
                "PU",
                "Shipper",
                "Origin",
                "Pickup Location",
                "Shipper Pickup",
                "Load At",
            ],
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Use the role of the stop in the shipment route, not rigid keyword mapping."
            ),
            "rules": [
                "Normalize a pickup-side route stop to stop_type='pickup'.",
                "A company called shipper/origin may indicate pickup-side meaning, but context controls.",
                "Do not classify a non-route address as pickup merely because a pickup-related word "
                "appears nearby.",
            ],
        },
        "delivery_semantics": {
            "product_fields": ["stops[].stop_type"],
            "meaning": (
                "A delivery is a physical route stop where freight is delivered, dropped, or received."
            ),
            "possible_labels_examples": [
                "Delivery",
                "Drop",
                "Dropoff",
                "DEL",
                "Receiver",
                "Consignee",
                "Destination",
                "Delivery Location",
                "Consignee Delivery",
                "SO",
                "Stop Off",
            ],
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Use route context to determine delivery-side meaning. Terms such as SO/Stop Off "
                "are context-dependent."
            ),
            "rules": [
                "Normalize a delivery-side route stop to stop_type='delivery'.",
                "Receiver and consignee strongly indicate delivery-side meaning but must still be "
                "interpreted in context.",
                "SO/Stop Off may represent an intermediate delivery or stop-off depending on the route.",
                "Do not create delivery stops from unrelated company/address mentions.",
            ],
        },
        "appointment_date_time": {
            "product_fields": [
                "stops[].appointment_date",
                "stops[].appointment_time_text",
            ],
            "meaning": (
                "Appointment date/time information belongs to its corresponding physical route stop."
            ),
            "possible_labels_examples": [
                "Pickup",
                "Delivery",
                "Date",
                "Expected Date",
                "Appointment",
                "Appt",
                "Date/Time",
                "Target Window",
                "Pickup Date",
                "Delivery Date",
                "Appointment Time",
                "Shipping Hours",
                "Receiving Hours",
            ],
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Attach date/time evidence to the correct physical route stop. Preserve the "
                "document's actual appointment semantics."
            ),
            "rules": [
                "Normalize an unambiguous supported date to YYYY-MM-DD.",
                "Preserve appointment windows rather than truncating them to the first time.",
                "Preserve the source time/range in appointment_time_text.",
                "If a stop date is supported but no time is provided, keep the date and leave time null.",
                "If the stop is FCFS, open-window, or similar, preserve that semantic wording where "
                "the response schema allows rather than inventing an exact time.",
                "Do not confuse document creation dates with stop appointments.",
                "Do not confuse confirmation dates, signature dates, audit dates, digital acceptance "
                "timestamps, invoice/payment deadlines, detention timing, policy dates, or unrelated "
                "timestamps with stop appointments.",
            ],
        },
        "references": {
            "product_fields": ["references"],
            "meaning": (
                "Meaningful shipment-related identifiers other than the principal broker load reference."
            ),
            "possible_labels_examples": [
                "PO",
                "PO Number",
                "BOL",
                "Bill of Lading",
                "PRO",
                "EL",
                "Shipment",
                "Reference",
                "Confirmation",
                "Order",
            ],
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Preserve meaningful secondary shipment identifiers when supported, without elevating "
                "them automatically to the primary broker_load_reference."
            ),
            "rules": [
                "Do not treat every number in the document as a reference.",
                "Exclude phone numbers, dollar amounts, weights, dates, timestamps, addresses, audit "
                "IDs, IP addresses, page numbers, and random numeric tokens unless the document clearly "
                "identifies them as shipment references.",
                "Stop-specific references should remain associated with the stop when the schema "
                "supports that relationship.",
                "A secondary valid reference should not replace the principal load reference solely "
                "because it appears later, is longer, or looks more numeric.",
                "Do not invent reference values.",
            ],
        },
        "freight_mode": {
            "product_fields": ["mode"],
            "meaning": (
                "The transportation mode for this load, taken from explicit load-level mode evidence."
            ),
            "possible_labels_examples": [
                "Mode",
                "Freight Mode",
                "Service Type",
                "Shipment Type",
            ],
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Use an explicit load-level Mode, Freight Mode, Service Type, Shipment Type, or "
                "equivalent field. Do not infer mode from equipment or stop behavior."
            ),
            "normalization": {
                "Full TruckLoad": "FTL",
                "Full Truckload": "FTL",
                "Truckload": "FTL",
                "FTL": "FTL",
                "Less Than Truckload": "LTL",
                "Less-than-Truckload": "LTL",
                "LTL": "LTL",
                "Partial": "PARTIAL",
                "Partial Truckload": "PARTIAL",
                "Power Only": "POWER_ONLY",
                "Power-Only": "POWER_ONLY",
            },
            "rules": [
                "Populate mode only from explicit load-level mode evidence.",
                "Normalize Full TruckLoad, Full Truckload, Truckload, and FTL to FTL.",
                "Normalize Less Than Truckload, Less-than-Truckload, and LTL to LTL.",
                "Normalize Partial and Partial Truckload to PARTIAL.",
                "Normalize Power Only and Power-Only to POWER_ONLY when that mode is explicitly supported.",
                "Do not infer mode from equipment, trailer type, trailer size, weight, number of stops, "
                "live/live wording, or rate.",
                "If mode is unsupported or ambiguous, return null.",
            ],
        },
        "trailer_type": {
            "product_fields": ["trailer_type"],
            "meaning": (
                "The trailer body/type required for this load, separate from trailer size, equipment "
                "asset identity, freight mode, and temperature requirement."
            ),
            "possible_labels_examples": [
                "Trailer Type",
                "Equipment Type",
                "Equipment",
                "Trailer",
                "Equipment Required",
            ],
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Extract the trailer body/type. When type and size appear together in a broader "
                "equipment description, put only the body/type in trailer_type."
            ),
            "normalization": {
                "Van": "Van",
                "Dry Van": "Dry Van",
                "Reefer": "Reefer",
                "Refrigerated": "Reefer",
            },
            "rules": [
                "Extract trailer body/type separately from trailer size.",
                "A broader equipment_type value may remain source-faithful when a combined equipment "
                "description is present; trailer_type must contain only the supported body/type.",
                "When type and size appear together, do not put length or size into trailer_type.",
                "Normalize only clear synonyms such as Van, Dry Van, and Reefer.",
                "If the broker explicitly permits more than one trailer type, preserve the alternatives "
                "rather than arbitrarily selecting one.",
                "Do not infer trailer type from commodity, temperature, mode, weight, or equipment "
                "asset IDs.",
                "If trailer type is unsupported, return null.",
            ],
        },
        "trailer_size": {
            "product_fields": ["trailer_size"],
            "meaning": (
                "The explicit trailer length or size required for this load, separate from trailer "
                "body/type and from the full equipment description."
            ),
            "possible_labels_examples": [
                "Trailer Size",
                "Trailer Length",
                "Equipment Size",
                "Length",
            ],
            "examples_not_exhaustive": True,
            "how_to_choose": (
                "Extract explicit trailer length/size only. Do not copy the full equipment description "
                "into trailer_size."
            ),
            "normalization": {
                "53'": "53 ft",
                "53 feet": "53 ft",
            },
            "rules": [
                "Extract explicit trailer length/size separately from trailer type.",
                "A combined equipment description may supply both type and size; trailer_size contains "
                "the length/size only.",
                "Do not copy the full equipment description into trailer_size.",
                "Normalize clear length evidence to a consistent form such as 53' to 53 ft and "
                "53 feet to 53 ft. Apply the same pattern to other explicit lengths.",
                "Do not infer a size from a cryptic equipment code unless the source explicitly "
                "establishes the mapping.",
                "If no explicit supported size is present, return null.",
            ],
        },
    },
}

APPROVED_FIELD_RULE_KEYS: tuple[str, ...] = (
    "broker_load_reference",
    "broker_company",
    "broker_authority",
    "broker_contact",
    "rate_broker_pay",
    "customer_rate_guardrail",
    "stops",
    "pickup_semantics",
    "delivery_semantics",
    "appointment_date_time",
    "references",
    "freight_mode",
    "trailer_type",
    "trailer_size",
)


def get_load_rate_con_field_rules() -> dict[str, Any]:
    """Return a deep-copy-safe static field_rules object (caller may mutate the copy)."""
    import copy

    return copy.deepcopy(LOAD_RATE_CON_FIELD_RULES)
