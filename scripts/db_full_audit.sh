#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# When DB URLs are not set, run this script inside truckerp-api with env from SSM (db_run.sh).
if [ -z "${DB_FULL_AUDIT_INSIDE:-}" ]; then
  if [ -z "${PLATFORM_DATABASE_URL:-}" ] || [ -z "${TENANT_DATABASE_URL:-}" ]; then
    exec "$SCRIPT_DIR/db_run.sh" bash -c 'export DB_FULL_AUDIT_INSIDE=1; exec /app/scripts/db_full_audit.sh'
  fi
fi
# Inside container: use platform/tenant URLs from truckerp.env if not already set.
if [ -n "${DB_FULL_AUDIT_INSIDE:-}" ]; then
  [ -z "${PLATFORM_DATABASE_URL:-}" ] && [ -n "${DATABASE_URL:-}" ] && export PLATFORM_DATABASE_URL="$DATABASE_URL"
  if [ -z "${TENANT_DATABASE_URL:-}" ]; then
    if [ -n "${ALEMBIC_TENANT_DATABASE_URL:-}" ]; then
      export TENANT_DATABASE_URL="${ALEMBIC_TENANT_DATABASE_URL//+asyncpg/}"
    else
      # Derive tenant URL from platform URL (same host/creds, different db name).
      _template="${POSTGRES_ADMIN_URL:-${DATABASE_URL:-}}"
      _tenant_db="${TENANT_DB_NAME:-tenant_demo}"
      if [ -n "$_template" ]; then
        _base="${_template%/*}"
        export TENANT_DATABASE_URL="${_base}/${_tenant_db}"
        export TENANT_DATABASE_URL="${TENANT_DATABASE_URL//+asyncpg/}"
      fi
      unset _template _tenant_db _base
    fi
  fi
fi

# ============================================================
# DB Full Audit (READ-ONLY)
# Platform + Tenant DB
#
# Output: artifacts/db_full_audit_report.md
# ============================================================

REPORT_PATH="artifacts/db_full_audit_report.md"
mkdir -p "$(dirname "$REPORT_PATH")"

NOW_UTC="$(date -u +"%Y-%m-%d %H:%M:%S UTC")"

