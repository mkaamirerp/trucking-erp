import { useCallback, useEffect, useState } from "react";

export type WorkspaceLayoutMode = "table" | "board";

const STORAGE_PREFIX = "truckerp_workspace_layout";

function storageKey(workspaceId: string, userId: number | string | null): string {
  return `${STORAGE_PREFIX}_${workspaceId}_${userId ?? "anon"}`;
}

export function useWorkspaceLayout(
  workspaceId: string,
  userId: number | string | null,
  defaultMode: WorkspaceLayoutMode = "table"
): [WorkspaceLayoutMode, (mode: WorkspaceLayoutMode) => void] {
  const [mode, setModeState] = useState<WorkspaceLayoutMode>(defaultMode);

  useEffect(() => {
    try {
      const key = storageKey(workspaceId, userId);
      const stored = window.localStorage.getItem(key);
      if (stored === "table" || stored === "board") {
        setModeState(stored);
      }
    } catch {
      /* ignore */
    }
  }, [workspaceId, userId]);

  const setMode = useCallback(
    (next: WorkspaceLayoutMode) => {
      setModeState(next);
      try {
        window.localStorage.setItem(storageKey(workspaceId, userId), next);
      } catch {
        /* ignore */
      }
    },
    [workspaceId, userId]
  );

  return [mode, setMode];
}
