# TruckERP documentation map

Module layout after classification move. Prefer each module folder; do not reintroduce competing Load/Trip authority files.

| Module | Path | Notes |
|---|---|---|
| Load / Trip | [`load_trip/`](./load_trip/) | Canonical: [`load_trip/MASTER.md`](./load_trip/MASTER.md) |
| Load Parser | [`load_parser/`](./load_parser/) | contracts/, lab/ |
| DL Parser | [`dl_parser/`](./dl_parser/) | |
| Fuel | [`fuel/`](./fuel/) | |
| Tolls | [`tolls/`](./tolls/) | Canonical: [`tolls/MASTER.md`](./tolls/MASTER.md) |
| People / Driver | [`people_driver/`](./people_driver/) | onboarding/, troubleshooting/ |
| Application / Onboarding | [`application_onboarding/`](./application_onboarding/) | |
| Assets / Fleet | [`assets_fleet/`](./assets_fleet/) | scaffold |
| Login / Auth | [`auth/`](./auth/) | operations/ |
| Email Intake | [`email_intake/`](./email_intake/) | legacy_email/, operations/ |
| Payroll / Settlements | [`payroll_settlements/`](./payroll_settlements/) | settlements/ |
| Finance / Accounting | [`finance_accounting/`](./finance_accounting/) | scaffold |
| Compliance | [`compliance/`](./compliance/) | |
| CA Certificate | [`ca_certificate/`](./ca_certificate/) | scaffold |
| Integrations | [`integrations/`](./integrations/) | vendors/ |
| Platform | [`platform/`](./platform/) | database/, migrations/, … |
| Shared Engineering | [`shared/engineering/`](./shared/engineering/) | |
| Shared Product | [`shared/product/`](./shared/product/) | includes [`DOCUMENTATION_MASTER_INDEX.md`](./shared/product/DOCUMENTATION_MASTER_INDEX.md) |
| Archive | [`archive/`](./archive/) | historical only |
| Review Queue | [`_review/`](./_review/) | unclear / pending split |

**Fixtures still at:** [`fixtures/fuel/`](./fixtures/fuel/), [`fixtures/load_lab/`](./fixtures/load_lab/) (module-owned later). Unclassified fixture material under [`_review/fixtures/`](./_review/fixtures/).