# ---- Required env (echo what we're using; redact password) ----
redact_url() {
  local u="$1"
  if [[ "$u" =~ ^(postgresql(\+[^:]+)?://[^:]+:)([^@]*)(@.*)$ ]]; then
    echo "${BASH_REMATCH[1]}***${BASH_REMATCH[4]}"
  else
    echo "(invalid or empty)"
  fi
}
echo "DB audit env:"
if [ -n "${PLATFORM_DATABASE_URL:-}" ]; then echo "  PLATFORM_DATABASE_URL: $(redact_url "$PLATFORM_DATABASE_URL")"; else echo "  PLATFORM_DATABASE_URL: (not set)"; fi
if [ -n "${TENANT_DATABASE_URL:-}" ]; then echo "  TENANT_DATABASE_URL:   $(redact_url "$TENANT_DATABASE_URL")"; else echo "  TENANT_DATABASE_URL:   (not set)"; fi
: "${PLATFORM_DATABASE_URL:?PLATFORM_DATABASE_URL is required (postgresql://...)}"
: "${TENANT_DATABASE_URL:?TENANT_DATABASE_URL is required (postgresql://...)}"
# psql does not accept postgresql+asyncpg://; use plain postgresql:// for platform
PLATFORM_DATABASE_URL_PSQL="${PLATFORM_DATABASE_URL/+asyncpg/}"

# ---- Optional tuning ----
TENANT_LABEL="${TENANT_LABEL:-tenant_demo}"
PSQL_OPTS=(-v ON_ERROR_STOP=0 -X -q -P pager=off)

# Print as markdown code block
md_code() {
  echo '```'
  cat
  echo '```'
}

h1() { echo -e "\n# $1\n"; }
h2() { echo -e "\n## $1\n"; }
h3() { echo -e "\n### $1\n"; }

note() { echo -e "> $1\n"; }

run_sql() {
  # run_sql <db_url> <title> <sql>
  local db_url="$1"
  local title="$2"
  local sql="$3"

  h3 "$title"
  {
    echo "SQL:"
    echo "$sql"
  } | md_code

  echo "Result:"
  if ! echo "$sql" | psql "$db_url" "${PSQL_OPTS[@]}" 2>&1 | md_code; then
    echo "> ⚠️ Query failed (continuing)."
  fi
  echo
}

run_sql_csv() {
  # run_sql_csv <db_url> <title> <sql>
  local db_url="$1"
  local title="$2"
  local sql="$3"

  h3 "$title"
  {
    echo "SQL:"
    echo "$sql"
  } | md_code

  echo "Result (CSV):"
  if ! echo "$sql" | psql "$db_url" "${PSQL_OPTS[@]}" --csv 2>&1 | md_code; then
    echo "> ⚠️ Query failed (continuing)."
  fi
  echo
}

run_sql_table() {
  # run_sql_table <db_url> <title> <sql>
  local db_url="$1"
  local title="$2"
  local sql="$3"

  h3 "$title"
  {
    echo "SQL:"
    echo "$sql"
  } | md_code

  echo "Result (table):"
  if ! echo "$sql" | psql "$db_url" "${PSQL_OPTS[@]}" -P format=aligned -P border=2 2>&1 | md_code; then
    echo "> ⚠️ Query failed (continuing)."
  fi
  echo
}

# ------------------------------------------------------------
# Header (output to terminal)
# ------------------------------------------------------------
h1 "DB Full Audit Report (READ-ONLY)"
note "Generated: $NOW_UTC"
note "Tenant label: $TENANT_LABEL"
note "Platform DB URL: (hidden)"
note "Tenant DB URL: (hidden)"

# ============================================================
# SECTION A — PLATFORM DB AUDIT
# ============================================================
h2 "A) Platform DB Audit"

# A1) List all tables (spot unexpected business tables)
run_sql_table "$PLATFORM_DATABASE_URL_PSQL" "A1) List all tables in public schema" \
"select schemaname, tablename
from pg_catalog.pg_tables
where schemaname = 'public'
order by tablename;"

# A2) Explicitly flag forbidden business table names
run_sql_table "$PLATFORM_DATABASE_URL_PSQL" "A2) Flag forbidden business tables if present" \
"with forbidden(name) as (
  values
    ('drivers'),
    ('loads'),
    ('brokers'),
    ('driver_profiles'),
    ('people'),
    ('person_roles'),
    ('driver_documents'),
    ('driver_document_files'),
    ('pay_runs'),
    ('pay_run_items')
)
select f.name as forbidden_table, to_regclass('public.'||f.name) as regclass
from forbidden f
where to_regclass('public.'||f.name) is not null
order by f.name;"

# A3) Check Alembic version
run_sql_table "$PLATFORM_DATABASE_URL_PSQL" "A3) Platform Alembic version" \
"select * from public.alembic_version;"

# A4) Tenant registry sanity
run_sql_table "$PLATFORM_DATABASE_URL_PSQL" "A4) platform_tenants overview" \
"select id, slug, status, db_status, db_name, provisioned_at, created_at, updated_at
from public.platform_tenants
order by id
limit 200;"

# A5) Verify existence of guardrail view
run_sql_table "$PLATFORM_DATABASE_URL_PSQL" "A5) Guardrail view existence (platform_forbidden_tables)" \
"select to_regclass('public.platform_forbidden_tables') as platform_forbidden_tables_view;"

# A6) Reserved slugs sanity (if present)
run_sql_table "$PLATFORM_DATABASE_URL_PSQL" "A6) reserved slugs table existence + sample" \
"select to_regclass('public.reserved_slugs') as reserved_slugs_regclass;"

run_sql_table "$PLATFORM_DATABASE_URL_PSQL" "A6b) reserved_slugs sample (if table exists)" \
"select *
from public.reserved_slugs
order by created_at desc
limit 50;"

# A7) Unexpected functions/triggers (public schema)
run_sql_table "$PLATFORM_DATABASE_URL_PSQL" "A7) Functions in public schema" \
"select n.nspname as schema, p.proname as function_name, pg_get_function_identity_arguments(p.oid) as args
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
order by p.proname;"

run_sql_table "$PLATFORM_DATABASE_URL_PSQL" "A7b) Triggers in public schema tables" \
"select event_object_table as table_name, trigger_name, action_timing, event_manipulation
from information_schema.triggers
where trigger_schema='public'
order by event_object_table, trigger_name;"

# A8) Sequences in platform
run_sql_table "$PLATFORM_DATABASE_URL_PSQL" "A8) Sequences in platform (public schema)" \
"select sequence_schema, sequence_name, data_type, start_value, minimum_value, maximum_value, increment, cycle_option
from information_schema.sequences
where sequence_schema='public'
order by sequence_name;"

# A9) platform_tenants data quality
run_sql_table "$PLATFORM_DATABASE_URL_PSQL" "A9) Duplicate tenant slugs" \
"select slug, count(*) as cnt
from public.platform_tenants
group by slug
having count(*) > 1
order by cnt desc, slug;"

run_sql_table "$PLATFORM_DATABASE_URL_PSQL" "A9b) Tenants with invalid/empty db_name when READY" \
"select id, slug, status, db_status, db_name
from public.platform_tenants
where (db_status ilike 'READY' or status ilike 'ACTIVE')
  and (db_name is null or btrim(db_name) = '')
order by id;"

# ============================================================
# SECTION B — TENANT DB AUDIT
# ============================================================
h2 "B) Tenant DB Audit"

# B1) List tables
run_sql_table "$TENANT_DATABASE_URL" "B1) List all tables in public schema" \
"select schemaname, tablename
from pg_catalog.pg_tables
where schemaname = 'public'
order by tablename;"

# B2) Tenant alembic version (tenant)
run_sql_table "$TENANT_DATABASE_URL" "B2) Tenant Alembic version" \
"select * from public.alembic_version;"

# B3) Verify tenant guardrail view existence
run_sql_table "$TENANT_DATABASE_URL" "B3) Guardrail view existence (tenant_forbidden_tables)" \
"select to_regclass('public.tenant_forbidden_tables') as tenant_forbidden_tables_view;"

# B4) Foreign keys list (includes on delete, deferrable)
run_sql_table "$TENANT_DATABASE_URL" "B4) Foreign keys (with ON DELETE + deferrable)" \
"select
  con.conname as fk_name,
  nsp.nspname as schema_name,
  rel.relname as table_name,
  a.attname as column_name,
  nsp2.nspname as ref_schema,
  rel2.relname as ref_table,
  a2.attname as ref_column,
  con.confdeltype as on_delete_code,
  case con.confdeltype
    when 'a' then 'NO ACTION'
    when 'r' then 'RESTRICT'
    when 'c' then 'CASCADE'
    when 'n' then 'SET NULL'
    when 'd' then 'SET DEFAULT'
    else con.confdeltype::text
  end as on_delete_action,
  con.condeferrable as deferrable,
  con.condeferred as initially_deferred
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
join pg_class rel2 on rel2.oid = con.confrelid
join pg_namespace nsp2 on nsp2.oid = rel2.relnamespace
join unnest(con.conkey) with ordinality as ck(attnum, ord) on true
join pg_attribute a on a.attrelid = rel.oid and a.attnum = ck.attnum
join unnest(con.confkey) with ordinality as fk(attnum, ord) on fk.ord = ck.ord
join pg_attribute a2 on a2.attrelid = rel2.oid and a2.attnum = fk.attnum
where con.contype = 'f'
  and nsp.nspname = 'public'
order by table_name, fk_name, ck.ord;"

# B5/B6) Unique constraints on composite keys (robust via pg_index/pg_attribute)
run_sql_table "$TENANT_DATABASE_URL" "B5) Verify UNIQUE(tenant_id, id) on people" \
"with idx as (
  select
    t.relname as table_name,
    i.relname as index_name,
    ix.indisunique,
    array_agg(a.attname::text order by x.ord) as cols
  from pg_index ix
  join pg_class t on t.oid = ix.indrelid
  join pg_class i on i.oid = ix.indexrelid
  join unnest(ix.indkey) with ordinality as x(attnum, ord) on true
  join pg_attribute a on a.attrelid = t.oid and a.attnum = x.attnum
  where t.relname = 'people'
  group by t.relname, i.relname, ix.indisunique
)
select *
from idx
where indisunique = true
  and cols = array['tenant_id','id']::text[];"

run_sql_table "$TENANT_DATABASE_URL" "B6) Verify UNIQUE(tenant_id, person_id) on driver_profiles" \
"with idx as (
  select
    t.relname as table_name,
    i.relname as index_name,
    ix.indisunique,
    array_agg(a.attname::text order by x.ord) as cols
  from pg_index ix
  join pg_class t on t.oid = ix.indrelid
  join pg_class i on i.oid = ix.indexrelid
  join unnest(ix.indkey) with ordinality as x(attnum, ord) on true
  join pg_attribute a on a.attrelid = t.oid and a.attnum = x.attnum
  where t.relname = 'driver_profiles'
  group by t.relname, i.relname, ix.indisunique
)
select *
from idx
where indisunique = true
  and cols = array['tenant_id','person_id']::text[];"

