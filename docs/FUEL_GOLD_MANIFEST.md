# Fuel Gold manifest

**Not established.** There is no `gold/fuel` branch and no `fuel-gold-*` tag yet.

When Fuel is frozen the same way as DL:

1. Create branch `gold/fuel` at the verified commit.
2. Create immutable tag `fuel-gold-YYYY-MM-DD` at that commit.
3. Replace this file with the gold SHA, baked image (if any), dependent files, and parked bugs.
4. Add the row to [GOLD_MODULES.md](./GOLD_MODULES.md).

Do not store Fuel files on `gold/dl` or in `DL_GOLD_MANIFEST.md`.
