# TruckERP Integration Reference — LoadStop Catalog

Source snapshot: LoadStop Integrations, checked 2026-09-21.
Source: https://loadstop.com/integrations

Purpose: reference map for TruckERP integration planning. This is not a statement that TruckERP currently supports these integrations. Before building PDF/file parsers, investigate whether the provider exposes an API, SFTP, structured export, partner feed, or other machine-readable integration.

## ELDs — Carrier
- KeepTruckin / Motive
- Samsara
- Geotab
- TrackEnsure
- Orbcomm
- Elog 360
- TruckX
- Omnitracs
- TT ELD
- Beyond GPS
- Verizon Connect
- Fleet Hunt
- Alfa ELD
- BigRoad
- VisTracks
- Coretex
- Isaac ELD
- Vlog ELD
- Ada ELD
- Sparkle ELD
- MyDriverBook
- Forward Thinking
- JJ Keller
- Regulog ELD

## Asset Tracking — Carrier
- Spireon
- FleetSharp
- Anytrek
- Verizon (Assets)
- SkyBitz
- Orbcomm (Assets)
- Thermo King
- RoadReady
- TGI

## Load Boards — Broker
- DAT
- Truckstop
- C.H. Robinson
- Loadsmart
- Uber Freight

## Factoring & Pay — Carrier
- RTS Financial
- First Line Funding Group
- Compass Funding
- Baron Finance
- Revolution Capital
- Flat Rate Funding
- OTR Capital
- TAFS
- Apex Capital
- Love's Financial
- eCapital
- WEX
- Farwest Capital
- PCG
- TAB Bank
- Express Freight Finance

## Accounting
- QuickBooks Online
- QuickBooks Desktop
- NetSuite
- Microsoft Dynamics GP

## Mileage
- Google Mileage
- Trimble / PC Miler
- Trimble Fuel Optimization

## Fuel & Tolls — Carrier
- EFS Fuel Card
- Comdata
- TCS Fuel Card
- Pilot Flying J
- QuickQ
- BVD Fuel Card
- Motive Fuel Card
- Relay Fuel Card
- BTF
- PrePass
- Bestpass

## Visibility
- FourKites — Broker
- Descartes MacroPoint — Carrier
- MacroPoint Brokerage — Broker
- FarEye — Broker
- Project44 (P44) — Broker

## Compliance & Onboarding
- MyCarrierPortal — Broker
- RMIS — Broker
- Highway — Broker
- Tenstreet — Carrier

## Factoring & Pay — Broker
- TriumphPay
- Denim
- Triumph Business Capital
- Epay Manager
- Relay (Lumper)

## Maintenance — Carrier
- Fullbay

## Other
- Gmail
- Microsoft Outlook
- Slack
- Telegram

## TruckERP research notes
1. Treat this catalog as a market/reference checklist, not an implementation specification.
2. For each integration, identify the actual technical rail independently: REST/API, SFTP, EDI, CSV/XLS/DAT export, webhook, partner feed, etc.
3. Corporate ownership does not prove a shared technical adapter. Validate each feed from real documentation or sample data.
4. Prefer structured machine-readable feeds over PDF parsing whenever available.
5. Normalize provider-specific data into TruckERP canonical schemas; keep provider adapters isolated.
6. Fuel/toll/accounting/settlement integrations require strict tenant, unit, owner, currency, amount, duplicate/idempotency, and reconciliation gates.
7. Current high-interest TruckERP research targets include BVD, EFS, Comdata, PrePass, Bestpass, DAT, ELD providers, QuickBooks, and NetSuite.
8. HOS247 was not present in this LoadStop catalog snapshot; investigate HOSconnect/API separately.

## Catalog scope
LoadStop groups the catalog under ELDs, Assets, Loads, Accounting, Factoring, Fuel, Mileage, Visibility, Compliance, Maintenance, and Other. The list above preserves every unique integration displayed on the page at the time checked.