# B7) NOT NULL status of critical columns (schema-level)
run_sql_table "$TENANT_DATABASE_URL" "B7) NOT NULL schema flags for critical columns" \
"select table_name, column_name, is_nullable, data_type
from information_schema.columns
where table_schema='public'
  and (
    (table_name='people' and column_name in ('tenant_id','id','email'))
    or (table_name='driver_profiles' and column_name in ('tenant_id','id','person_id'))
    or (table_name='person_roles' and column_name in ('tenant_id','id','person_id'))
  )
order by table_name, column_name;"

# B8-B10) Orphans referencing people (existing pattern + sample ids)
run_sql_table "$TENANT_DATABASE_URL" "B8) Orphan rows: driver_profiles -> people" \
"select count(*) as orphan_count
from public.driver_profiles dp
left join public.people p
  on p.tenant_id = dp.tenant_id and p.id = dp.person_id
where dp.person_id is not null
  and p.id is null;"

run_sql_table "$TENANT_DATABASE_URL" "B8b) Orphan samples: driver_profiles -> people" \
"select dp.id as driver_profile_id, dp.tenant_id, dp.person_id
from public.driver_profiles dp
left join public.people p
  on p.tenant_id = dp.tenant_id and p.id = dp.person_id
where dp.person_id is not null
  and p.id is null
