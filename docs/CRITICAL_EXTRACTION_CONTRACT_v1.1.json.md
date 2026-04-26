{
  "critical_extraction_contract_version": "1.1",
  "purpose": "Extract only dispatch-critical fields from broker rate confirmations/load tenders. Wrong blank is safer than wrong filled.",
  "global_rules": [
    "Return null when uncertain.",
    "Every extracted critical field must include confidence and source evidence.",
    "Do not invent missing values.",
    "Do not use broker office, carrier address, bill-to address, invoice address, remittance address, payment address, mailing address, or corporate address as physical pickup/delivery stops.",
    "Preserve stop order as shown in the PDF.",
    "If multiple pickups or deliveries exist, return all of them in stops[].",
    "If stop type is unclear, use stop_type='unknown' and needs_review=true.",
    "If only city/state is present, fill city/state and mark address_quality='partial'.",
    "Do not promote weak references to broker_load_reference. If uncertain, leave broker_load_reference.value null and preserve candidates separately.",
    "For broker_load_reference, never use ordinary English words or instruction words as values."
  ],
  "field_instructions": {
    "broker_name": {
      "meaning": "The broker/logistics company issuing the rate confirmation/load tender.",
      "look_for_sections": [
        "header",
        "broker",
        "load confirmation",
        "rate confirmation",
        "carrier tender",
        "corporate information",
        "bill to"
      ],
      "avoid": [
        "carrier name",
        "factoring company",
        "driver name",
        "shipper name",
        "receiver name",
        "customs broker unless explicitly the booking broker"
      ],
      "output": {
        "value": null,
        "confidence": null,
        "source_text": null,
        "page_number": null,
        "needs_review": true,
        "reason": null
      }
    },
    "broker_load_reference": {
      "meaning": "The main broker/order/load/tender reference used by dispatch to identify this load with the broker.",
      "look_for_labels": [
        "Load #",
        "Load Number",
        "Load ID",
        "Order #",
        "Order Number",
        "PO#",
        "PO #",
        "PO Number",
        "Rate Confirmation #",
        "Confirmation #",
        "Dispatch #",
        "Shipment ID",
        "Load Confirmation",
        "Freight Bill #",
        "EL #",
        "Reference #"
      ],
      "broker_specific_hints": {
        "TQL": ["PO#"],
        "J.B. Hunt": ["Load Number"],
        "Armstrong": ["Load #", "Armstrong load number"],
        "DeGroot Logistics": ["Load Number"],
        "BM2 Freight": ["Load Number"],
        "Hub Group": ["Load #"],
        "RXO": ["Order #", "Load Confirmation", "LZ reference"],
        "Landstar": ["Freight Bill #", "EL #"],
        "Circle Logistics": ["Load #", "Load Number"]
      },
      "do_not_use_labels": [
        "MC #",
        "DOT #",
        "Phone",
        "Fax",
        "Weight",
        "Miles",
        "Rate",
        "Total",
        "Estimated Weight",
        "Carrier Number",
        "Carrier Invoice #",
        "late fee",
        "detention",
        "quick pay"
      ],
      "hard_value_rules": [
        "Value must contain at least one digit unless a broker-specific active mapping explicitly allows otherwise.",
        "Reject values that are only common words or instruction words.",
        "Reject boolean/instruction values such as Yes, No, True, False, RELATES, will, must, shall, required, Information.",
        "Reject values that are phone numbers, fax numbers, MC/DOT numbers, weights, miles, money amounts, dates, or times.",
        "If the best candidate is low confidence, leave value null."
      ],
      "if_uncertain": "Leave value null and explain why in reason.",
      "output": {
        "value": null,
        "label": null,
        "confidence": null,
        "source_text": null,
        "page_number": null,
        "needs_review": true,
        "reason": null
      }
    },
    "carrier_rate_total": {
      "meaning": "Total amount payable to the carrier for hauling this load.",
      "look_for_labels": [
        "Total",
        "Total Carrier Pay",
        "Carrier Freight Pay",
        "Agreed Rate",
        "Net Freight Charges",
        "Total Cost",
        "Line Haul",
        "Rate"
      ],
      "do_not_use_labels": [
        "late fee",
        "detention rate",
        "quick pay fee",
        "advance fee",
        "lumper receipt",
        "fuel advance",
        "claim",
        "fine"
      ],
      "output": {
        "amount": null,
        "currency": null,
        "confidence": null,
        "source_text": null,
        "page_number": null,
        "needs_review": true,
        "reason": null
      }
    },
    "stops": {
      "meaning": "Ordered list of physical pickup and delivery locations where the driver must go.",
      "stop_detection_rules": [
        "Create one stop for each physical pickup/shipper/origin.",
        "Create one stop for each physical delivery/receiver/consignee/destination/drop.",
        "Keep the sequence shown in the PDF.",
        "Do not collapse multiple pickups into one stop.",
        "Do not collapse multiple deliveries into one stop.",
        "Never use broker office, carrier, remittance, payment, bill-to, invoice, mailing, or corporate addresses as stops.",
        "If address is incomplete, fill known parts and mark address_quality='partial'.",
        "If a stop appears to be pickup but is not certain, use stop_type='unknown' and needs_review=true."
      ],
      "pickup_indicators": [
        "Pickup",
        "Pick-up Location",
        "PU",
        "Shipper",
        "Origin",
        "Stop #1 pickup",
        "Shipper Pickup",
        "Pickup Location",
        "Pickup Date",
        "Pickup #"
      ],
      "delivery_indicators": [
        "Delivery",
        "Consignee",
        "Receiver",
        "Destination",
        "Drop",
        "Dropoff",
        "DEL",
        "SO",
        "Stop #2 drop",
        "Receiver or Delivery Location",
        "Delivery Date",
        "Delivery #"
      ],
      "address_labels": [
        "Name",
        "Location",
        "Name and Address",
        "Address",
        "City/St/Zip",
        "City/State/Zip",
        "Date",
        "Time",
        "Appointment",
        "Target Window",
        "Reference number"
      ],
      "output_array_item": {
        "stop_sequence": null,
        "stop_type": null,
        "facility_name": null,
        "street": null,
        "city": null,
        "state_province": null,
        "postal_zip": null,
        "country": null,
        "date": null,
        "time_window": null,
        "reference_numbers": [],
        "address_quality": null,
        "confidence": null,
        "source_section": null,
        "source_text": null,
        "page_number": null,
        "needs_review": true,
        "reason": null
      }
    },
    "equipment": {
      "meaning": "Truck/trailer/equipment required for this load.",
      "look_for_labels": [
        "Equipment",
        "Equipment Type",
        "Trailer Type",
        "Trailer Size",
        "Mode",
        "Van",
        "Reefer",
        "Dry Van",
        "Flatbed",
        "53'",
        "48'"
      ],
      "output": {
        "equipment_type": null,
        "trailer_size": null,
        "confidence": null,
        "source_text": null,
        "page_number": null,
        "needs_review": true,
        "reason": null
      }
    },
    "temperature_requirement": {
      "meaning": "Temperature requirement for reefer or temperature-controlled loads.",
      "look_for_labels": [
        "Temperature",
        "Temp",
        "Temperature Setting",
        "Temperature Minimum",
        "Temperature Maximum",
        "Continuous",
        "Run Type",
        "Reefer"
      ],
      "output": {
        "temperature_required": null,
        "temperature_min": null,
        "temperature_max": null,
        "temperature_unit": null,
        "run_type": null,
        "confidence": null,
        "source_text": null,
        "page_number": null,
        "needs_review": true,
        "reason": null
      }
    },
    "commodity": {
      "meaning": "Freight/product being hauled.",
      "look_for_labels": [
        "Commodity",
        "Product",
        "Description",
        "Freight Description",
        "Item",
        "Commodity Description"
      ],
      "output": {
        "value": null,
        "confidence": null,
        "source_text": null,
        "page_number": null,
        "needs_review": true,
        "reason": null
      }
    },
    "weight": {
      "meaning": "Total shipment weight.",
      "look_for_labels": [
        "Weight",
        "Estimated Weight",
        "Total Weight",
        "Wgt",
        "lbs",
        "pounds"
      ],
      "do_not_use_labels": [
        "rate",
        "miles",
        "phone",
        "MC",
        "DOT",
        "load number"
      ],
      "output": {
        "weight_lbs": null,
        "confidence": null,
        "source_text": null,
        "page_number": null,
        "needs_review": true,
        "reason": null
      }
    }
  },
  "required_response_shape": {
    "critical_extraction_contract_version": "1.1",
    "broker_name": {
      "value": null,
      "confidence": null,
      "source_text": null,
      "page_number": null,
      "needs_review": true,
      "reason": null
    },
    "broker_load_reference": {
      "value": null,
      "label": null,
      "confidence": null,
      "source_text": null,
      "page_number": null,
      "needs_review": true,
      "reason": null
    },
    "carrier_rate_total": {
      "amount": null,
      "currency": null,
      "confidence": null,
      "source_text": null,
      "page_number": null,
      "needs_review": true,
      "reason": null
    },
    "stops": [
      {
        "stop_sequence": null,
        "stop_type": null,
        "facility_name": null,
        "street": null,
        "city": null,
        "state_province": null,
        "postal_zip": null,
        "country": null,
        "date": null,
        "time_window": null,
        "reference_numbers": [],
        "address_quality": null,
        "confidence": null,
        "source_section": null,
        "source_text": null,
        "page_number": null,
        "needs_review": true,
        "reason": null
      }
    ],
    "equipment": {
      "equipment_type": null,
      "trailer_size": null,
      "confidence": null,
      "source_text": null,
      "page_number": null,
      "needs_review": true,
      "reason": null
    },
    "temperature_requirement": {
      "temperature_required": null,
      "temperature_min": null,
      "temperature_max": null,
      "temperature_unit": null,
      "run_type": null,
      "confidence": null,
      "source_text": null,
      "page_number": null,
      "needs_review": true,
      "reason": null
    },
    "commodity": {
      "value": null,
      "confidence": null,
      "source_text": null,
      "page_number": null,
      "needs_review": true,
      "reason": null
    },
    "weight": {
      "weight_lbs": null,
      "confidence": null,
      "source_text": null,
      "page_number": null,
      "needs_review": true,
      "reason": null
    }
  }
}
