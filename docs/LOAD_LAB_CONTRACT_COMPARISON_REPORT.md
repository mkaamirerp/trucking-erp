# Load Lab — truckerjson vs critical_v1_1 (real run comparison)

Generated on host API; tenant `demo` (`tenant_id=53`). Each run: **POST** `truckerjson` first (capture), then `critical_v1_1` (capture). Default in code remains **truckerjson**; this is evidence only.

**Tool:** `tools/run_load_lab_contract_pair_eval.py` (see script docstring). Per-contract `parse_response` snapshots: `/tmp/contract_pair_{run_id}_truck.json` and `..._crit.json` in the API container (not committed).

## Executive summary (2026-04-26)

All **12** sematic requests returned **HTTP 200** and **`semantic_extract_status: success`**.

- **Stops / geography:** `stop_type`, city, state, most streets/postals **match** between contracts on this set; `stops[]` count matches (2 each). **Stop `sequence` differs by convention (0,1 vs 1,2)** — treat as **format**, not re-order; both passes preserve pickup→delivery order.
- **Appointments:** `appointment_date` often differs by **string format** (ISO `YYYY-MM-DD` vs `MM/DD/YYYY`); mark **needs_review** for the same calendar day.
- **Rate / currency:** `extracted.rate` matches where compared; `critical` adds structured **`carrier_rate_total` with `currency: USD`** in `context.critical_extraction_v1_1` (not duplicated in the row-level table for every line).
- **Broker load ref — regression risk (critical):** for **39**, **42**, **43**, **`broker_load_reference` is null in `critical` where `truckerjson` had a non-nonsense string** (Armstrong: `3872125-1`, Hub: long digit string, TQL: `34307972`). **Guardrails ran** (`Y` on those rows) but **dropping a plausible ref** is not automatically “safer” than `truckerjson` on this evidence — **needs product review and mapping fixes** before any default switch.
- **Run 40 commodity:** `truckerjson` has `Item`; `critical` **∅** — review.
- **Reefer 41 — temperature:** Free-text `Continuous` (T) vs band `-10.0--10.0 F` (C) — **needs_review** (different encodings; not a simple equal compare).
- **TQL 43 — equipment / trailer fields:** more splitting in `truckerjson` (`trailer_type` / `trailer_size`); `critical` coalesces — **needs_review** for default decision.

**Verdict on default switch:** **Do not** make `critical_v1_1` the Load Lab default yet. Evidence shows **wins on currency + structured rate**, but **unacceptable or unexplained `broker_load_reference` nulls** on multiple PDFs where legacy had a readable ref. Harden `critical` mapping / guardrails for `broker_load_reference` (and confirm Hub/TQL/Armstrong with PDF ground truth) first.

**Field instructions / guardrails to fix (priority):**

1. **`broker_load_reference`:** stop clearing valid order/load IDs when the legacy field was non-nonsense; prefer **needs_review** or structured uncertainty over **null** unless the contract explicitly cannot support the ID.
2. **Primary reference + diagnostics** (existing issue): still align with `load_lab` reference heuristics so nonsense tokens are not “accepted” in other layers (see `LOAD_LAB_REAL_PDF_EVALUATION.md`).
3. **Sequence display:** either normalize to 0-based in both or document 1-based in `critical` output for UI.
4. **Date normalization:** one canonical `appointment_date` format after extraction, or mark comparable-equivalence in eval.
5. **Temperature** on reefer: one representation (setpoint vs “continuous” vs band).


| run_id | filename | contract | http | semantic status |
| --- | --- | --- | --- | --- |
| 38 | JBHunt.pdf | truckerjson | 200 | success |
| 38 | JBHunt.pdf | critical_v1_1 | 200 | success |
| 39 | Armstrong.pdf | truckerjson | 200 | success |
| 39 | Armstrong.pdf | critical_v1_1 | 200 | success |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | truckerjson | 200 | success |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | critical_v1_1 | 200 | success |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | truckerjson | 200 | success |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | critical_v1_1 | 200 | success |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | truckerjson | 200 | success |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | critical_v1_1 | 200 | success |
| 43 | TQLRC.pdf | truckerjson | 200 | success |
| 43 | TQLRC.pdf | critical_v1_1 | 200 | success |

