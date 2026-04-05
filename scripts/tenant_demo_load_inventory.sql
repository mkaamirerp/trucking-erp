-- Read-only inventory for tenant_demo.loads (run with tenant DB creds).
SELECT COUNT(DISTINCT tenant_id) AS tenants, MIN(tenant_id) AS tid_min, MAX(tenant_id) AS tid_max FROM loads;

SELECT
  CASE
    WHEN load_number ~ '^[0-9]+$' THEN 'numeric_only'
    WHEN load_number ~ '^(L-STOPS|L-READY|L-DRAFT-999|SRCH-|L-REORDER|L-TEST)-' THEN 'pytest_prefix'
    WHEN load_number LIKE 'INT-%' THEN 'intake_INT'
    WHEN load_number LIKE 'DRAFT-%' THEN 'draft_auto'
    ELSE 'other'
  END AS bucket,
  COUNT(*)::bigint AS n
FROM loads
GROUP BY 1
ORDER BY n DESC;

SELECT COUNT(*)::bigint AS loads_without_stops
FROM loads l
WHERE NOT EXISTS (SELECT 1 FROM load_stops s WHERE s.load_id = l.id AND s.tenant_id = l.tenant_id);

SELECT broker_name_snapshot, COUNT(*)::bigint AS n
FROM loads
WHERE broker_name_snapshot IS NOT NULL
GROUP BY 1
ORDER BY n DESC
LIMIT 15;

SELECT COALESCE(b.name, '(no broker row)') AS broker_name, COUNT(*)::bigint AS n
FROM loads l
LEFT JOIN brokers b ON b.id = l.broker_id AND b.tenant_id = l.tenant_id
GROUP BY 1
ORDER BY n DESC
NULLS LAST
LIMIT 15;

SELECT status, COUNT(*)::bigint AS n FROM loads GROUP BY 1 ORDER BY n DESC;

-- Sample newest 5 per bucket for manual review (pattern only)
SELECT load_number, status, broker_name_snapshot,
  (SELECT COUNT(*) FROM load_stops s WHERE s.load_id = l.id AND s.tenant_id = l.tenant_id) AS stop_count
FROM loads l
WHERE load_number ~ '^(L-STOPS|L-READY)-'
ORDER BY l.id DESC
LIMIT 8;

SELECT load_number, status, broker_name_snapshot,
  (SELECT COUNT(*) FROM load_stops s WHERE s.load_id = l.id AND s.tenant_id = l.tenant_id) AS stop_count
FROM loads l
WHERE load_number ~ '^[0-9]+$'
ORDER BY l.id DESC
LIMIT 8;
