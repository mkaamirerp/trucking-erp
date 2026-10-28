import type { LoadReparseChange } from "@/api";

function showValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

type Props = {
  changes: LoadReparseChange[];
  busy: boolean;
  onChangeField: (change: LoadReparseChange) => void;
  onClose: () => void;
};

export function ReparseChangesDialog({ changes, busy, onChangeField, onClose }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
      <div className="max-h-[80vh] w-full max-w-2xl overflow-auto rounded-lg bg-white p-4 shadow-lg">
        <div className="mb-3 flex items-start justify-between gap-3">
          <h2 className="text-base font-semibold text-gray-900">
            {changes.length === 0
              ? "No changes found"
              : `Revised rate confirmation — ${changes.length} change${changes.length === 1 ? "" : "s"}`}
          </h2>
          <button type="button" className="text-sm text-gray-600 underline" onClick={onClose} disabled={busy}>
            Close
          </button>
        </div>
        <p className="mb-3 text-sm text-gray-600">
          The load form is unchanged until you click Change. You can still edit any field. Nothing is stored until Save.
        </p>
        {changes.length > 0 ? (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b text-xs uppercase text-gray-500">
                <th className="py-2 pr-2">Field</th>
                <th className="py-2 pr-2">On the load</th>
                <th className="py-2 pr-2">Revised PDF</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {changes.map((change) => (
                <tr key={change.field} className="border-b border-gray-100">
                  <td className="py-2 pr-2 font-medium">{change.label}</td>
                  <td className="py-2 pr-2">{showValue(change.current_value)}</td>
                  <td className="py-2 pr-2">{showValue(change.revised_value)}</td>
                  <td className="py-2 text-right">
                    {change.editable === true ? (
                      <button
                        type="button"
                        className="rounded border border-gray-300 px-2 py-1 text-xs font-medium"
                        disabled={busy}
                        onClick={() => onChangeField(change)}
                      >
                        Change
                      </button>
                    ) : (
                      <span className="text-xs text-gray-500">For review</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-gray-700">The revised PDF matches this load. Save if you still want to keep that PDF.</p>
        )}
      </div>
    </div>
  );
}
