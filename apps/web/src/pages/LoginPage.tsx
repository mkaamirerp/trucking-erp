import React, { useState, useEffect, useCallback, useRef } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import {
  login,
  loginStepUpIssue,
  loginStepUpVerify,
  getTenantStatus,
  LoginRateLimitedError,
  LoginVerificationRequiredError,
  LoginStepUpRequiredError,
} from "../api";
import { authErrorToMessage } from "../utils/authErrorToMessage";
import { loadTurnstileScript } from "../lib/turnstile";
import { getTenantSlugFromHost } from "../tenant";

/** Optional build-time fallback; on workspace hosts the API value from GET /api/v1/public/tenant/{slug} wins when present. */
const VITE_TURNSTILE_SITE_KEY = (import.meta.env.VITE_TURNSTILE_SITE_KEY ?? "").trim();

const SIGN_IN_SECURITY_HINT =
  "If you did not try to sign in, use Forgot password after you regain access, or contact your workspace admin.";

function loginErrorStatus(err: unknown): number {
  if (err instanceof Error && "status" in err && typeof (err as Error & { status?: number }).status === "number") {
    return (err as Error & { status: number }).status;
  }
  return 401;
}

function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const tenantSlug = getTenantSlugFromHost();
  /** Runtime Turnstile site key from GET /api/v1/public/tenant/{slug}; prefer over VITE when non-empty. */
  const [apiTurnstile, setApiTurnstile] = useState<{ loaded: boolean; key: string }>({ loaded: false, key: "" });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [loginChallengeId, setLoginChallengeId] = useState<string | null>(null);
  /** After admin cleared a sign-in block: show plain-language notice on the MFA step. */
  const [stepUpAfterAdminUnlock, setStepUpAfterAdminUnlock] = useState(false);
  /** User preference: remember browser after successful sign-in (optional cookie, set only when allowed). */
  const [trustThisDevice, setTrustThisDevice] = useState(false);
  /** Sign-in rate limit (POST /auth/login 429): seconds until user can retry without refresh. */
  const [loginLockoutSeconds, setLoginLockoutSeconds] = useState(0);

  const turnstileContainerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);
  /** If step-up was entered after a Turnstile-backed login attempt, reuse the same token on the final login. */
  const otpFlowTurnstileRef = useRef<string | null>(null);

  // Show session error when redirected from protected route (e.g. "Your session expired. Please sign in again.")
  useEffect(() => {
    const sessionError = location.state?.sessionError as string | undefined;
    if (sessionError) setError(sessionError);
  }, [location.state]);

  useEffect(() => {
    if (!tenantSlug) {
      setApiTurnstile({ loaded: true, key: "" });
      return;
    }
    let cancelled = false;
    setApiTurnstile({ loaded: false, key: "" });
    getTenantStatus(tenantSlug)
      .then((t) => {
        if (!cancelled) setApiTurnstile({ loaded: true, key: (t.turnstile_site_key ?? "").trim() });
      })
      .catch(() => {
        if (!cancelled) setApiTurnstile({ loaded: true, key: "" });
      });
    return () => {
      cancelled = true;
    };
  }, [tenantSlug]);

  const turnstileSiteKey = (apiTurnstile.key || VITE_TURNSTILE_SITE_KEY || "").trim();

  useEffect(() => {
    if (loginLockoutSeconds <= 0) return;
    const id = window.setTimeout(() => {
      setLoginLockoutSeconds((s) => Math.max(0, s - 1));
    }, 1000);
    return () => window.clearTimeout(id);
  }, [loginLockoutSeconds]);

  const navigateAfterLogin = useCallback(
    (result: { workspace_url?: string }) => {
      const returnTo = (location.state as { from?: string } | null)?.from;
      if (returnTo === "/add-workspace" || returnTo === "/create-workspace") {
        navigate("/add-workspace", { replace: true });
        return;
      }
      if (result.workspace_url) {
        window.location.href = result.workspace_url;
      } else {
        navigate("/dashboard");
      }
    },
    [navigate, location.state]
  );

  const resetStepUpState = useCallback(() => {
    setLoginChallengeId(null);
    setOtpCode("");
    setStepUpAfterAdminUnlock(false);
    otpFlowTurnstileRef.current = null;
  }, []);

  const performLogin = useCallback(
    async (turnstileToken?: string | null) => {
      setLoading(true);
      setError(null);
      try {
        const result = await login({
          email,
          password,
          turnstile_token: turnstileToken ?? undefined,
          // Password-only sign-in: no MFA checkbox; keep convenient trust cookie unless policy adds a checkbox here later.
          trust_this_device: true,
        });
        setLoginLockoutSeconds(0);
        setNeedsVerification(false);
        resetStepUpState();
        navigateAfterLogin(result);
      } catch (err) {
        if (err instanceof LoginRateLimitedError) {
          setLoginLockoutSeconds(err.retryAfterSeconds);
          setError(err.message);
          setNeedsVerification(false);
          resetStepUpState();
          return;
        }
        if (err instanceof LoginStepUpRequiredError) {
          otpFlowTurnstileRef.current = turnstileToken ?? null;
          try {
            await loginStepUpIssue({ login_challenge_id: err.loginChallengeId });
          } catch (issueErr) {
            const st = loginErrorStatus(issueErr);
            const raw = issueErr instanceof Error ? issueErr.message : "Could not send verification code.";
            setError(authErrorToMessage(st, raw));
            return;
          }
          setError(null);
          setNeedsVerification(false);
          setTrustThisDevice(false);
          setStepUpAfterAdminUnlock(err.afterSignInUnlock);
          setLoginChallengeId(err.loginChallengeId);
          return;
        }
        if (err instanceof LoginVerificationRequiredError) {
          let key = turnstileSiteKey;
          if (!key && tenantSlug) {
            try {
              const t = await getTenantStatus(tenantSlug);
              const k = (t.turnstile_site_key ?? "").trim();
              setApiTurnstile({ loaded: true, key: k });
              if (k) key = k;
              else if (VITE_TURNSTILE_SITE_KEY) key = VITE_TURNSTILE_SITE_KEY.trim();
            } catch {
              /* ignore */
            }
          }
          if (!key) {
            setError(
              "For your security we need a quick check before you sign in, but this workspace is not finished being set up for that yet. " +
                "Your administrator should add the Turnstile site key to the server (TURNSTILE_SITE_KEY — the public key, alongside the secret). " +
                "After that, refresh this page and try again.",
            );
            setNeedsVerification(false);
          } else {
            setError(null);
            setNeedsVerification(true);
          }
          return;
        }
        const status = loginErrorStatus(err);
        const raw = err instanceof Error ? err.message : "Invalid email or password";
        setError(authErrorToMessage(status, raw));
        setNeedsVerification(false);
        resetStepUpState();
      } finally {
        setLoading(false);
      }
    },
    [email, password, navigateAfterLogin, resetStepUpState, turnstileSiteKey]
  );

  // Changing credentials ends verification / step-up flows (not while OTP challenge is active — fields are
  // disabled then, but this avoids edge cases where a stale effect run could clear the challenge).
  useEffect(() => {
    if (loginChallengeId) return;
    setNeedsVerification(false);
    resetStepUpState();
  }, [email, password, loginChallengeId, resetStepUpState]);

  useEffect(() => {
    if (!needsVerification || !turnstileSiteKey) return;
    const el = turnstileContainerRef.current;
    if (!el) return;

    let cancelled = false;

    const mount = async () => {
      try {
        await loadTurnstileScript();
      } catch {
        if (!cancelled) {
          setError("Could not load verification. Check your connection and try again.");
        }
        return;
      }
      if (cancelled || !el.isConnected || !window.turnstile) return;
      if (widgetIdRef.current) {
        window.turnstile.remove(widgetIdRef.current);
        widgetIdRef.current = null;
      }
      el.innerHTML = "";
      widgetIdRef.current = window.turnstile.render(el, {
        sitekey: turnstileSiteKey,
        callback: (token: string) => {
          void performLogin(token);
        },
        "error-callback": () => {
          if (!cancelled) {
            setError("Verification could not be shown. Please refresh and try again.");
          }
        },
      });
    };

    void mount();

    return () => {
      cancelled = true;
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
        widgetIdRef.current = null;
      }
      el.innerHTML = "";
    };
  }, [needsVerification, performLogin, turnstileSiteKey]);

  const handleOtpSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginChallengeId || !otpCode.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await loginStepUpVerify({ login_challenge_id: loginChallengeId, otp: otpCode.trim() });
      const result = await login({
        email,
        password,
        login_challenge_id: loginChallengeId,
        turnstile_token: otpFlowTurnstileRef.current ?? undefined,
        trust_this_device: trustThisDevice,
      });
      setLoginLockoutSeconds(0);
      resetStepUpState();
      navigateAfterLogin(result);
    } catch (err) {
      if (err instanceof LoginRateLimitedError) {
        setLoginLockoutSeconds(err.retryAfterSeconds);
        setError(err.message);
        return;
      }
      if (err instanceof LoginVerificationRequiredError) {
        if (!turnstileSiteKey) {
          setError(
            "We still need the sign-in check to finish, but the verification step is not available on this page yet. " +
              "An administrator should set TURNSTILE_SITE_KEY on the server (public site key next to the secret), then refresh.",
          );
        } else {
          setError(null);
          setNeedsVerification(true);
        }
        return;
      }
      if (err instanceof LoginStepUpRequiredError) {
        setError("We still need to verify it’s you. Try signing in again.");
        resetStepUpState();
        return;
      }
      const status = loginErrorStatus(err);
      const raw = err instanceof Error ? err.message : "Invalid email or password";
      setError(authErrorToMessage(status, raw));
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loginChallengeId) {
      await handleOtpSubmit(e);
      return;
    }
    await performLogin(undefined);
  };

  const handleResendStepUp = async () => {
    if (!loginChallengeId) return;
    setLoading(true);
    setError(null);
    try {
      await loginStepUpIssue({ login_challenge_id: loginChallengeId });
    } catch (issueErr) {
      const st = loginErrorStatus(issueErr);
      const raw = issueErr instanceof Error ? issueErr.message : "Could not resend code.";
      setError(authErrorToMessage(st, raw));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="trk-auth">
      <div className="trk-auth-wrap">
        <div className="trk-brand">
          <div className="trk-badge">🚚</div>
          <div>
            <h1>Trucking ERP</h1>
            <p>Secure fleet operations platform</p>
          </div>
        </div>

        <div className="trk-card">
          <h2>Sign in</h2>
          <p className="trk-foot">Access your company workspace</p>

          <form onSubmit={handleSubmit}>
            {(error || loginLockoutSeconds > 0) && (
              <div className="trk-error" role="status">
                {error ? <p>{error}</p> : null}
                {loginLockoutSeconds > 0 ? (
                  <p style={{ marginTop: error ? "0.5rem" : 0, fontWeight: 600 }}>
                    You can try again in{" "}
                    {`${Math.floor(loginLockoutSeconds / 60)}:${String(loginLockoutSeconds % 60).padStart(2, "0")}`}
                  </p>
                ) : null}
              </div>
            )}

            <div className="trk-field">
              <label className="trk-label">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="trk-input"
                placeholder="admin@company.com"
                disabled={Boolean(loginChallengeId) || loginLockoutSeconds > 0}
              />
            </div>

            <div className="trk-field">
              <label className="trk-label">Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="trk-input"
                placeholder="••••••••"
                disabled={Boolean(loginChallengeId) || loginLockoutSeconds > 0}
              />
            </div>

            {loginChallengeId ? (
              <div className="trk-field">
                {stepUpAfterAdminUnlock ? (
                  <div className="trk-callout-info" role="status">
                    <p>
                      This sign-in lock was cleared. For security, enter the verification code we sent to your
                      email.
                    </p>
                  </div>
                ) : (
                  <p className="trk-foot" style={{ marginBottom: "0.75rem" }}>
                    Enter the verification code sent to your email.
                  </p>
                )}
                <label className="trk-label">Verification code</label>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  className="trk-input"
                  placeholder="6-digit code"
                  disabled={loginLockoutSeconds > 0}
                />
                <button type="button" className="trk-link" style={{ marginTop: "0.5rem", background: "none", border: "none", padding: 0, cursor: "pointer" }} onClick={() => void handleResendStepUp()} disabled={loading || loginLockoutSeconds > 0}>
                  Resend code
                </button>

                <label className="trk-check">
                  <input
                    type="checkbox"
                    checked={trustThisDevice}
                    onChange={(e) => setTrustThisDevice(e.target.checked)}
                    disabled={loginLockoutSeconds > 0}
                  />
                  <span>
                    Trust this device
                    <span className="trk-check-hint">Skip the verification code on this device next time.</span>
                  </span>
                </label>
              </div>
            ) : null}

            {needsVerification && turnstileSiteKey && !loginChallengeId ? (
              <div className="trk-field">
                <p className="trk-foot" style={{ marginBottom: "0.75rem" }}>
                  Complete the verification below to continue signing in.
                </p>
                <div ref={turnstileContainerRef} className="trk-turnstile-host" />
                <p className="trk-foot" style={{ marginTop: "0.75rem", fontSize: "0.9rem" }}>
                  {SIGN_IN_SECURITY_HINT}
                </p>
              </div>
            ) : null}

            {loginChallengeId ? (
              <p className="trk-foot" style={{ marginTop: "-0.5rem", marginBottom: "0.5rem", fontSize: "0.9rem" }}>
                {SIGN_IN_SECURITY_HINT}
              </p>
            ) : null}

            <button type="submit" disabled={loading || loginLockoutSeconds > 0} className="trk-primary">
              {loading ? "Please wait..." : loginChallengeId ? "Verify and sign in" : "Sign in"}
            </button>

            <div className="trk-row">
              <Link to="/forgot-password" className="trk-link">
                Forgot password?
              </Link>
              <Link to="/create-workspace" className="trk-link">
                Create a workspace
              </Link>
            </div>
          </form>

          <div className="trk-foot">Tenant-isolated • Secure • Multi-tenant SaaS</div>
        </div>

        <div className="trk-copyright">© {new Date().getFullYear()} Trucking ERP</div>
      </div>
    </div>
  );
}

export default LoginPage;
