# TruckERP TODO

## Fuel Card Adjustments — provider-authorized corrections

**Status:** TODO — future Fuel operationalization; do not pull into the current BVD source-review milestone.

**Design:** `docs/FUEL_CARD_ADJUSTMENTS.md`

**Implementation checklist:** `docs/FUEL_CARD_ADJUSTMENTS_TODO.md`

**Architecture reference:** `docs/FUEL_CARD_MODULE_DESIGN.md`

Core rule: a provider correction never overwrites the original provider transaction. TruckERP records a linked adjustment so the company can search a disputed invoice/transaction, capture the provider-authorized correction and evidence, and preserve the original → adjustment(s) → effective-cost audit chain.

Primary relationship:

```text
Fuel-card provider
        ↕
Fleet / company account
        ↕
TruckERP company financial history
```

This is not a driver-dispute or owner-operator-dispute workflow.

---

## Load parser — restore and verify principal load identifier label fallback

**Status:** TODO — do not implement blindly; verify against current rules/tests first.

**Context**

During EC2 worktree cleanup, an uncommitted change from the old `tmp/operational-references-slice` worktree was intentionally backed up before that worktree was removed. The working tree itself is gone, but the exact diff is preserved locally on EC2 at:

```text
~/truckerp_backups/ec2_cleanup_20260920/operational_working.diff
```

The affected function is:

```text
app/services/load_parser_mechanical_validation.py
_strip_load_reference_field_label(...)
```

### What current `main` does

Current `main` reads only:

```python
LOAD_RATE_CON_FIELD_RULES["rules"]["principal_load_identifier"].get(
    "strong_labels"
)
```

So label stripping currently depends only on `strong_labels`.

### What the backed-up uncommitted change did

The preserved diff changed the lookup to:

```python
ident = LOAD_RATE_CON_FIELD_RULES["rules"]["principal_load_identifier"]
raw_labels = ident.get("possible_labels_examples") or ident.get("strong_labels") or []
labels = [
    str(label).strip()
    for label in raw_labels
    if str(label).strip()
]
```

Important: the priority in the preserved change is:

```text
possible_labels_examples
    -> if empty/missing, fall back to strong_labels
```

It is **not** `strong_labels` first.

### Historical detail that caused confusion

The old operational worktree base was using `possible_labels_examples` only. The uncommitted change made that more defensive by falling back to `strong_labels`. Current `main`, however, now uses `strong_labels` only. Therefore there are three observed states:

```text
Old operational base:
    possible_labels_examples ONLY

Backed-up uncommitted change:
    possible_labels_examples FIRST
    -> strong_labels FALLBACK

Current main:
    strong_labels ONLY
```

Do not infer that the backed-up change should be pasted mechanically without checking the current rule contract and tests.

### Cursor task

1. Open `LOAD_RATE_CON_FIELD_RULES["rules"]["principal_load_identifier"]` and inspect the current meaning/content of:
   - `possible_labels_examples`
   - `strong_labels`
2. Inspect current tests around principal load/reference identifier discovery and `_strip_load_reference_field_label`.
3. Confirm whether the intended source-label stripping behavior is still:

```python
possible_labels_examples -> fallback to strong_labels
```

4. If yes, restore the backed-up behavior in `_strip_load_reference_field_label`.
5. Add/adjust regression tests that prove:
   - labels present in `possible_labels_examples` are stripped when followed by the allowed separator;
   - if `possible_labels_examples` is absent/empty, `strong_labels` still works;
   - glued identifiers such as `PO12345` remain untouched;
   - the change does not select a different load identifier; it only strips the leading discovery label;
   - existing rate-confirmation/load-parser fixtures still pass.
6. Run the focused load-parser tests first, then the relevant broader Load regression tests.
7. Show the exact diff and test results before committing.

### Recovery evidence

The exact preserved change can be inspected on EC2 with:

```bash
grep -n -A8 -B8 "possible_labels_examples" \
  ~/truckerp_backups/ec2_cleanup_20260920/operational_working.diff
```

Do not delete that backup until this TODO is resolved and committed to `main`.