## Field-by-field comparison (extracted + notes)


| run | PDF | field | truckerjson | critical_v1_1 | T mark | C mark | guardrail? | safer C? | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 38 | JBHunt.pdf | broker_name | J.B. Hunt (ICS) | J.B. Hunt, Inc. | needs_review | needs_review | | n/a | |
| 38 | JBHunt.pdf | broker_load_reference | 66P2859 | 66P2859 | needs_review | correct | N | n/a | T: C: |
| 38 | JBHunt.pdf | rate (extracted.rate) | 2841.0 | 2841.0 | correct | correct | | n/a | critical `carrier_rate_total` in context: amount=2841.0 currency='USD' |
| 38 | JBHunt.pdf | equipment_type | 53' Dry Van | 53' Dry Van | correct | correct | | n/a | |
| 38 | JBHunt.pdf | trailer_type | ∅ | ∅ | correct | correct | | n/a | |
| 38 | JBHunt.pdf | trailer_size | ∅ | ∅ | correct | correct | | n/a | |
| 38 | JBHunt.pdf | temperature_requirement | ∅ | ∅ | correct | correct | | n/a | |
| 38 | JBHunt.pdf | commodity | Fak | Fak | correct | correct | | n/a | |
| 38 | JBHunt.pdf | estimated_weight | 42000 | 42000 | correct | correct | | n/a | |
| 38 | JBHunt.pdf | stops[0].sequence | 0 | 1 | needs_review | needs_review | | n/a |  |
| 38 | JBHunt.pdf | stops[0].stop_type | pickup | pickup | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[0].facility_name | Pilkington Urbancrest | Pilkington Urbancrest | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[0].street | 3440 Centerpoint Drive, Suite A | 3440 Centerpoint Drive, Suite A | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[0].city | Urbancrest | Urbancrest | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[0].state_or_province | OH | OH | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[0].postal_code | 43123 | 43123 | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[0].appointment_date | 2026-03-06 | 03/06/2026 | needs_review | needs_review | | n/a |  |
| 38 | JBHunt.pdf | stops[0].appointment_time_text | 07:00 - 12:00 | 07:00 - 12:00 | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[1].sequence | 1 | 2 | needs_review | needs_review | | n/a |  |
| 38 | JBHunt.pdf | stops[1].stop_type | delivery | delivery | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[1].facility_name | Pilkington | Pilkington | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[1].street | 5 Karen Dr, Ste 1 | 5 Karen Dr, Ste 1 | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[1].city | Westbrook | Westbrook | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[1].state_or_province | ME | ME | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[1].postal_code | 04092 | 04092 | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[1].appointment_date | 2026-03-09 | 03/09/2026 | needs_review | needs_review | | n/a |  |
| 38 | JBHunt.pdf | stops[1].appointment_time_text | 08:00 - 12:00 | 08:00 - 12:00 | correct | correct | | n/a |  |
| 38 | JBHunt.pdf | stops[] order/count | 2 stops | 2 stops | — | — | | | OK |
| 39 | Armstrong.pdf | broker_name | Armstrong Transport Group | Armstrong Transport Group | correct | correct | | n/a | |
| 39 | Armstrong.pdf | broker_load_reference | 3872125-1 | ∅ | needs_review | missing | Y | no | T: C:dropped value vs legacy |
| 39 | Armstrong.pdf | rate (extracted.rate) | 1800.0 | 1800.0 | correct | correct | | n/a | critical `carrier_rate_total` in context: amount=1800.0 currency='USD' |
| 39 | Armstrong.pdf | equipment_type | V53, 53' Van | 53' Van 53' | needs_review | needs_review | | n/a | |
| 39 | Armstrong.pdf | trailer_type | ∅ | ∅ | correct | correct | | n/a | |
| 39 | Armstrong.pdf | trailer_size | ∅ | ∅ | correct | correct | | n/a | |
| 39 | Armstrong.pdf | temperature_requirement | ∅ | ∅ | correct | correct | | n/a | |
| 39 | Armstrong.pdf | commodity | Poly Grind | Poly Grind | correct | correct | | n/a | |
| 39 | Armstrong.pdf | estimated_weight | 43000 | 43000 | correct | correct | | n/a | |
| 39 | Armstrong.pdf | stops[0].sequence | 0 | 1 | needs_review | needs_review | | n/a |  |
| 39 | Armstrong.pdf | stops[0].stop_type | pickup | pickup | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[0].facility_name | RAY DORNHECKER | RAY DORNHECKER | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[0].street | 3620 W 38th St | 3620 W 38th St | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[0].city | Chicago | Chicago | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[0].state_or_province | IL | IL | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[0].postal_code | 60632 | 60632 | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[0].appointment_date | 2025-10-28 | 10/28/2025 | needs_review | needs_review | | n/a |  |
| 39 | Armstrong.pdf | stops[0].appointment_time_text | 06:30-10:00 CST | 06:30-10:00 CST | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[1].sequence | 1 | 2 | needs_review | needs_review | | n/a |  |
| 39 | Armstrong.pdf | stops[1].stop_type | delivery | delivery | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[1].facility_name | ICS - NC (REIDSVILLE) | ICS - NC (REIDSVILLE) | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[1].street | 1704 Barnes St | 1704 Barnes St | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[1].city | Reidsville | Reidsville | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[1].state_or_province | NC | NC | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[1].postal_code | 27320 | 27320 | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[1].appointment_date | 2025-10-29 | 10/29/2025 | needs_review | needs_review | | n/a |  |
| 39 | Armstrong.pdf | stops[1].appointment_time_text | 07:00-12:00 | 07:00-12:00 | correct | correct | | n/a |  |
| 39 | Armstrong.pdf | stops[] order/count | 2 stops | 2 stops | — | — | | | OK |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | broker_name | DeGroot Logistics | DeGroot Logistics | correct | correct | | n/a | |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | broker_load_reference | 161836 | 161836 | needs_review | correct | N | n/a | T: C: |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | rate (extracted.rate) | 1900.0 | 1900.0 | correct | correct | | n/a | critical `carrier_rate_total` in context: amount=1900.0 currency='USD' |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | equipment_type | Dry Van 53' | Dry Van 53' | correct | correct | | n/a | |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | trailer_type | ∅ | ∅ | correct | correct | | n/a | |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | trailer_size | ∅ | ∅ | correct | correct | | n/a | |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | temperature_requirement | ∅ | ∅ | correct | correct | | n/a | |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | commodity | Item | ∅ | needs_review | needs_review | | n/a | |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | estimated_weight | 41328 | 41328 | correct | correct | | n/a | |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[0].sequence | 0 | 1 | needs_review | needs_review | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[0].stop_type | pickup | pickup | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[0].facility_name | MICHIGAN SUGAR COMPANY | MICHIGAN SUGAR COMPANY | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[0].street | 947 PINE ST | 947 PINE ST | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[0].city | SEBEWAING | SEBEWAING | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[0].state_or_province | MI | MI | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[0].postal_code | 48759 | 48759 | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[0].appointment_date | 2025-10-16 | 10/16/2025 | needs_review | needs_review | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[0].appointment_time_text | 16:00 | 16:00 | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[1].sequence | 1 | 2 | needs_review | needs_review | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[1].stop_type | delivery | delivery | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[1].facility_name | CENTER VALLEY | CENTER VALLEY | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[1].street | 2700 SAUCON VALLEY ROAD | 2700 SAUCON VALLEY ROAD | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[1].city | CENTER VALLEY | CENTER VALLEY | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[1].state_or_province | PA | PA | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[1].postal_code | 18034 | 18034 | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[1].appointment_date | 2025-10-17 | 10/17/2025 | needs_review | needs_review | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[1].appointment_time_text | 23:50 | 23:50 | correct | correct | | n/a |  |
| 40 | 161836 - FIRST BASE FREIGHT LTD DOT3143231 Highway RateCon - Carrier Rate and Load Confirmation (002).pdf | stops[] order/count | 2 stops | 2 stops | — | — | | | OK |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | broker_name | BM2 Freight Services Inc. - S/C | BM2 Freight Services Inc. | needs_review | needs_review | | n/a | |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | broker_load_reference | 612845 | 612845 | needs_review | correct | N | n/a | T: C: |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | rate (extracted.rate) | 2550.0 | 2550.0 | correct | correct | | n/a | critical `carrier_rate_total` in context: amount=2550.0 currency='USD' |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | equipment_type | Reefer 53' | Reefer 53' | correct | correct | | n/a | |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | trailer_type | ∅ | ∅ | correct | correct | | n/a | |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | trailer_size | ∅ | ∅ | correct | correct | | n/a | |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | temperature_requirement | Continuous | -10.0--10.0 F | needs_review | needs_review | | n/a | different encoding: free text vs setpoint band |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | commodity | Stuffer Bread | Stuffer Bread | correct | correct | | n/a | |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | estimated_weight | 17224 | 17224 | correct | correct | | n/a | |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[0].sequence | 0 | 1 | needs_review | needs_review | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[0].stop_type | pickup | pickup | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[0].facility_name | ASPIRE | ASPIRE | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[0].street | 115 Sinclair Blvd | 115 Sinclair Blvd | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[0].city | Brantford | Brantford | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[0].state_or_province | ON | ON | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[0].postal_code | N3S 7X6 | N3S 7X6 | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[0].appointment_date | 2026-03-31 | 03/31/2026 | needs_review | needs_review | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[0].appointment_time_text | 19:00 | 19:00 | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[1].sequence | 1 | 2 | needs_review | needs_review | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[1].stop_type | delivery | delivery | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[1].facility_name | Romeoville IL Hub | Romeoville IL Hub | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[1].street | 1257 North Schmidt Road | 1257 North Schmidt Road | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[1].city | Romeoville | Romeoville | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[1].state_or_province | IL | IL | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[1].postal_code | 60446 | 60446 | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[1].appointment_date | 2026-04-01 | 04/01/2026 | needs_review | needs_review | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[1].appointment_time_text | 12:30 | 12:30 | correct | correct | | n/a |  |
| 41 | 612845 - MC1397898 9582479 CANADA INC Reefer - Carrier Rate and Load Confirmation.pdf | stops[] order/count | 2 stops | 2 stops | — | — | | | OK |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | broker_name | Hub Group | Hub Group | correct | correct | | n/a | |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | broker_load_reference | 25180652398968 | ∅ | needs_review | missing | Y | no | T: C:dropped value vs legacy |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | rate (extracted.rate) | 1683.02 | 1683.02 | correct | correct | | n/a | critical `carrier_rate_total` in context: amount=1683.02 currency='USD' |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | equipment_type | dry van | dry van 53 | needs_review | needs_review | | n/a | |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | trailer_type | Van | ∅ | needs_review | needs_review | | n/a | |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | trailer_size | 53 | ∅ | needs_review | needs_review | | n/a | |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | temperature_requirement | CONTINUOUS | continuous | needs_review | needs_review | | n/a | |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | commodity | beans and rice | beans and rice | correct | correct | | n/a | |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | estimated_weight | 43000 | 43000 | correct | correct | | n/a | |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[0].sequence | 0 | 1 | needs_review | needs_review | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[0].stop_type | pickup | pickup | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[0].facility_name | Agrocrop Exports Ltd. | Agrocrop Exports Ltd. | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[0].street | 100 Agrocrop Rd | 100 Agrocrop Rd | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[0].city | BOLTON | BOLTON | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[0].state_or_province | ON | ON | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[0].postal_code | L7E 1B1 | L7E 1B1 | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[0].appointment_date | 2025-05-16 | 05/16/2025 | needs_review | needs_review | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[0].appointment_time_text | 1100 | 1100 | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[1].sequence | 1 | 2 | needs_review | needs_review | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[1].stop_type | delivery | delivery | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[1].facility_name | ALDI | ALDI | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[1].street | 295 Rye St | 295 Rye st | needs_review | needs_review | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[1].city | SOUTH WINDSOR | SOUTH WINDSOR | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[1].state_or_province | CT | CT | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[1].postal_code | 06074 | 06074 | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[1].appointment_date | 2025-05-17 | 05/17/2025 | needs_review | needs_review | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[1].appointment_time_text | 0100 | 0100 | correct | correct | | n/a |  |
| 42 | order_confirmation_2398968_4674419509316643175-lme_temp.pdf | stops[] order/count | 2 stops | 2 stops | — | — | | | OK |
| 43 | TQLRC.pdf | broker_name | Total Quality Logistics (TQL) | TQL | needs_review | needs_review | | n/a | |
| 43 | TQLRC.pdf | broker_load_reference | 34307972 | ∅ | needs_review | missing | Y | no | T: C:dropped value vs legacy |
| 43 | TQLRC.pdf | rate (extracted.rate) | 2100.0 | 2100.0 | correct | correct | | n/a | critical `carrier_rate_total` in context: amount=2100.0 currency='USD' |
| 43 | TQLRC.pdf | equipment_type | Van Or Reefer | Van Or Reefer 48 ft or 53 ft | needs_review | needs_review | | n/a | |
| 43 | TQLRC.pdf | trailer_type | Van | ∅ | needs_review | needs_review | | n/a | |
| 43 | TQLRC.pdf | trailer_size | 48 ft or 53 ft | ∅ | needs_review | needs_review | | n/a | |
| 43 | TQLRC.pdf | temperature_requirement | ∅ | ∅ | correct | correct | | n/a | |
| 43 | TQLRC.pdf | commodity | Tobacco and substitutes | Tobacco and substitutes | correct | correct | | n/a | |
| 43 | TQLRC.pdf | estimated_weight | 23000 | 23000 | correct | correct | | n/a | |
| 43 | TQLRC.pdf | stops[0].sequence | 0 | 1 | needs_review | needs_review | | n/a |  |
| 43 | TQLRC.pdf | stops[0].stop_type | pickup | pickup | correct | correct | | n/a |  |
| 43 | TQLRC.pdf | stops[0].facility_name | ∅ | ∅ | missing | missing | | n/a |  |
| 43 | TQLRC.pdf | stops[0].city | Charlotte | Charlotte | correct | correct | | n/a |  |
| 43 | TQLRC.pdf | stops[0].state_or_province | NC | NC | correct | correct | | n/a |  |
| 43 | TQLRC.pdf | stops[0].postal_code | ∅ | ∅ | missing | missing | | n/a |  |
| 43 | TQLRC.pdf | stops[0].appointment_date | 2025-10-29 | 10/29/2025 | needs_review | needs_review | | n/a |  |
| 43 | TQLRC.pdf | stops[0].appointment_time_text | 14:00 | Appt 14:00 | needs_review | needs_review | | n/a |  |
| 43 | TQLRC.pdf | stops[1].sequence | 1 | 2 | needs_review | needs_review | | n/a |  |
| 43 | TQLRC.pdf | stops[1].stop_type | delivery | delivery | correct | correct | | n/a |  |
| 43 | TQLRC.pdf | stops[1].facility_name | ∅ | ∅ | missing | missing | | n/a |  |
| 43 | TQLRC.pdf | stops[1].city | Westborough | Westborough | correct | correct | | n/a |  |
| 43 | TQLRC.pdf | stops[1].state_or_province | MA | MA | correct | correct | | n/a |  |
| 43 | TQLRC.pdf | stops[1].postal_code | ∅ | ∅ | missing | missing | | n/a |  |
| 43 | TQLRC.pdf | stops[1].appointment_date | 2025-10-30 | 10/30/2025 | needs_review | needs_review | | n/a |  |
| 43 | TQLRC.pdf | stops[1].appointment_time_text | 21:00 | Appt 21:00 | needs_review | needs_review | | n/a |  |
| 43 | TQLRC.pdf | stops[] order/count | 2 stops | 2 stops | — | — | | | OK |

## Interpretation (evidence-based, not a default switch)


- **guardrail_changed**: see `parse_diagnostics.critical_extraction_v1_1_guardrails` in critical pass (count logged per run in capture; full payload in `parse_response` only on critical rows).
- **safer (critical vs legacy)**: for `broker_load_reference`, if legacy is **wrong** (nonsense token) and critical is **null**, treat as **safer** on that field.
- Stops: address fields need human verification against the PDF; rows marked `needs_review` on any diff.


## Raw JSON


Per-run `parse_response` objects are not embedded here (large). Re-run the script and add file export if you need archives.

