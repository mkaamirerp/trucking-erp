import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useMe } from "../hooks/useMe";

const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

// Keep in sync with VALID_THEMES in app/routers/me.py
export type Theme = "dark" | "dark-blue" | "dark-navy" | "light-slate";

type ThemeContextValue = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
};

const ThemeContext = createContext<ThemeContextValue>({
  theme: "dark",
  setTheme: () => {},
});

function getInitialTheme(): Theme {
  try {
    const stored = localStorage.getItem("trk-theme");
    if (stored === "dark" || stored === "dark-blue" || stored === "dark-navy" || stored === "light-slate") {
      return stored;
    }
  } catch {
    // localStorage unavailable (e.g. private mode with strict settings)
  }
  return "dark";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { me } = useMe();
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);

  // Apply to <html data-theme="…"> and persist to localStorage on every change.
  // This runs synchronously after paint so there is no flash between
  // the localStorage-seeded initial value and the committed state.
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("trk-theme", theme);
    } catch {
      // ignore write errors
    }
  }, [theme]);

  // Once the server session loads, treat its value as authoritative.
  // Handles the case where the user changed their theme on another device.
  useEffect(() => {
    if (me?.theme) {
      setThemeState(me.theme as Theme);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.theme]);

  function setTheme(newTheme: Theme): void {
    // Optimistic: update DOM immediately, no reload required.
    setThemeState(newTheme);
    // Persist to server in the background — failure is silent because the
    // change is already in localStorage and will survive a page refresh.
    fetch(`${API_BASE}/me/preferences`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme: newTheme }),
    }).catch(() => {
      // intentionally swallowed
    });
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
