#!/usr/bin/env python3
"""Read-only export of tenant_demo Fuel tables into fuel_db_audit/."""

from __future__ import annotations

import csv
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("FUEL_DB_AUDIT_OUT", str(ROOT / "fuel_db_audit")))
USE_DOCKER = os.environ.get("FUEL_DB_AUDIT_DOCKER", "1") == "1"
DOCKER_CONTAINER = os.environ.get("FUEL_DB_AUDIT_CONTAINER", "truckerp-api")

BATCHES = {
    "bvd_838710": {"batch_id": 5, "import_ref": "b45e8c49-ca95-49f9-bc05-71ab33fb66d6", "invoice": "838710"},
    "bvd_972201": {"batch_id": 7, "import_ref": "917c3d52-c1d5-4c18-afec-46ff6275ac5c", "invoice": "972201"},
    "nationwide_20250522B_06142026": {
        "batch_id": 8,
        "import_ref": "eab57e99-c4bf-40e3-ba2e-21141729a8d8",
        "invoice": "20250522B-06142026",
    },
}

FUEL_TABLES = [
    "fuel_provider_connections",
    "fuel_source_batches",
    "fuel_transactions",
    "fuel_charge_category",
    "fuel_provider_category_mapping",
    "fuel_transaction_financial_event",
    "fuel_transaction_classification_event",
    "fuel_oo_pricing_rules",
    "fuel_source_controls",
    "fuel_extraction_corrections",
    "fuel_card_account_assignments",
    "fuel_bvd",
    "fuel_bvd_field_correction",
    "fuel_bvd_import_stage",
    "fuel_bvd_stage_row",
    "fuel_bvd_stage_field_correction",
    "fuel_nationwide",
    "fuel_nationwide_field_correction",
    "fuel_nationwide_import_stage",
    "fuel_nationwide_stage_row",
    "fuel_nationwide_stage_field_correction",
]


def _docker_bash(script: str) -> str:
    return subprocess.check_output(
        [
            "docker",
            "exec",
            DOCKER_CONTAINER,
            "bash",
            "-lc",
            f"set -a && . /run/secrets/truckerp.env && set +a && {script}",
        ],
        text=True,
    )


def pg_url() -> str:
    if USE_DOCKER:
        raw = _docker_bash('echo -n "$TENANT_DATABASE_URL"').strip()
    else:
        raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL", "")
    if not raw:
        raise RuntimeError("TENANT_DATABASE_URL not set")
    if raw.startswith("postgresql+asyncpg://"):
        return "postgresql://" + raw[len("postgresql+asyncpg://") :]
    return raw


def psql_query(sql: str) -> str:
    url = pg_url()
    esc = sql.replace("'", "'\"'\"'")
    if USE_DOCKER:
        out = _docker_bash(
            'P="${TENANT_DATABASE_URL/postgresql+asyncpg:/postgresql:}" && '
            f"psql \"$P\" -v ON_ERROR_STOP=1 -t -A -c '{esc}'"
        )
    else:
        out = subprocess.check_output(
            ["psql", url, "-v", "ON_ERROR_STOP=1", "-t", "-A", "-c", sql],
            text=True,
        )
    return out.strip()


def psql_copy_csv(sql: str, path: Path) -> None:
    url = pg_url()
    path.parent.mkdir(parents=True, exist_ok=True)
    esc = sql.replace("'", "'\"'\"'")
    if USE_DOCKER:
        data = _docker_bash(
            'P="${TENANT_DATABASE_URL/postgresql+asyncpg:/postgresql:}" && '
            f"psql \"$P\" -v ON_ERROR_STOP=1 -c \"\\copy ({esc}) TO STDOUT WITH CSV HEADER\""
        )
        path.write_text(data, encoding="utf-8")
    else:
        with path.open("w", encoding="utf-8", newline="") as f:
            subprocess.check_call(
                ["psql", url, "-v", "ON_ERROR_STOP=1", "-c", f"\\copy ({sql}) TO STDOUT WITH CSV HEADER"],
                stdout=f,
            )