limit 20;"

run_sql_table "$TENANT_DATABASE_URL" "B9) Orphan rows: person_roles -> people" \
"select count(*) as orphan_count
from public.person_roles pr
left join public.people p
  on p.tenant_id = pr.tenant_id and p.id = pr.person_id
where pr.person_id is not null
  and p.id is null;"

run_sql_table "$TENANT_DATABASE_URL" "B9b) Orphan samples: person_roles -> people" \
"select pr.id as person_role_id, pr.tenant_id, pr.person_id
from public.person_roles pr
left join public.people p
  on p.tenant_id = pr.tenant_id and p.id = pr.person_id
where pr.person_id is not null
  and p.id is null
limit 20;"

run_sql_table "$TENANT_DATABASE_URL" "B10) Orphan rows: drivers (legacy) -> people (if exists)" \
"select count(*) as orphan_count
from public.drivers d
left join public.people p
  on p.tenant_id = d.tenant_id and p.id = d.person_id
where d.person_id is not null
  and p.id is null;"

run_sql_table "$TENANT_DATABASE_URL" "B10b) Orphan samples: drivers (legacy) -> people" \
"select d.id as driver_id, d.tenant_id, d.person_id
from public.drivers d
left join public.people p
  on p.tenant_id = d.tenant_id and p.id = d.person_id
where d.person_id is not null
  and p.id is null
limit 20;"

# B11) Indexes that include tenant_id
run_sql_table "$TENANT_DATABASE_URL" "B11) Indexes that include tenant_id" \
"select
  t.relname as table_name,
  i.relname as index_name,
  pg_get_indexdef(i.oid) as indexdef
from pg_index ix
join pg_class t on t.oid = ix.indrelid
join pg_class i on i.oid = ix.indexrelid
join pg_attribute a on a.attrelid = t.oid
where t.relname in ('people','driver_profiles','person_roles','drivers','loads','brokers','driver_documents','driver_document_files')
  and a.attname = 'tenant_id'
  and a.attnum = any(ix.indkey)
order by table_name, index_name;"

# B12) Row counts for core tables
run_sql_table "$TENANT_DATABASE_URL" "B12) Row counts (core tables)" \
"select 'people' as table_name, count(*) as rows from public.people
union all select 'driver_profiles', count(*) from public.driver_profiles
union all select 'person_roles', count(*) from public.person_roles
union all select 'drivers', count(*) from public.drivers
union all select 'loads', count(*) from public.loads
union all select 'brokers', count(*) from public.brokers
union all select 'driver_documents', count(*) from public.driver_documents
union all select 'driver_document_files', count(*) from public.driver_document_files
order by table_name;"

