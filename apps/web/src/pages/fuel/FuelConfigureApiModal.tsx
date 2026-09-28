import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createFuelProviderConnection,
  listFuelProviderConnections,
  listFuelProviders,
  testFuelProviderConnection,
  type FuelConnectionFieldDef,
  type FuelConnectionMethodDef,
  type FuelProviderCatalog,
  type FuelProviderConnection,
} from "../../api";

type Props = {
  open: boolean;
  onClose: () => void;
  initialProviderCode: string;
};

function methodDef(
  provider: FuelProviderCatalog | undefined,
  method: string,
): FuelConnectionMethodDef | undefined {
  return provider?.connection_methods.find((m) => m.connection_method === method);
}

export default function FuelConfigureApiModal({ open, onClose, initialProviderCode }: Props) {
  const [catalog, setCatalog] = useState<FuelProviderCatalog[]>([]);
  const [connections, setConnections] = useState<FuelProviderConnection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const [providerCode, setProviderCode] = useState(initialProviderCode);
  const [connectionMethod, setConnectionMethod] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [autoSync, setAutoSync] = useState(false);
  const [syncFrequency, setSyncFrequency] = useState<string>("manual");
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open) return;
    setProviderCode(initialProviderCode);
    setError(null);
    setNotice(null);
    setLoading(true);
    Promise.all([listFuelProviders(), listFuelProviderConnections()])
      .then(([providers, rows]) => {
        setCatalog(providers);
        setConnections(rows);
        const p = providers.find((x) => x.provider_code === initialProviderCode) ?? providers[0];
        if (p) {
          setProviderCode(p.provider_code);
          setConnectionMethod(p.default_connection_method ?? p.supported_connection_methods[0] ?? "");
        }
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load providers"))
      .finally(() => setLoading(false));
  }, [open, initialProviderCode]);

  const selectedProvider = useMemo(
    () => catalog.find((p) => p.provider_code === providerCode),
    [catalog, providerCode],
  );
  const selectedMethod = methodDef(selectedProvider, connectionMethod);
  const selectableMethods = useMemo(
    () => (selectedProvider?.connection_methods ?? []).filter((m) => m.selectable),
    [selectedProvider],
  );
  const fields: FuelConnectionFieldDef[] = selectedMethod?.selectable ? selectedMethod.fields : [];
  const apiAvailable = selectableMethods.some((m) => m.live_adapter_implemented || m.selectable);
  const existing = connections.find((c) => c.provider_code === providerCode);

  const syncOptions = useMemo(() => {
    if (!selectedMethod?.scheduling_capability) return [{ value: "manual", label: "Manual only" }];
    return [
      { value: "manual", label: "Manual" },
      { value: "daily", label: "Daily" },
      { value: "weekly", label: "Weekly" },
    ];
  }, [selectedMethod]);

  if (!open) return null;

  async function onSave(e: FormEvent) {
    e.preventDefault();
    if (!providerCode || !connectionMethod || !selectedMethod?.selectable) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      await createFuelProviderConnection({
        provider_code: providerCode,
        connection_method: connectionMethod,
        enabled,
        auto_sync_enabled: autoSync,
        sync_frequency: syncFrequency === "manual" ? null : syncFrequency,
        fields: fieldValues,
      });
      setNotice("Configuration saved. Credentials are stored server-side.");
      const rows = await listFuelProviderConnections();
      setConnections(rows);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not save configuration");
    } finally {
      setSaving(false);
    }
  }

  async function onTest() {
    if (!existing) {
      setError("Save a connection first, then test.");
      return;
    }
    setTesting(true);
    setError(null);
    try {
      const result = await testFuelProviderConnection(existing.id);
      setNotice(result.message || (result.success ? "Connection test succeeded." : "Connection test failed."));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-[var(--trk-border)] bg-[var(--trk-surface)] p-5 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-[var(--trk-text)]">Configure vendor API</h2>
            <p className="mt-1 text-sm text-[var(--trk-text-muted)]">
              Connect a fuel card provider for automatic transaction imports.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-[var(--trk-border)] px-2 py-1 text-sm text-[var(--trk-text-muted)]"
          >
            Close
          </button>
        </div>

        {loading ? <p className="mt-4 text-sm text-[var(--trk-text-muted)]">Loading…</p> : null}
        {error ? (
          <p className="mt-4 text-sm text-[var(--trk-danger)]" role="alert">{error}</p>
        ) : null}
        {notice ? (
          <p className="mt-4 text-sm text-[var(--trk-success)]" role="status">{notice}</p>
        ) : null}

        <form className="mt-4 space-y-4" onSubmit={onSave}>
          <label className="block text-sm">
            <span className="font-medium text-[var(--trk-text)]">Vendor</span>
            <select
              className="mt-1 block w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-3 py-2 text-sm"
              value={providerCode}
              onChange={(e) => {
                const code = e.target.value;
                const p = catalog.find((x) => x.provider_code === code);
                setProviderCode(code);
                setConnectionMethod(p?.default_connection_method ?? "");
                setFieldValues({});
              }}
            >
              {catalog.map((p) => (
                <option key={p.provider_code} value={p.provider_code}>{p.display_name}</option>
              ))}
            </select>
          </label>

          {!apiAvailable ? (
            <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-[var(--trk-text)]">
              API is not available or not verified for this provider. Use Upload file for PDF/CSV imports.
            </p>
          ) : (
            <>
              <label className="block text-sm">
                <span className="font-medium text-[var(--trk-text)]">Connection method</span>
                <select
                  className="mt-1 block w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-3 py-2 text-sm"
                  value={connectionMethod}
                  onChange={(e) => {
                    setConnectionMethod(e.target.value);
                    setFieldValues({});
                  }}
                >
                  {selectableMethods.map((m) => (
                    <option key={m.connection_method} value={m.connection_method}>{m.label}</option>
                  ))}
                </select>
              </label>

              {fields.map((field) => (
                <label key={field.key} className="block text-sm">
                  <span className="font-medium text-[var(--trk-text)]">{field.label}</span>
                  <input
                    type={field.secret ? "password" : "text"}
                    required={field.required}
                    className="mt-1 block w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-3 py-2 text-sm"
                    value={fieldValues[field.key] ?? ""}
                    onChange={(e) => setFieldValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  />
                </label>
              ))}

              {selectedMethod?.scheduling_capability ? (
                <label className="block text-sm">
                  <span className="font-medium text-[var(--trk-text)]">Sync frequency</span>
                  <select
                    className="mt-1 block w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-3 py-2 text-sm"
                    value={syncFrequency}
                    onChange={(e) => setSyncFrequency(e.target.value)}
                  >
                    {syncOptions.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </label>
              ) : null}

              <label className="flex items-center gap-2 text-sm text-[var(--trk-text)]">
                <input
                  type="checkbox"
                  checked={autoSync}
                  onChange={(e) => setAutoSync(e.target.checked)}
                />
                Automatically process when received (still subject to duplicate and review rules)
              </label>

              <label className="flex items-center gap-2 text-sm text-[var(--trk-text)]">
                <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
                Connection enabled
              </label>
            </>
          )}

          <div className="flex flex-wrap justify-end gap-2 border-t border-[var(--trk-border)] pt-4">
            <button
              type="button"
              disabled={!existing || testing}
              onClick={() => void onTest()}
              className="rounded-md border border-[var(--trk-border-strong)] px-4 py-2 text-sm disabled:opacity-50"
            >
              {testing ? "Testing…" : "Test connection"}
            </button>
            <button
              type="submit"
              disabled={!apiAvailable || saving || !selectedMethod?.selectable}
              className="rounded-md bg-[var(--trk-btn-primary)] px-4 py-2 text-sm font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save configuration"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
