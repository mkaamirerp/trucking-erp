import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  createFuelProviderConnection,
  listFuelProviderConnections,
  listFuelProviders,
  syncFuelProviderConnection,
  testFuelProviderConnection,
  updateFuelProviderConnection,
  type FuelConnectionFieldDef,
  type FuelConnectionMethodDef,
  type FuelProviderCatalog,
  type FuelProviderConnection,
} from "../api";
import { ADMIN, OPS } from "../routes";

const INPUT_CLS =
  "mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500 disabled:bg-gray-100";

type Props = {
  entryPoint: "admin" | "fuel";
};

function methodDef(provider: FuelProviderCatalog | undefined, method: string): FuelConnectionMethodDef | undefined {
  return provider?.connection_methods.find((m) => m.connection_method === method);
}

export default function FuelProviderConnectionsPage({ entryPoint }: Props) {
  const [catalog, setCatalog] = useState<FuelProviderCatalog[]>([]);
  const [rows, setRows] = useState<FuelProviderConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [providerCode, setProviderCode] = useState("");
  const [connectionMethod, setConnectionMethod] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});

  const selectedProvider = useMemo(
    () => catalog.find((p) => p.provider_code === providerCode),
    [catalog, providerCode],
  );
  const selectedMethod = methodDef(selectedProvider, connectionMethod);
  const selectableMethods = useMemo(
    () => (selectedProvider?.connection_methods ?? []).filter((m) => m.selectable),
    [selectedProvider],
  );
  const unverifiedMethods = selectedProvider?.unverified_connection_methods ?? [];
  const fields: FuelConnectionFieldDef[] = selectedMethod?.selectable ? selectedMethod.fields : [];
  const canConfigure = selectableMethods.length > 0;

  const otherEntry =
    entryPoint === "admin"
      ? { href: OPS.FUEL_PROVIDERS, label: "Fuel → Providers" }
      : { href: ADMIN.INTEGRATIONS_FUEL, label: "Admin → Integrations → Fuel" };

  const refresh = useCallback(async () => {
    const [providers, connections] = await Promise.all([
      listFuelProviders(),
      listFuelProviderConnections(),
    ]);
    setCatalog(providers);
    setRows(connections);
    if (!providerCode && providers.length) {
      const firstConfigurable = providers.find((p) => p.supported_connection_methods.length > 0) ?? providers[0];
      setProviderCode(firstConfigurable.provider_code);
      setConnectionMethod(firstConfigurable.default_connection_method ?? "");
    }
  }, [providerCode]);

  useEffect(() => {
    setLoading(true);
    refresh()
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load Fuel providers"))
      .finally(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    if (!selectedProvider) return;
    if (!selectedProvider.supported_connection_methods.includes(connectionMethod)) {
      setConnectionMethod(selectedProvider.default_connection_method ?? "");
      setFieldValues({});
    }
  }, [selectedProvider, connectionMethod]);

  const onProviderChange = (code: string) => {
    const next = catalog.find((p) => p.provider_code === code);
    setProviderCode(code);
    setConnectionMethod(next?.default_connection_method ?? "");
    setFieldValues({});
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!providerCode || !connectionMethod || !canConfigure) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      await createFuelProviderConnection({
        provider_code: providerCode,
        connection_method: connectionMethod,
        enabled,
        fields: fieldValues,
      });
      setFieldValues({});
      setEnabled(false);
      setNotice("Provider connection saved. Secrets are stored server-side and are never returned.");
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not save provider connection");
    } finally {
      setSaving(false);
    }
  };

  const onTest = async (id: number) => {
    setBusyId(id);
    setError(null);
    setNotice(null);
    try {
      const out = await testFuelProviderConnection(id);
      const failed = out.success !== true || out.attempted !== true;
      setNotice(
        failed
          ? `Unsuccessful: connection method not implemented. No provider connection was attempted. (${out.result})`
          : `${out.result}: ${out.message}`,
      );
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setBusyId(null);
    }
  };

  const onSync = async (id: number) => {
    setBusyId(id);
    setError(null);
    setNotice(null);
    try {
      const out = await syncFuelProviderConnection(id);
      const failed = out.success !== true || out.attempted !== true;
      setNotice(
        failed
          ? `Unsuccessful: connection method not implemented. No provider connection was attempted. (${out.result})`
          : `${out.result}: ${out.message}`,
      );
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setBusyId(null);
    }
  };

  const onToggleEnabled = async (row: FuelProviderConnection) => {
    setBusyId(row.id);
    setError(null);
    try {
      await updateFuelProviderConnection(row.id, { enabled: !row.enabled });
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not update connection");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Fuel / card providers</h1>
        <p className="text-sm text-gray-600 mt-1">
          Tenant provider connections are stored once and used from both{" "}
          <a className="text-blue-700 underline" href={otherEntry.href}>
            {otherEntry.label}
          </a>{" "}
          and this page. The backend catalog defines vendors, connection methods, and fields. Only
          methods with captured Fuel-design evidence are configurable. Live API/SFTP adapters are
          not implemented; Test and Sync never report a successful provider connection.
        </p>
      </div>

      {loading && <p className="text-sm text-gray-500">Loading…</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {notice && <p className="text-sm text-amber-800">{notice}</p>}

      {!loading && (
        <form onSubmit={onSubmit} className="rounded-xl border border-gray-200 bg-white p-4 space-y-4">
          <h2 className="text-sm font-semibold text-gray-900">Add provider connection</h2>
          <div>
            <label className="block text-sm font-medium text-gray-700" htmlFor="fuel-provider">
              Fuel provider
            </label>
            <select
              id="fuel-provider"
              className={INPUT_CLS}
              value={providerCode}
              onChange={(e) => onProviderChange(e.target.value)}
              disabled={saving}
            >
              {catalog.map((p) => (
                <option key={p.provider_code} value={p.provider_code}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </div>
          {selectedProvider && (
            <p className="text-xs text-gray-500">{selectedProvider.instructions}</p>
          )}
          {unverifiedMethods.length > 0 && (
            <p className="text-xs text-amber-800">
              Unverified / not configurable until captured evidence exists:{" "}
              {unverifiedMethods.join(", ")}
            </p>
          )}
          {!canConfigure && (
            <p className="text-sm text-amber-800">
              No verified connection method. This provider cannot be configured until Fuel
              design/research captures a real contract, sample, or credentials.
            </p>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700" htmlFor="fuel-method">
              Connection method
            </label>
            <select
              id="fuel-method"
              className={INPUT_CLS}
              value={connectionMethod}
              onChange={(e) => {
                setConnectionMethod(e.target.value);
                setFieldValues({});
              }}
              disabled={saving || !canConfigure}
            >
              {selectableMethods.map((m) => (
                <option key={m.connection_method} value={m.connection_method}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          {fields.map((field) => (
            <div key={field.key}>
              <label className="block text-sm font-medium text-gray-700" htmlFor={`fuel-field-${field.key}`}>
                {field.label}
                {field.required ? " *" : ""}
              </label>
              <input
                id={`fuel-field-${field.key}`}
                type={field.secret ? "password" : "text"}
                autoComplete={field.secret ? "new-password" : "off"}
                className={INPUT_CLS}
                value={fieldValues[field.key] ?? ""}
                onChange={(e) => setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                disabled={saving}
              />
            </div>
          ))}
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              disabled={saving}
            />
            Enable this connection
          </label>
          <button
            type="submit"
            disabled={saving || !canConfigure}
            className="rounded-md bg-blue-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save connection"}
          </button>
        </form>
      )}

      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        <h2 className="text-sm font-semibold text-gray-900 px-4 py-3 border-b border-gray-100">
          Saved connections
        </h2>
        {rows.length === 0 && !loading ? (
          <p className="px-4 py-6 text-sm text-gray-500">No Fuel provider connections yet.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {rows.map((row) => (
              <li key={row.id} className="px-4 py-3 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {row.display_name || row.provider_code}{" "}
                      <span className="font-normal text-gray-500">
                        {row.provider_code} · {row.connection_method}
                        {row.account_reference ? ` · ${row.account_reference}` : ""}
                      </span>
                    </p>
                    <p className="text-xs text-gray-500">
                      {row.enabled ? "Enabled" : "Disabled"}
                      {Object.entries(row.secrets).map(([key, state]) => (
                        <span key={key}>
                          {" "}
                          · {key}: {state.configured ? state.masked_display || "Configured: Yes" : "not configured"}
                        </span>
                      ))}
                    </p>
                    {row.last_test_status && (
                      <p className="text-xs text-amber-800">
                        Last test:{" "}
                        {row.last_test_status === "connection_method_not_implemented"
                          ? "unsuccessful — connection method not implemented; no provider connection attempted"
                          : row.last_test_status}
                      </p>
                    )}
                    {row.last_sync_status === "connection_method_not_implemented" && (
                      <p className="text-xs text-amber-800">
                        Last sync: unsuccessful — connection method not implemented; no provider
                        connection attempted
                      </p>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      disabled={busyId === row.id}
                      onClick={() => onToggleEnabled(row)}
                    >
                      {row.enabled ? "Disable" : "Enable"}
                    </button>
                    <button
                      type="button"
                      className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      disabled={busyId === row.id}
                      onClick={() => onTest(row.id)}
                    >
                      Test connection
                    </button>
                    <button
                      type="button"
                      className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      disabled={busyId === row.id}
                      onClick={() => onSync(row.id)}
                    >
                      Sync now
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