# ------------------------------------------------------------
# NEW: B14) Unexpected columns in core tables (golden list)
# Keep this minimal and focused; expand as schema stabilizes.
# ------------------------------------------------------------
run_sql_table "$TENANT_DATABASE_URL" "B14) Core table columns (compare vs expected manually)" \
"select table_name, column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema='public'
  and table_name in ('people','driver_profiles','person_roles','drivers','loads','brokers')
order by table_name, ordinal_position;"

# B15) Data type mismatches vs expected (lightweight sanity)
run_sql_table "$TENANT_DATABASE_URL" "B15) Type sanity for critical IDs" \
"select table_name, column_name, data_type
from information_schema.columns
where table_schema='public'
  and (
    (table_name='people' and column_name in ('id','tenant_id'))
    or (table_name='driver_profiles' and column_name in ('id','tenant_id','person_id'))
    or (table_name='person_roles' and column_name in ('id','tenant_id','person_id'))
  )
order by table_name, column_name;"

# B16) NOT NULL violations (actual data)
run_sql_table "$TENANT_DATABASE_URL" "B16) Actual NULLs in columns that should not be NULL (spot corruption)" \
"select
  'people.tenant_id' as col, count(*) as null_rows
from public.people where tenant_id is null
union all select 'people.id', count(*) from public.people where id is null
union all select 'driver_profiles.tenant_id', count(*) from public.driver_profiles where tenant_id is null
union all select 'driver_profiles.id', count(*) from public.driver_profiles where id is null
union all select 'driver_profiles.person_id', count(*) from public.driver_profiles where person_id is null
union all select 'person_roles.tenant_id', count(*) from public.person_roles where tenant_id is null
union all select 'person_roles.id', count(*) from public.person_roles where id is null
union all select 'person_roles.person_id', count(*) from public.person_roles where person_id is null
order by col;"

# B17) Unique constraint violations (duplicates in important columns)
run_sql_table "$TENANT_DATABASE_URL" "B17) Duplicate people emails per tenant (if business expects unique)" \
"select tenant_id, lower(email) as email_norm, count(*) as cnt
from public.people
where email is not null and btrim(email) <> ''
group by tenant_id, lower(email)
having count(*) > 1
order by cnt desc, tenant_id
limit 50;"

# B18) Sequences health (out-of-sync)
run_sql_table "$TENANT_DATABASE_URL" "B18) Identity/sequence-backed columns (discover candidates)" \
"select
  c.relname as table_name,
  a.attname as column_name,
  pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname) as seq_name
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
join pg_attribute a on a.attrelid = c.oid
where n.nspname='public'
  and c.relkind='r'
  and a.attnum > 0
  and not a.attisdropped
  and pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname) is not null
order by table_name, column_name;"

run_sql_table "$TENANT_DATABASE_URL" "B18b) Sequence vs MAX(id) checks (common core tables)" \
"with seqs as (
  select
    'people'::text as table_name,
    'id'::text as column_name,
    pg_get_serial_sequence('public.people','id') as seq_name
  union all
  select 'driver_profiles','id', pg_get_serial_sequence('public.driver_profiles','id')
  union all
  select 'person_roles','id', pg_get_serial_sequence('public.person_roles','id')
  union all
  select 'drivers','id', pg_get_serial_sequence('public.drivers','id')
),
vals as (
  select
    s.table_name,
    s.column_name,
    s.seq_name,
    (select max(id) from public.people) as people_max_id,
    (select max(id) from public.driver_profiles) as driver_profiles_max_id,
    (select max(id) from public.person_roles) as person_roles_max_id,
    (select max(id) from public.drivers) as drivers_max_id
  from seqs s
)
select *
from vals;"

