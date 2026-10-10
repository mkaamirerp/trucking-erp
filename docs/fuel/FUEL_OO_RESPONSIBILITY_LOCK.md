# TruckERP Fuel — Owner-Operator Fuel Responsibility Lock

**Status:** LOCKED architecture clarification for the Fuel/Card module.

**Applies to:** Fuel/Card architecture, O/O onboarding/configuration, historical responsibility resolution, O/O pricing, settlement handoff, and future O/O Portal.

**Important:** This clarification separates truck ownership, driver assignment, and fuel financial responsibility. It must be applied when Segment 4 code and the main Fuel design/implementation documents are reconciled.

---

## 1. Ownership, driver assignment, and fuel responsibility are separate

TruckERP must not infer who pays for fuel solely from who owns the truck or who is driving it.

There are three distinct relationships:

1. **Truck ownership** — who owns the asset.
2. **Driver assignment** — who operates the truck.
3. **Carrier/O/O commercial agreement** — who is financially responsible for fuel and which pricing terms apply.

These relationships may change independently and must preserve historical truth.

---

## 2. Truck ownership

When a truck is added/onboarded, TruckERP establishes ownership independently:

- `COMPANY`
- `OWNER_OPERATOR`, linked to the applicable O/O/payee

Ownership is effective-dated/historical.

Ownership identifies who owns the asset. **Ownership does not by itself determine who pays for fuel.**

An O/O-owned truck must not automatically create an O/O fuel charge.

---

## 3. Driver assignment

An O/O bringing a truck into the carrier must have an eligible driver for the truck. The driver may be:

- the owner-operator personally, or
- another approved driver supplied/assigned to operate the O/O truck.

Changing the driver does not change truck ownership.

Driver employment/type must not by itself determine fuel financial responsibility.

Example:

```text
Truck 501 owner:        OWNER_OPERATOR / Payee A
Assigned driver:        Driver B
Truck ownership:        still OWNER_OPERATOR / Payee A
Fuel responsibility:   determined by the effective carrier/O/O agreement
```

Therefore logic equivalent to `is_company_driver -> no O/O fuel responsibility` is not an authoritative financial rule.

---

## 4. Carrier/O/O agreement determines fuel responsibility

An O/O-owned truck may legitimately operate under different commercial arrangements.

Fuel responsibility must allow at least:

- `COMPANY/CARRIER`
- `OWNER_OPERATOR`

Example real-world arrangement:

An owner-operator supplies and owns the truck, while the carrier agreement provides that the carrier pays fuel and insurance.

For Fuel/Card this means:

```text
ownership = OWNER_OPERATOR
owner/payee = applicable O/O
fuel responsibility = COMPANY/CARRIER
O/O fuel charge = NONE
```

The truck remains O/O-owned. The carrier-paid fuel term does not convert it into a company-owned truck.

Insurance is mentioned only to demonstrate that asset ownership and expense responsibility are separate concepts. Insurance accounting is not part of the Fuel module.

---

## 5. O/O fuel pricing applies only when the O/O is responsible for fuel

Only after the effective agreement establishes `OWNER_OPERATOR` fuel responsibility may TruckERP resolve and apply an O/O fuel-pricing rule.

Supported pricing modes remain:

1. **No provider/company discount passed through** — O/O is charged pump/retail price.
2. **Full provider/company discount passed through** — O/O receives the full provider discount.
3. **Fixed discount per unit** — configured cents per litre/gallon are passed to the O/O.
4. **Percentage of provider discount** — configured percentage of the provider/company discount is passed to the O/O.

Example:

```text
Pump price:             $3.00 / unit
Provider discount:      $0.25 / unit
Carrier/provider cost:  $2.75 / unit
O/O benefit:            $0.05 / unit
O/O charge price:       $2.95 / unit
```

Provider/source financial truth remains immutable. O/O charge values are derived TruckERP financial values and must remain separate from provider amounts.

---

## 6. Effective dating is mandatory

Truck ownership, carrier/O/O fuel-responsibility terms, and O/O pricing terms must preserve historical/effective dating where applicable.

