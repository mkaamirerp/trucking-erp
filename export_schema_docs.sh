#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="/home/admin/trucking_erp/docs/db_schema"
mkdir -p "$OUT_DIR"

PG_CONT=trucking_erp-truckerp-postgres-1
PG_USER="postgres"

echo "== Databases (platform + tenants) =="
# Fetch DB list, ensuring we handle potential empty results safely
DBS="$(docker exec -i "$PG_CONT" psql -U "$PG_USER" -tAc "
  select datname
  from pg_database
  where datistemplate=false
    and (datname='trucking_erp' or datname like 'tenant_%')
  order by 1;
" | sed '/^\s*$/d')"

if [ -z "$DBS" ]; then
  echo "❌ No DBs found: trucking_erp or tenant_%"
  exit 1
fi

echo "$DBS" | sed 's/^/ - /'

# README index
{
  echo "# Database Schema Docs"
  echo
  echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "## Included databases"
  echo
  echo "$DBS" | sed 's/^/- `/' | sed 's/$/`/'
  echo
  echo "## Files"
  echo
} > "$OUT_DIR/README.md"

for DB in $DBS; do
  OUT_MD="$OUT_DIR/${DB}__schema.md"
  echo "Processing: $DB..."

  {
    echo "# Schema: $DB"
    echo
    echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
  } > "$OUT_MD"

  # Tables list (schema.table)
  TABLES="$(docker exec -i "$PG_CONT" psql -U "$PG_USER" -d "$DB" -tAc "
    select n.nspname || '.' || c.relname
    from pg_class c
    join pg_namespace n on n.oid=c.relnamespace
    where c.relkind='r'
      and n.nspname not in ('pg_catalog','information_schema')
    order by 1;
  " | sed '/^\s*$/d')"

  echo "## Tables" >> "$OUT_MD"
  echo >> "$OUT_MD"
  echo "$TABLES" | sed 's/^/- `/' | sed 's/$/`/' >> "$OUT_MD"
  echo >> "$OUT_MD"

  while IFS= read -r FULL; do
    [ -z "$FULL" ] && continue
    SCHEMA="${FULL%%.*}"
    TABLE="${FULL#*.}"

    echo "---" >> "$OUT_MD"
    echo >> "$OUT_MD"
    echo "## \`$FULL\`" >> "$OUT_MD"
    echo >> "$OUT_MD"

    # Primary Key Lookup
    PK_COLS="$(docker exec -i "$PG_CONT" psql -U "$PG_USER" -d "$DB" -tAc "
      select coalesce(string_agg(a.attname, ', ' order by x.n), '')
      from (
        select unnest(conkey) as attnum, generate_subscripts(conkey,1) as n
        from pg_constraint
        where contype='p'
          and conrelid='\"$SCHEMA\".\"$TABLE\"'::regclass
      ) x
      join pg_attribute a
        on a.attrelid='\"$SCHEMA\".\"$TABLE\"'::regclass
       and a.attnum=x.attnum;
    " | sed 's/^\s*//;s/\s*$//')"

    if [ -n "$PK_COLS" ]; then
      echo "**Primary Key:** \`($PK_COLS)\`" >> "$OUT_MD"
    else
      echo "**Primary Key:** _(none)_" >> "$OUT_MD"
    fi
    echo >> "$OUT_MD"

    # Foreign Key Lookup
    echo "**Foreign Keys:**" >> "$OUT_MD"
    FK_ROWS="$(docker exec -i "$PG_CONT" psql -U "$PG_USER" -d "$DB" -P pager=off -tAc "
      with fk as (
        select conname, conrelid, confrelid, conkey, confkey, confupdtype, confdeltype
        from pg_constraint
        where contype='f'
          and conrelid='\"$SCHEMA\".\"$TABLE\"'::regclass
      ),
      fk_cols as (
        select
          fk.conname,
          string_agg(a.attname, ', ' order by x.n) as src_cols,
          string_agg(ra.attname, ', ' order by x.n) as ref_cols,
          fk.confrelid::regclass::text as ref_table,
          fk.confupdtype,
          fk.confdeltype
        from fk
        join lateral (
          select generate_subscripts(fk.conkey,1) as n,
                 fk.conkey[generate_subscripts(fk.conkey,1)] as src_attnum,
                 fk.confkey[generate_subscripts(fk.confkey,1)] as ref_attnum
        ) x on true
        join pg_attribute a on a.attrelid=fk.conrelid and a.attnum=x.src_attnum
        join pg_attribute ra on ra.attrelid=fk.confrelid and ra.attnum=x.ref_attnum
        group by fk.conname, fk.confrelid, fk.confupdtype, fk.confdeltype
      )
      select
        conname || ': (' || src_cols || ') -> ' ||
        ref_table || '(' || ref_cols || ') ' ||
        '[ON UPDATE ' ||
        case confupdtype when 'a' then 'NO ACTION' when 'r' then 'RESTRICT' when 'c' then 'CASCADE' when 'n' then 'SET NULL' when 'd' then 'SET DEFAULT' else 'UNKNOWN' end ||
        ', ON DELETE ' ||
        case confdeltype when 'a' then 'NO ACTION' when 'r' then 'RESTRICT' when 'c' then 'CASCADE' when 'n' then 'SET NULL' when 'd' then 'SET DEFAULT' else 'UNKNOWN' end || ']'
      from fk_cols order by conname;
    " | sed '/^\s*$/d')"

    if [ -n "$FK_ROWS" ]; then
      echo "$FK_ROWS" | sed 's/^/- `/' | sed 's/$/`/' >> "$OUT_MD"
    else
      echo "- _(none)_" >> "$OUT_MD"
    fi
    echo >> "$OUT_MD"

    # Columns Table Generation
    echo "### Columns" >> "$OUT_MD"
    echo >> "$OUT_MD"
    echo "| # | Column | Type | Boolean? | Nullable? | Default | Enum values |" >> "$OUT_MD"
    echo "|---:|---|---|---|---|---|---|" >> "$OUT_MD"

    docker exec -i "$PG_CONT" psql -U "$PG_USER" -d "$DB" -P pager=off -tAc "
      with cols as (
        select
          a.attnum as pos,
          a.attname as column_name,
          pg_catalog.format_type(a.atttypid, a.atttypmod) as col_type,
          case when a.atttypid='bool'::regtype then 'YES' else '' end as is_boolean,
          case when a.attnotnull then 'NO' else 'YES' end as is_nullable,
          coalesce(pg_get_expr(ad.adbin, ad.adrelid), '') as col_default,
          a.atttypid
        from pg_attribute a
        join pg_class c on c.oid=a.attrelid
        join pg_namespace n on n.oid=c.relnamespace
        left join pg_attrdef ad on ad.adrelid=a.attrelid and ad.adnum=a.attnum
        where n.nspname='$SCHEMA'
          and c.relname='$TABLE'
          and a.attnum>0
          and not a.attisdropped
        order by a.attnum
      ),
      enums as (
        select t.oid as type_oid,
               string_agg(e.enumlabel, ', ' order by e.enumsortorder) as enum_vals
        from pg_type t
        join pg_enum e on e.enumtypid=t.oid
        group by t.oid
      )
      select pos || '||' || column_name || '||' || replace(col_type, '|', ' ') || '||' || is_boolean || '||' || is_nullable || '||' || replace(col_default, '|', ' ') || '||' || coalesce(enums.enum_vals, '')
      from cols left join enums on enums.type_oid=cols.atttypid;
    " | while IFS="||" read -r POS COL TYP BOOL NUL DEF ENUMS; do
          [ -z "${BOOL:-}" ] && BOOL=" "
          [ -z "${DEF:-}" ] && DEF=" "
          [ -z "${ENUMS:-}" ] && ENUMS=" "
          echo "| $POS | \`$COL\` | $TYP | $BOOL | $NUL | \`$DEF\` | $ENUMS |" >> "$OUT_MD"
        done

    echo >> "$OUT_MD"
  done <<< "$TABLES"

  echo "- [\`${DB}__schema.md\`](./${DB}__schema.md)" >> "$OUT_DIR/README.md"
done

echo "✅ Finished. Output folder: $OUT_DIR"