# B19) Foreign keys referencing people that are missing tenant_id
run_sql_table "$TENANT_DATABASE_URL" "B19) FKs referencing people that do NOT include tenant_id (CRITICAL)" \
"with fk_cols as (
  select
    con.oid,
    con.conname as fk_name,
    rel.relname as table_name,
    rel2.relname as ref_table,
    array_agg(a.attname order by ck.ord) as cols,
    array_agg(a2.attname order by ck.ord) as ref_cols
  from pg_constraint con
  join pg_class rel on rel.oid = con.conrelid
  join pg_class rel2 on rel2.oid = con.confrelid
  join pg_namespace nsp on nsp.oid = rel.relnamespace
  join unnest(con.conkey) with ordinality as ck(attnum, ord) on true
  join pg_attribute a on a.attrelid = rel.oid and a.attnum = ck.attnum
  join unnest(con.confkey) with ordinality as fk(attnum, ord) on fk.ord = ck.ord
  join pg_attribute a2 on a2.attrelid = rel2.oid and a2.attnum = fk.attnum
  where con.contype='f'
    and nsp.nspname='public'
  group by con.oid, con.conname, rel.relname, rel2.relname
)
select *
from fk_cols
where ref_table='people'
  and not ('tenant_id' = any(cols) and 'tenant_id' = any(ref_cols))
order by table_name, fk_name;"

# B20) Actual cross-tenant links (tenant_id differs across join)
run_sql_table "$TENANT_DATABASE_URL" "B20) Cross-tenant mismatches (driver_profiles -> people)" \
"select dp.id as driver_profile_id, dp.tenant_id as dp_tenant, p.tenant_id as people_tenant, dp.person_id
from public.driver_profiles dp
join public.people p on p.id = dp.person_id
where dp.tenant_id <> p.tenant_id
limit 50;"

run_sql_table "$TENANT_DATABASE_URL" "B20b) Cross-tenant mismatches (person_roles -> people)" \
"select pr.id as person_role_id, pr.tenant_id as pr_tenant, p.tenant_id as people_tenant, pr.person_id
from public.person_roles pr
join public.people p on p.id = pr.person_id
where pr.tenant_id <> p.tenant_id
limit 50;"

run_sql_table "$TENANT_DATABASE_URL" "B20c) Cross-tenant mismatches (drivers legacy -> people)" \
"select d.id as driver_id, d.tenant_id as d_tenant, p.tenant_id as people_tenant, d.person_id
from public.drivers d
join public.people p on p.id = d.person_id
where d.tenant_id <> p.tenant_id
limit 50;"

# B21) Table owners
run_sql_table "$TENANT_DATABASE_URL" "B21) Table owners (public schema)" \
"select c.relname as table_name, pg_catalog.pg_get_userbyid(c.relowner) as owner
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname='public'
  and c.relkind='r'
order by table_name;"

# B22) Table sizes and bloat estimate (size only, read-only)
run_sql_table "$TENANT_DATABASE_URL" "B22) Table sizes (pg_total_relation_size)" \
"select
  c.relname as table_name,
  pg_size_pretty(pg_total_relation_size(c.oid)) as total_size,
  pg_size_pretty(pg_relation_size(c.oid)) as table_size,
  pg_size_pretty(pg_indexes_size(c.oid)) as indexes_size
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname='public'
  and c.relkind='r'
order by pg_total_relation_size(c.oid) desc
limit 50;"

# B23) Unused or duplicate indexes (stat-based + definition listing)
run_sql_table "$TENANT_DATABASE_URL" "B23) Index usage stats (pg_stat_user_indexes)" \
"select
  schemaname,
  relname as table_name,
  indexrelname as index_name,
  idx_scan,
  pg_size_pretty(pg_relation_size(indexrelid)) as index_size
from pg_stat_user_indexes
where schemaname='public'
order by idx_scan asc, pg_relation_size(indexrelid) desc
limit 100;"

run_sql_table "$TENANT_DATABASE_URL" "B23b) Index definitions (spot duplicates/near-duplicates)" \
"select
  t.relname as table_name,
  i.relname as index_name,
  pg_get_indexdef(i.oid) as indexdef
from pg_index ix
join pg_class t on t.oid = ix.indrelid
join pg_class i on i.oid = ix.indexrelid
join pg_namespace n on n.oid = t.relnamespace
where n.nspname='public'
order by t.relname, i.relname;"

# B24) Check constraints summary
run_sql_table "$TENANT_DATABASE_URL" "B24) Check constraints (public schema)" \
"select
  con.conname as check_name,
  rel.relname as table_name,
  pg_get_constraintdef(con.oid) as definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where con.contype='c'
  and nsp.nspname='public'
order by table_name, check_name;"

# B25) Default values for core columns
run_sql_table "$TENANT_DATABASE_URL" "B25) Column defaults (core tables)" \
"select table_name, column_name, column_default
from information_schema.columns
where table_schema='public'
  and table_name in ('people','driver_profiles','person_roles','drivers','loads','brokers')
  and column_default is not null
