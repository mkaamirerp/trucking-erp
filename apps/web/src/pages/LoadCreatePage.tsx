import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createLoad } from "@/api";
import { OPS } from "@/routes";

/**
 * Minimal create-load step: allocates a draft load_number server-side pattern,
 * then redirects to the load detail record for full entry (same outcome as Dispatch "New Load").
 */
export default function LoadCreatePage() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadNumber = `L-${Date.now().toString(36).toUpperCase()}`;
    createLoad({ load_number: loadNumber, status: "unassigned" })
      .then((load) => {
        if (!cancelled) navigate(OPS.LOAD_DETAIL(load.id), { replace: true });
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not create load");
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  if (error) {
    return (
      <div className="p-6 text-sm text-red-400">
        {error}
        <button
          type="button"
          className="ml-3 text-sky-400 underline"
          onClick={() => navigate(OPS.INTAKE, { replace: true })}
        >
          Back to intake
        </button>
      </div>
    );
  }

  return (
    <div className="p-6 text-sm text-[#94a3b8]">
      Creating load…
    </div>
  );
}
