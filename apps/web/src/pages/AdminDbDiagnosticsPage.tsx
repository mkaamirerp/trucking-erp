import { useEffect, useMemo, useState } from "react";
import { fetchWithTenant } from "../api";
import Card from "../components/Card";
import StatusBadge from "../components/StatusBadge";

type Severity = "INFO" | "WARN" | "CRITICAL";

type Signal = {
  severity: Severity;
  title: string;
  what_it_means: string;
  why_we_care: string;
  how_to_fix: string;
  data?: unknown;
};

type DiagnosticsResponse = {
  versions: {
    platform_db: { alembic_version: string | null };
    tenant_db: { alembic_version: string | null };
  };
  guardrails: {
    platform_forbidden_tables_view: string | null;
    tenant_forbidden_tables_view: string | null;
  };
  forbidden_tables: {
    platform_found: string[];
    tenant_found: string[];
  };
  signals: Signal[];
  incidents: {
    tenant: unknown[];
    platform: unknown[];
  };
  context: {
    tenant_id: number | null;
    tenant_slug: string | null;
    user_id: string;
    role: string | null;
  };
};

const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

function severityColor(sev: Severity): "gray" | "yellow" | "red" {
  if (sev === "CRITICAL") return "red";
  if (sev === "WARN") return "yellow";
  return "gray";
}

export default function AdminDbDiagnosticsPage() {
  const [data, setData] = useState<DiagnosticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchWithTenant(`${API_BASE}/admin/diagnostics/db`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await res.text());
        return res.json() as Promise<DiagnosticsResponse>;
      })
      .then((json) => {
        if (!cancelled) setData(json);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load diagnostics");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const summary = useMemo(() => {
    const platformForbidden = data?.forbidden_tables.platform_found?.length ?? 0;
    const tenantForbidden = data?.forbidden_tables.tenant_found?.length ?? 0;
    const tenantViewMissing = data ? !data.guardrails.tenant_forbidden_tables_view : false;
    const hasCritical = (data?.signals ?? []).some((s) => s.severity === "CRITICAL");
    return {
      platformForbidden,
      tenantForbidden,
      tenantViewMissing,
      hasCritical,
    };
  }, [data]);

  if (loading) {
    return <div className="text-sm text-gray-700">Loading diagnostics…</div>;
  }

  if (error) {
    return (
      <div className="space-y-2">
        <h1 className="text-lg font-semibold">Database Diagnostics</h1>
        <p className="text-sm text-red-700 whitespace-pre-wrap">{error}</p>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold">Database Diagnostics</h1>
          <p className="text-sm text-gray-600">
            Read-only report: guardrails, migrations, and safety signals for platform/tenant DB.
          </p>
        </div>
        <div className="text-xs text-gray-500 text-right">
          <div>
            Tenant: <span className="font-medium">{data.context.tenant_slug ?? data.context.tenant_id ?? "?"}</span>
          </div>
          <div>
            Role: <span className="font-medium">{data.context.role ?? "?"}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium">Platform forbidden tables</div>
            <StatusBadge status={summary.platformForbidden ? "CRITICAL" : "OK"} />
          </div>
          <div className="text-xs text-gray-600 mt-1">
            Found: <span className="font-medium">{summary.platformForbidden}</span>
          </div>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium">Tenant forbidden tables</div>
            <StatusBadge
              status={summary.tenantForbidden ? "CRITICAL" : summary.tenantViewMissing ? "WARN" : "OK"}
            />
          </div>
          <div className="text-xs text-gray-600 mt-1">
            {summary.tenantViewMissing ? "Guardrail view missing" : `Found: ${summary.tenantForbidden}`}
          </div>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium">Migrations</div>
            <StatusBadge status="OK" />
          </div>
          <div className="text-xs text-gray-600 mt-1">
            Platform: <span className="font-medium">{data.versions.platform_db.alembic_version ?? "?"}</span>
          </div>
          <div className="text-xs text-gray-600">
            Tenant: <span className="font-medium">{data.versions.tenant_db.alembic_version ?? "?"}</span>
          </div>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium">Overall status</div>
            <StatusBadge status={summary.hasCritical ? "CRITICAL" : "OK"} />
          </div>
          <div className="text-xs text-gray-600 mt-1">Signals: {data.signals.length}</div>
        </Card>
      </div>

      <section className="space-y-3">
        <h2 className="text-base font-semibold">Signals</h2>
        <div className="space-y-3">
          {data.signals.map((s, idx) => (
            <div key={idx} className="border border-gray-200 rounded-lg bg-white p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium">{s.title}</div>
                <span
                  className={
                    "text-xs px-2 py-1 rounded border " +
                    (severityColor(s.severity) === "red"
                      ? "bg-red-50 text-red-700 border-red-200"
                      : severityColor(s.severity) === "yellow"
                        ? "bg-amber-50 text-amber-700 border-amber-200"
                        : "bg-gray-50 text-gray-700 border-gray-200")
                  }
                >
                  {s.severity}
                </span>
              </div>
              <div className="text-sm text-gray-700 mt-2 whitespace-pre-wrap">{s.what_it_means}</div>
              <div className="text-xs text-gray-600 mt-2">
                <div className="font-medium text-gray-700">Why we care</div>
                <div className="whitespace-pre-wrap">{s.why_we_care}</div>
              </div>
              <div className="text-xs text-gray-600 mt-2">
                <div className="font-medium text-gray-700">How to fix</div>
                <div className="whitespace-pre-wrap">{s.how_to_fix}</div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