order by table_name, column_name;"

# ------------------------------------------------------------
# Missing indexes on FK columns (performance trap)
# ------------------------------------------------------------
run_sql_table "$TENANT_DATABASE_URL" "B26) FK columns missing a supporting index (heuristic)" \
"with fks as (
  select
    con.conname as fk_name,
    rel.relname as table_name,
    array_agg(a.attname order by ck.ord) as fk_cols
  from pg_constraint con
  join pg_class rel on rel.oid = con.conrelid
  join pg_namespace nsp on nsp.oid = rel.relnamespace
  join unnest(con.conkey) with ordinality as ck(attnum, ord) on true
  join pg_attribute a on a.attrelid = rel.oid and a.attnum = ck.attnum
  where con.contype='f'
    and nsp.nspname='public'
  group by con.conname, rel.relname
),
idx_cols as (
  select
    t.relname as table_name,
    i.relname as index_name,
    array_agg(a.attname order by x.ord) as cols
  from pg_index ix
  join pg_class t on t.oid = ix.indrelid
  join pg_class i on i.oid = ix.indexrelid
  join pg_namespace n on n.oid = t.relnamespace
  join unnest(ix.indkey) with ordinality as x(attnum, ord) on true
  join pg_attribute a on a.attrelid = t.oid and a.attnum = x.attnum
  where n.nspname='public'
  group by t.relname, i.relname
)
select
  f.table_name,
  f.fk_name,
  f.fk_cols,
  coalesce((
    select string_agg(ic.index_name, ', ')
    from idx_cols ic
    where ic.table_name = f.table_name
      and ic.cols[1:array_length(f.fk_cols,1)] = f.fk_cols
  ), '(no left-prefix index)') as supporting_indexes
from fks f
order by supporting_indexes, f.table_name, f.fk_name;"

# ============================================================
# NEW ADDITIONAL CHECKS (B27–B31)
# ============================================================

run_sql_table "$TENANT_DATABASE_URL" "B27) Tables without a primary key" \
"select c.relname as table_name
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind = 'r'
  and not exists (
    select 1 from pg_index i
    where i.indrelid = c.oid and i.indisprimary
  )
order by table_name;"

run_sql_table "$TENANT_DATABASE_URL" "B28) Exact duplicate indexes (same columns)" \
"with idx_cols as (
  select
    t.relname as table_name,
    i.relname as index_name,
    array_agg(a.attname order by x.ord) as cols,
    pg_get_indexdef(i.oid) as def
  from pg_index ix
  join pg_class t on t.oid = ix.indrelid
  join pg_class i on i.oid = ix.indexrelid
  join pg_namespace n on n.oid = t.relnamespace
  join unnest(ix.indkey) with ordinality as x(attnum, ord) on true
  join pg_attribute a on a.attrelid = t.oid and a.attnum = x.attnum
  where n.nspname = 'public'
  group by t.relname, i.relname, i.oid
)
select table_name, cols, count(*) as idx_count,
       string_agg(index_name, ', ') as index_names
from idx_cols
group by table_name, cols
having count(*) > 1
order by table_name, cols;"

run_sql_table "$TENANT_DATABASE_URL" "B29) Orphaned sequences not owned by any column" \
"select seq_ns.nspname as schema_name, seq.relname as seq_name
from pg_class seq
join pg_namespace seq_ns on seq_ns.oid = seq.relnamespace
left join pg_depend d on d.objid = seq.oid and d.deptype = 'a'
left join pg_class owned_tbl on owned_tbl.oid = d.refobjid
where seq.relkind = 'S'
  and seq_ns.nspname = 'public'
  and owned_tbl is null;"

run_sql_table "$TENANT_DATABASE_URL" "B30) Invalid (NOT VALID) constraints" \
"select conname, conrelid::regclass as table_name, pg_get_constraintdef(oid)
from pg_constraint
where convalidated = false;"

run_sql_table "$TENANT_DATABASE_URL" "B31) Tables without any indexes" \
"select c.relname as table_name
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind = 'r'
  and not exists (
    select 1 from pg_index i where i.indrelid = c.oid
  )
order by table_name;"

# ============================================================
# END
# ============================================================
h2 "END"
note "Done."
