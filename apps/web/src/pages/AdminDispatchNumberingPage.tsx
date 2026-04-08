import { useCallback, useEffect, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import { getDispatchNumbering, putDispatchNumbering } from "@/api";

export default function AdminDispatchNumberingPage() {
  const [prefix, setPrefix] = useState("");
  const [locked, setLocked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serverPrefix, setServerPrefix] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    const data = await getDispatchNumbering();
    setServerPrefix(data.trip_number_prefix ?? null);
    setLocked(Boolean(data.prefix_locked));
    setPrefix((data.trip_number_prefix ?? "").trim());
  }, []);

  useEffect(() => {
    setLoading(true);
    refresh()
      .catch((e) => setError(e?.message || "Failed to load dispatch numbering"))
      .finally(() => setLoading(false));
  }, [refresh]);

  const onSave = async () => {
    const trimmed = prefix.trim();
    if (!trimmed) {
      setError("Enter a non-empty trip number prefix.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await putDispatchNumbering({ trip_number_prefix: trimmed });
      await refresh();
    } catch (e: any) {
      setError(e?.message || "Could not save prefix");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Dispatch trip numbering</h1>
        <p className="text-sm text-gray-600 mt-1">
          Set the fixed prefix for dispatch trip numbers (for example <span className="font-mono text-gray-800">T-</span>
          ). After the first dispatch mints a trip number, this prefix is locked for the tenant.
        </p>
      </div>

      <Card title="Trip number prefix">
        {loading && <p className="text-sm text-gray-500">Loading…</p>}
        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
        {!loading && (
          <div className="space-y-4">
            <div>
              <label htmlFor="trip-prefix" className="block text-sm font-medium text-gray-700">
                Prefix
              </label>
              <input
                id="trip-prefix"
                type="text"
                value={prefix}
                onChange={(e) => setPrefix(e.target.value)}
                disabled={locked || saving}
                maxLength={32}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500 disabled:bg-gray-100"
              />
              {locked ? (
                <p className="mt-2 text-xs text-amber-700">
                  Prefix is locked. Trip numbers already issued for this workspace; the prefix cannot be changed here.
                </p>
              ) : (
                <p className="mt-2 text-xs text-gray-500">
                  Save once you are sure — dispatch will lock this value after the first trip number is minted.
                </p>
              )}
            </div>
            {serverPrefix != null && (
              <p className="text-xs text-gray-600">
                Current value on server: <span className="font-mono">{serverPrefix || "(empty)"}</span>
              </p>
            )}
            <Button type="button" onClick={onSave} disabled={saving || locked}>
              {saving ? "Saving…" : locked ? "Locked" : "Save prefix"}
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
