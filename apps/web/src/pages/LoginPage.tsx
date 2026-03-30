import React, { useState, useEffect, useCallback, useRef } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import {
  login,
  loginStepUpIssue,
  loginStepUpVerify,
  LoginVerificationRequiredError,
  LoginStepUpRequiredError,
} from "../api";
import { authErrorToMessage } from "../utils/authErrorToMessage";
import { loadTurnstileScript } from "../lib/turnstile";

const TURNSTILE_SITE_KEY = (import.meta.env.VITE_TURNSTILE_SITE_KEY ?? "").trim();

function loginErrorStatus(err: unknown): number {
  if (err instanceof Error && "status" in err && typeof (err as Error & { status?: number }).status === "number") {
    return (err as Error & { status: number }).status;
  }
  return 401;
}

function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsVerification, setNeedsVerification] = useState(false);
  const [loginChallengeId, setLoginChallengeId] = useState<string | null>(null);

  const turnstileContainerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);
  /** If step-up was entered after a Turnstile-backed login attempt, reuse the same token on the final login. */
  const otpFlowTurnstileRef = useRef<string | null>(null);

  // Show session error when redirected from protected route (e.g. "Your session expired. Please sign in again.")
  useEffect(() => {
    const sessionError = location.state?.sessionError as string | undefined;
    if (sessionError) setError(sessionError);
  }, [location.state]);

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
        });
        setNeedsVerification(false);
        resetStepUpState();
        navigateAfterLogin(result);
      } catch (err) {
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
          setLoginChallengeId(err.loginChallengeId);
          return;
        }
        if (err instanceof LoginVerificationRequiredError) {
          if (!TURNSTILE_SITE_KEY) {
            setError("Sign-in verification is unavailable. Please try again later or contact support.");
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
    [email, password, navigateAfterLogin, resetStepUpState]
  );

  // Changing credentials ends verification / step-up flows.
  useEffect(() => {
    setNeedsVerification(false);
    resetStepUpState();
  }, [email, password, resetStepUpState]);

  useEffect(() => {
    if (!needsVerification || !TURNSTILE_SITE_KEY) return;
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
        sitekey: TURNSTILE_SITE_KEY,
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
  }, [needsVerification, performLogin]);

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
      });
      resetStepUpState();
      navigateAfterLogin(result);
    } catch (err) {
      if (err instanceof LoginVerificationRequiredError) {
        if (!TURNSTILE_SITE_KEY) {
          setError("Sign-in verification is unavailable. Please try again later or contact support.");
        } else {
          setError(null);
          setNeedsVerification(true);
        }
        return;
      }
      if (err instanceof LoginStepUpRequiredError) {
        setError("Additional verification is still required. Try signing in again.");
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
            {error && <div className="trk-error">{error}</div>}

            <div className="trk-field">
              <label className="trk-label">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="trk-input"
                placeholder="admin@company.com"
                disabled={Boolean(loginChallengeId)}
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
                disabled={Boolean(loginChallengeId)}
              />
            </div>

            {loginChallengeId ? (
              <div className="trk-field">
                <p className="trk-foot" style={{ marginBottom: "0.75rem" }}>
                  Enter the verification code sent to your email.
                </p>
                <label className="trk-label">Verification code</label>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  className="trk-input"
                  placeholder="6-digit code"
                />
                <button type="button" className="trk-link" style={{ marginTop: "0.5rem", background: "none", border: "none", padding: 0, cursor: "pointer" }} onClick={() => void handleResendStepUp()} disabled={loading}>
                  Resend code
                </button>
              </div>
            ) : null}

            {needsVerification && TURNSTILE_SITE_KEY && !loginChallengeId ? (
              <div className="trk-field">
                <p className="trk-foot" style={{ marginBottom: "0.75rem" }}>
                  Complete verification to continue signing in.
                </p>
                <div ref={turnstileContainerRef} className="trk-turnstile-host" />
              </div>
            ) : null}

            <button type="submit" disabled={loading} className="trk-primary">
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