An agreement may change without changing ownership.

Example:

```text
Jan 1–Jun 30
  ownership: OWNER_OPERATOR
  fuel responsibility: COMPANY/CARRIER

Starting Jul 1
  ownership: same OWNER_OPERATOR
  fuel responsibility: OWNER_OPERATOR
  pricing: configured O/O discount rule
```

A May fuel transaction must continue to resolve under the carrier-paid agreement. A July transaction resolves under the new O/O-paid agreement.

TruckERP must never use today's agreement or pricing rule to rewrite historical fuel responsibility.

---

## 7. Authoritative resolution sequence

Fuel financial responsibility must follow this sequence:

```text
transaction time
    -> historical truck resolution
    -> historical truck ownership
    -> historical O/O/payee when applicable
    -> effective carrier/O/O agreement
    -> fuel financial responsibility
    -> if responsibility = OWNER_OPERATOR:
         effective O/O fuel-pricing rule
    -> derived O/O fuel charge
```

Driver assignment remains operational/audit context. It does not replace the commercial responsibility hierarchy.

AI/parser output is never authoritative for ownership, payee, agreement selection, financial responsibility, O/O pricing, or settlement posting.

---

## 8. Conflict and missing-data behavior

TruckERP must prefer `REVIEW` over guessing.

Expected cases:

- O/O-owned truck + agreement says carrier pays fuel -> valid; no O/O fuel charge.
- O/O-owned truck + agreement says O/O pays fuel -> valid; apply effective O/O pricing.
- O/O-owned truck + another approved driver -> ownership unchanged; agreement still determines fuel responsibility.
- Company-owned truck + unexpected O/O fuel-responsibility data -> `REVIEW` unless an explicitly supported commercial agreement proves that arrangement.
- Missing required agreement/responsibility -> `REVIEW`.
- Contradictory ownership/agreement/responsibility evidence -> `REVIEW`.
- Overlapping effective agreements -> `REVIEW`.
- Multiple applicable pricing rules -> `REVIEW`.

Never silently select whichever field happens to be checked first.

---

## 9. O/O onboarding/configuration relationship

O/O onboarding/configuration is the appropriate source for commercial terms where the existing TruckERP model supports them.

Before adding new Fuel fields, implementation must inspect and reuse accepted onboarding fields rather than creating duplicates.

The combined architecture needs to represent conceptually:

- O/O/payee identity
- O/O-owned truck(s)
- driver(s) assigned to those trucks
- who pays fuel
- O/O fuel pricing/discount mode when the O/O pays
- fixed discount amount when applicable
- percentage of provider discount when applicable
- effective dates/history

A current boolean such as participation in a fuel-discount program is not, by itself, sufficient to represent the full financial-responsibility and pricing agreement if it cannot answer who pays fuel and under which effective terms.

---

## 10. Future O/O Portal relationship

The future O/O Portal must support an owner-operator with one or multiple trucks and drivers.

Conceptual presentation:

```text
O/O / payee
    -> truck
        -> current/historical driver assignment
        -> fuel transactions
        -> carrier-paid vs O/O-responsible fuel
        -> applicable pricing/discount
        -> O/O deductions / settlement
```

The financial charge belongs to the applicable O/O/truck/agreement relationship, not merely to whichever driver purchased the fuel.

---

## 11. Segment 4 implementation consequence

Segment 4 O/O pricing code must not encode either of these shortcuts:

```text
O/O-owned truck -> O/O always pays fuel
company driver -> company always pays fuel
```

Instead, pricing eligibility must consume an authoritative effective fuel-responsibility result from the carrier/O/O agreement layer.

If responsibility is `COMPANY/CARRIER`, O/O charge calculation is not applicable.

If responsibility is `OWNER_OPERATOR`, resolve the effective pricing rule and calculate the derived O/O charge.

If responsibility cannot be established deterministically, return `REVIEW`.

This responsibility gate must be resolved before O/O pricing is allowed to move toward settlement.