def main() -> None:
    for sub in ("schema", "data", "lineage", "diagnostics"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)

    db_name = psql_query("SELECT current_database();")
    tenant_id = psql_query("SELECT DISTINCT tenant_id FROM fuel_source_batches ORDER BY tenant_id LIMIT 1;")
    now = datetime.now(timezone.utc).isoformat()

    identity = {
        "exported_at_utc": now,
        "database_name": db_name,
        "tenant_id_sample": tenant_id,
        "host_context": "truckerp-api container / tenant_demo",
        "batch_keys": BATCHES,
        "note": "Read-only snapshot; no credentials in this bundle.",
    }
    (OUT / "database_identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")

    if USE_DOCKER:
        alembic_rev = _docker_bash("cd /app && alembic -c alembic_tenant.ini current 2>/dev/null | head -1").strip()
    else:
        alembic_rev = subprocess.check_output(
            ["bash", "-lc", "cd /app && alembic -c alembic_tenant.ini current 2>/dev/null | head -1"],
            text=True,
            cwd=str(ROOT),
        ).strip()
    (OUT / "alembic_version.txt").write_text(alembic_rev + "\n", encoding="utf-8")

    url = pg_url()
    dump_args = ["pg_dump", url, "--schema-only", "--no-owner", "--no-privileges"] + sum(
        [["-t", t] for t in FUEL_TABLES], []
    )
    if USE_DOCKER:
        tables = " ".join(FUEL_TABLES)
        schema_sql = _docker_bash(
            f'U="${{TENANT_DATABASE_URL/postgresql+asyncpg:/postgresql:}}" && '
            f'pg_dump "$U" --schema-only --no-owner --no-privileges '
            + " ".join(f"-t {t}" for t in FUEL_TABLES)
        )
    else:
        schema_sql = subprocess.check_output(dump_args, text=True)
    (OUT / "schema" / "fuel_tables_schema.sql").write_text(schema_sql, encoding="utf-8")

    meta_sql = """
    SELECT json_agg(row_to_json(t) ORDER BY t.table_name, t.ordinal_position)
    FROM (
      SELECT
        c.table_name,
        c.column_name,
        c.ordinal_position,
        c.data_type,
        c.is_nullable,
        c.column_default
      FROM information_schema.columns c
      WHERE c.table_schema = 'public'
        AND c.table_name LIKE 'fuel_%'
    ) t;
    """
    cols = json.loads(psql_query(meta_sql) or "[]")
    idx_sql = """
    SELECT json_agg(row_to_json(t))
    FROM (
      SELECT tablename AS table_name, indexname, indexdef
      FROM pg_indexes
      WHERE schemaname = 'public' AND tablename LIKE 'fuel_%'
      ORDER BY tablename, indexname
    ) t;
    """
    indexes = json.loads(psql_query(idx_sql) or "null")
    con_sql = """
    SELECT json_agg(row_to_json(t))
    FROM (
      SELECT
        tc.table_name,
        tc.constraint_name,
        tc.constraint_type,
        kcu.column_name,
        ccu.table_name AS foreign_table_name,
        ccu.column_name AS foreign_column_name
      FROM information_schema.table_constraints tc
      LEFT JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
      LEFT JOIN information_schema.constraint_column_usage ccu
        ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
      WHERE tc.table_schema = 'public' AND tc.table_name LIKE 'fuel_%'
      ORDER BY tc.table_name, tc.constraint_name
    ) t;
    """
    constraints = json.loads(psql_query(con_sql) or "null")
    (OUT / "schema" / "columns_constraints_indexes.json").write_text(
        json.dumps({"columns": cols, "indexes": indexes, "constraints": constraints}, indent=2) + "\n",
        encoding="utf-8",
    )

    psql_copy_csv("SELECT * FROM fuel_source_batches ORDER BY id", OUT / "data" / "source_batches.csv")
    psql_copy_csv("SELECT * FROM fuel_source_controls ORDER BY batch_id, id", OUT / "data" / "source_controls.csv")
    psql_copy_csv(
        "SELECT * FROM fuel_transactions ORDER BY batch_id, source_row_order, id",
        OUT / "data" / "canonical_transactions.csv",
    )

    psql_copy_csv(
        f"SELECT * FROM fuel_bvd WHERE import_id = '{BATCHES['bvd_972201']['import_ref']}'::uuid ORDER BY id",
        OUT / "data" / "bvd_972201_native.csv",
    )
    psql_copy_csv(
        f"SELECT * FROM fuel_bvd WHERE import_id = '{BATCHES['bvd_838710']['import_ref']}'::uuid ORDER BY id",
        OUT / "data" / "bvd_838710_native.csv",
    )
    psql_copy_csv(
        f"SELECT * FROM fuel_nationwide WHERE import_id = '{BATCHES['nationwide_20250522B_06142026']['import_ref']}'::uuid ORDER BY id",
        OUT / "data" / "nationwide_20250522B_06142026_native.csv",
    )

    corrections = {
        "fuel_bvd_field_correction": json.loads(
            psql_query(
                "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM ("
                "SELECT * FROM fuel_bvd_field_correction WHERE import_id IN ("
                f"'{BATCHES['bvd_972201']['import_ref']}'::uuid, '{BATCHES['bvd_838710']['import_ref']}'::uuid)"
                " ORDER BY id) t;"
            )
        ),
        "fuel_nationwide_field_correction": json.loads(
            psql_query(
                "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM ("
                "SELECT * FROM fuel_nationwide_field_correction WHERE import_id = "
                f"'{BATCHES['nationwide_20250522B_06142026']['import_ref']}'::uuid ORDER BY id) t;"
            )
        ),
        "fuel_bvd_import_stage": json.loads(
            psql_query(
                "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM ("
                "SELECT * FROM fuel_bvd_import_stage WHERE stage_id IN ("
                f"'{BATCHES['bvd_972201']['import_ref']}'::uuid, '{BATCHES['bvd_838710']['import_ref']}'::uuid)"
                " ORDER BY stage_id) t;"
            )
        ),
        "fuel_bvd_stage_row": json.loads(
            psql_query(
                "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM ("
                "SELECT sr.* FROM fuel_bvd_stage_row sr "
                f"WHERE sr.stage_id IN ('{BATCHES['bvd_972201']['import_ref']}'::uuid, "
                f"'{BATCHES['bvd_838710']['import_ref']}'::uuid)"
                " ORDER BY sr.id) t;"
            )
        ),
        "fuel_nationwide_import_stage": json.loads(
            psql_query(
                "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM ("
                "SELECT * FROM fuel_nationwide_import_stage WHERE stage_id = "
                f"'{BATCHES['nationwide_20250522B_06142026']['import_ref']}'::uuid ORDER BY stage_id) t;"
            )
        ),
        "fuel_nationwide_stage_row": json.loads(
            psql_query(
                "SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM ("
                "SELECT sr.* FROM fuel_nationwide_stage_row sr "
                f"WHERE sr.stage_id = '{BATCHES['nationwide_20250522B_06142026']['import_ref']}'::uuid"
                " ORDER BY sr.id) t;"
            )
        ),
    }
    (OUT / "data" / "corrections_and_stage.json").write_text(
        json.dumps(corrections, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    for key, spec in [
        ("bvd_972201_row_crosswalk.csv", BATCHES["bvd_972201"]),
        ("bvd_838710_row_crosswalk.csv", BATCHES["bvd_838710"]),
        ("nationwide_row_crosswalk.csv", BATCHES["nationwide_20250522B_06142026"]),
    ]:
        bid = spec["batch_id"]
        iref = spec["import_ref"]
        provider = "BVD" if key.startswith("bvd") else "NATIONWIDE"
        native = "fuel_bvd" if provider == "BVD" else "fuel_nationwide"
        sql = f"""
        SELECT
          t.batch_id,
          t.id AS canonical_transaction_id,
          t.source_row_order,
          t.source_row_id,
          n.id AS native_row_id,
          n.row_type AS native_row_type
        FROM fuel_transactions t
        LEFT JOIN {native} n
          ON n.import_id = '{iref}'::uuid
         AND t.source_row_id = n.id::text
        WHERE t.batch_id = {bid}
        ORDER BY t.source_row_order, t.id
        """
        psql_copy_csv(sql.strip(), OUT / "lineage" / key)

    counts = json.loads(
        psql_query(
            """
            SELECT json_build_object(
              'fuel_source_batches', (SELECT COUNT(*) FROM fuel_source_batches),
              'fuel_source_controls', (SELECT COUNT(*) FROM fuel_source_controls),
              'fuel_transactions', (SELECT COUNT(*) FROM fuel_transactions),
              'fuel_bvd_rows', (SELECT COUNT(*) FROM fuel_bvd),
              'fuel_nationwide_rows', (SELECT COUNT(*) FROM fuel_nationwide),
              'by_batch', (
                SELECT COALESCE(json_agg(row_to_json(x)), '[]'::json) FROM (
                  SELECT batch_id, COUNT(*) AS transaction_count
                  FROM fuel_transactions GROUP BY batch_id ORDER BY batch_id
                ) x
              ),
              'native_bvd_972201', (SELECT COUNT(*) FROM fuel_bvd WHERE import_id = """
            + f"'{BATCHES['bvd_972201']['import_ref']}'"
            + """),
              'native_bvd_838710', (SELECT COUNT(*) FROM fuel_bvd WHERE import_id = """
            + f"'{BATCHES['bvd_838710']['import_ref']}'"
            + """),
              'native_nationwide', (SELECT COUNT(*) FROM fuel_nationwide WHERE import_id = """
            + f"'{BATCHES['nationwide_20250522B_06142026']['import_ref']}'"
            + """)
            );
            """
        )
    )
    (OUT / "diagnostics" / "counts.json").write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")

    money = json.loads(
        psql_query(
            """
            SELECT COALESCE(json_agg(row_to_json(x)), '[]'::json) FROM (
              SELECT batch_id, currency,
                SUM(total_amount) AS sum_total_amount,
                SUM(provider_discount_amount) AS sum_provider_discount_amount,
                SUM(pre_tax_amount) AS sum_pre_tax_amount
              FROM fuel_transactions
              GROUP BY batch_id, currency
              ORDER BY batch_id, currency
            ) x;
            """
        )
    )
    (OUT / "diagnostics" / "money_sums.json").write_text(json.dumps(money, indent=2) + "\n", encoding="utf-8")

    null_zero = json.loads(
        psql_query(
            """
            SELECT json_build_object(
              'provider_discount_amount_null', (SELECT COUNT(*) FROM fuel_transactions WHERE provider_discount_amount IS NULL),
              'provider_discount_amount_zero', (SELECT COUNT(*) FROM fuel_transactions WHERE provider_discount_amount = 0),
              'provider_discount_amount_positive', (SELECT COUNT(*) FROM fuel_transactions WHERE provider_discount_amount > 0),
              'provider_discount_amount_negative', (SELECT COUNT(*) FROM fuel_transactions WHERE provider_discount_amount < 0),
              'transaction_date_null', (SELECT COUNT(*) FROM fuel_transactions WHERE transaction_date IS NULL),
              'total_amount_null', (SELECT COUNT(*) FROM fuel_transactions WHERE total_amount IS NULL)
            );
            """
        )
    )
    (OUT / "diagnostics" / "null_vs_zero.json").write_text(json.dumps(null_zero, indent=2) + "\n", encoding="utf-8")

    readme = f"""Fuel database audit snapshot (read-only)
============================================

Exported: {now}
Database: {db_name}
Tenant id (from batches): {tenant_id}
Alembic tenant head: {alembic_rev}

Batches included:
  - BVD 838710 (batch_id=5)
  - BVD 972201 (batch_id=7)
  - Nationwide 20250522B-06142026 (batch_id=8)

Regenerate (from host, API container has psql):
  docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && python3 /path/to/export_fuel_db_audit.py'

This bundle is for forensic / ChatGPT audit only. No secrets.
"""
    (OUT / "README.txt").write_text(readme, encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
