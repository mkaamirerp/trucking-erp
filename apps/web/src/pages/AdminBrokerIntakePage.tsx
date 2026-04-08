import { useCallback, useEffect, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import { getBrokerIntakeSettings, patchBrokerIntakeSettings } from "@/api";

export default function AdminBrokerIntakePage() {
  const [autoCreate, setAutoCreate] = useState(true);
  const [serverValue, setServerValue] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    const data = await getBrokerIntakeSettings();
    setServerValue(Boolean(data.broker_auto_create_from_global));
    setAutoCreate(Boolean(data.broker_auto_create_from_global));
  }, []);

  useEffect(() => {
    setLoading(true);
    refresh()
      .catch((e) => setError(e?.message || "Failed to load broker intake settings"))
      .finally(() => setLoading(false));
  }, [refresh]);

  const onSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await patchBrokerIntakeSettings({ broker_auto_create_from_global: autoCreate });
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not save settings");
    } finally {
      setSaving(false);
    }
  };

  const dirty = serverValue !== null && autoCreate !== serverValue;

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Booking broker intake</h1>
        <p className="text-sm text-gray-600 mt-1">
          Control whether approved platform broker reference can automatically create a matching freight broker
          in your workspace when email intake matches on known sender, domain, or alias (not MC/DOT-only matches).
        </p>
      </div>

      <Card title="Auto-create from global reference">
        {loading && <p className="text-sm text-gray-500">Loading…</p>}
        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
        {!loading && (
          <div className="space-y-4">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                checked={autoCreate}
                onChange={(e) => setAutoCreate(e.target.checked)}
                disabled={saving}
              />
              <span className="text-sm text-gray-700">
                Allow automatic workspace broker rows from approved global reference when intake matches on header
                identity (A–C). When off, those matches stay in review until you create or link a broker manually.
              </span>
            </label>
            {serverValue !== null && (
              <p className="text-xs text-gray-500">
                Current server value:{" "}
                <span className="font-mono">{serverValue ? "enabled" : "disabled"}</span>
              </p>
            )}
            <Button type="button" onClick={onSave} disabled={saving || !dirty}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
