import { createContext, ReactNode, useContext, useEffect, useState, useCallback, useRef } from "react";
import { useLocation } from "react-router-dom";
import { checkSession, clearAuthStorage, logoutAndClearTraces, SessionData } from "../utils/sessionCheck";
import { refreshSession } from "../api";
import { getTenantSlugFromHost } from "../tenant";
import { forceWorkspaceRelogin, shouldForceReloginFrom403Body } from "../utils/forceWorkspaceRelogin";

type AuthContextValue = {
  session: SessionData | null;
  isValidating: boolean;
  isValid: boolean;
  isAuthenticated: boolean; // Alias for isValid
  loading: boolean; // Alias for isValidating
  /** True once initial bootstrap (checkSession/refresh) has completed. Blocks protected fetches until then. */
  authReady: boolean;
  /** True during logout flow; protected fetches should not run. */
  isLoggingOut: boolean;
  error: string | null;
  errorStatus: number | null;
  validateSession: () => Promise<void>;
  clearSession: () => void;
  /** Full logout: clears cookies, state, then redirects. Use instead of clearSession for user-initiated logout. */
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue>({
  session: null,
  isValidating: true,
  isValid: false,
  isAuthenticated: false,
  loading: true,
  authReady: false,
  isLoggingOut: false,
  error: null,
  errorStatus: null,
  validateSession: async () => {},
  clearSession: () => {},
  logout: async () => {},
});

/** Skip GET /auth/me on /login briefly after user-initiated logout (API may be restarting; client state already cleared). */
const LOGIN_SHELL_SKIP_VALIDATE_MS = 10_000;

function isLoginShellPath(pathname: string): boolean {
  return pathname === "/login" || pathname.startsWith("/login/");
}

/** Tenant app shells aligned with App.tsx isAppRoute — SPA moves between these need not re-run checkSession. */
function isAppRoutePath(pathname: string): boolean {
  return (
    /^\/payroll\//.test(pathname) ||
    /^\/dashboard/.test(pathname) ||
    /^\/dispatch/.test(pathname) ||
    /^\/inbox/.test(pathname) ||
    /^\/fleet/.test(pathname) ||
    /^\/loads/.test(pathname) ||
    /^\/driver-onboarding/.test(pathname) ||
    /^\/operations/.test(pathname) ||
    /^\/admin/.test(pathname)
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const prevPathnameRef = useRef<string | null>(null);
  const skipLoginShellValidateUntilRef = useRef<number>(0);
  /** Increment on user logout so in-flight validateSession exits after await without clearAuthStorage/extra POST or stale success. */
  const authValidationGenerationRef = useRef(0);
  const [session, setSession] = useState<SessionData | null>(null);
  const [isValidating, setIsValidating] = useState(true);
  const [isValid, setIsValid] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [idleTimeoutMs] = useState(() => {
    const fromStorage = typeof window !== "undefined" ? window.localStorage.getItem("idle_timeout_minutes") : null;
    const fromEnv = (import.meta as any)?.env?.VITE_IDLE_TIMEOUT_MINUTES;
    const minutes = Number(fromStorage || fromEnv || 15);
    return Number.isFinite(minutes) && minutes > 0 ? minutes * 60 * 1000 : 15 * 60 * 1000;
  });

  const validateSession = useCallback(async (): Promise<void> => {
    const tenantSlug = getTenantSlugFromHost();
    const pathname = typeof window !== "undefined" ? window.location.pathname : "";
    const allowMainDomainSession =
      pathname.startsWith("/create-workspace") ||
      pathname.startsWith("/create-workspace/") ||
      pathname.startsWith("/add-workspace") ||
      pathname.startsWith("/add-workspace/") ||
      pathname.startsWith("/signup");

    if (!tenantSlug && !allowMainDomainSession) {
      setSession(null);
      setIsValid(false);
      setIsValidating(false);
      setAuthReady(true);
      setError(null);
      setErrorStatus(null);
      return;
    }

    const genAtStart = authValidationGenerationRef.current;

    setIsValidating(true);
    setError(null);
    setErrorStatus(null);

    let result = await checkSession();
    if (authValidationGenerationRef.current !== genAtStart) return;

    // On 401, try refresh once before giving up
    if (!result.valid && result.status === 401) {
      const refreshed = await refreshSession();
      if (authValidationGenerationRef.current !== genAtStart) return;
      if (refreshed) {
        result = await checkSession();
        if (authValidationGenerationRef.current !== genAtStart) return;
      }
    }

    if (authValidationGenerationRef.current !== genAtStart) return;

    if (result.valid) {
      setSession(result.data);
      setIsValid(true);
      setError(null);
      setErrorStatus(null);
    } else {
      setSession(null);
      setIsValid(false);
      setError(result.error);
      setErrorStatus(result.status);
      if (result.status === 403 && shouldForceReloginFrom403Body(result.error || "")) {
        clearAuthStorage();
        forceWorkspaceRelogin();
        setIsValidating(false);
        setAuthReady(true);
        return;
      }
      if (result.status === 401 || result.status === 403) {
        clearAuthStorage();
      }
    }

    setIsValidating(false);
    setAuthReady(true);
  }, []);

  const clearSession = useCallback(() => {
    setSession(null);
    setIsValid(false);
    setError(null);
    setErrorStatus(null);
    clearAuthStorage();
  }, []);

  const logout = useCallback(async () => {
    authValidationGenerationRef.current += 1;
    setIsLoggingOut(true);
    try {
      await logoutAndClearTraces();
    } finally {
      skipLoginShellValidateUntilRef.current = Date.now() + LOGIN_SHELL_SKIP_VALIDATE_MS;
      setSession(null);
      setIsValid(false);
      setError(null);
      setErrorStatus(null);
      clearAuthStorage({ notifyServer: false });
      setIsValidating(false);
      setAuthReady(true);
      setIsLoggingOut(false);
    }
  }, []);

  // Validate session on mount (app boot) and when route changes (e.g. /create-workspace on main domain).
  // deps: pathname + validateSession only — do not add isValid/authReady here or checkSession re-runs on the same URL.
  useEffect(() => {
    try {
      const tenantSlug = getTenantSlugFromHost();
      const pathname = location.pathname;

      if (!tenantSlug) {
        prevPathnameRef.current = pathname;
        if (
          pathname.startsWith("/create-workspace") ||
          pathname.startsWith("/add-workspace") ||
          pathname.startsWith("/signup")
        ) {
          validateSession();
          return;
        }
        setSession(null);
        setIsValid(false);
        setIsValidating(false);
        setAuthReady(true);
        setError(null);
        return;
      }

      if (pathname === "/onboarding" || pathname.startsWith("/onboarding/")) {
        prevPathnameRef.current = pathname;
        setSession(null);
        setIsValid(false);
        setIsValidating(false);
        setAuthReady(true);
        setError(null);
        setErrorStatus(null);
        return;
      }

      if (tenantSlug && isLoginShellPath(pathname) && Date.now() < skipLoginShellValidateUntilRef.current) {
        prevPathnameRef.current = pathname;
        setSession(null);
        setIsValid(false);
        setIsValidating(false);
        setAuthReady(true);
        setError(null);
        setErrorStatus(null);
        return;
      }

      const prev = prevPathnameRef.current;
      prevPathnameRef.current = pathname;

      const skipTenantCheckSession =
        authReady &&
        isValid &&
        !isLoggingOut &&
        prev !== null &&
        prev !== pathname &&
        isAppRoutePath(pathname) &&
        (isAppRoutePath(prev) ||
          prev === "/" ||
          prev === "/login" ||
          prev.startsWith("/login/"));

      if (skipTenantCheckSession) {
        return;
      }

      validateSession();
    } catch (err) {
      setSession(null);
      setIsValid(false);
      setIsValidating(false);
      setAuthReady(true);
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }, [validateSession, location.pathname]);

  // Idle logout (client-side). Keeps session until user is inactive.
  useEffect(() => {
    if (!isValid) return;
    let timeoutId: number | undefined;

    const reset = () => {
      if (timeoutId) window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(() => {
        clearSession();
        window.location.assign("/login");
      }, idleTimeoutMs);
    };

    const events: Array<keyof WindowEventMap> = [
      "mousemove",
      "mousedown",
      "keydown",
      "touchstart",
      "scroll",
    ];

    events.forEach((evt) => window.addEventListener(evt, reset, { passive: true }));
    reset();

    return () => {
      if (timeoutId) window.clearTimeout(timeoutId);
      events.forEach((evt) => window.removeEventListener(evt, reset));
    };
  }, [isValid, idleTimeoutMs, clearSession]);

  return (
    <AuthContext.Provider
      value={{
        session,
        isValidating,
        isValid,
        isAuthenticated: isValid,
        loading: isValidating,
        authReady,
        isLoggingOut,
        error,
        errorStatus,
        validateSession,
        clearSession,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
