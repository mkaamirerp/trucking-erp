import React, { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { resetPassword } from "../api";

function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (newPassword.length < 12) {
      setError("Password must be at least 12 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (!token) {
      setError("Invalid reset link. Please use the link from your email.");
      return;
    }

    setLoading(true);
    try {
      await resetPassword({ token, new_password: newPassword });
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid or expired link. Please request a new password reset.");
    } finally {
      setLoading(false);
    }
  };

  if (success) {
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
            <h2>Password reset</h2>
            <p className="trk-foot">Your password has been updated. You can now sign in with your new password.</p>
            <div className="trk-row" style={{ marginTop: "1.5rem" }}>
              <Link to="/login" className="trk-primary" style={{ display: "inline-block", textDecoration: "none" }}>
                Sign in
              </Link>
            </div>
          </div>

          <div className="trk-copyright">
            © {new Date().getFullYear()} Trucking ERP
          </div>
        </div>
      </div>
    );
  }

  if (!token) {
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
            <h2>Invalid link</h2>
            <p className="trk-foot">This reset link is missing or invalid. Please request a new password reset from the sign-in page.</p>
            <div className="trk-row" style={{ marginTop: "1.5rem" }}>
              <Link to="/forgot-password" className="trk-link">Request new link</Link>
              <span style={{ margin: "0 0.5rem" }}>·</span>
              <Link to="/login" className="trk-link">Back to sign in</Link>
            </div>
          </div>

          <div className="trk-copyright">
            © {new Date().getFullYear()} Trucking ERP
          </div>
        </div>
      </div>
    );
  }

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
          <h2>Set new password</h2>
          <p className="trk-foot">Enter your new password (at least 12 characters).</p>

          <form onSubmit={handleSubmit}>
            {error && <div className="trk-error">{error}</div>}

            <div className="trk-field">
              <label className="trk-label">New password</label>
              <input
                type="password"
                required
                minLength={12}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="trk-input"
                placeholder="••••••••••••"
                autoComplete="new-password"
              />
            </div>

            <div className="trk-field">
              <label className="trk-label">Confirm password</label>
              <input
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="trk-input"
                placeholder="••••••••••••"
                autoComplete="new-password"
              />
            </div>

            <button type="submit" disabled={loading} className="trk-primary">
              {loading ? "Updating..." : "Update password"}
            </button>

            <div className="trk-row" style={{ marginTop: "1rem" }}>
              <Link to="/login" className="trk-link">Back to sign in</Link>
            </div>
          </form>
        </div>

        <div className="trk-copyright">
          © {new Date().getFullYear()} Trucking ERP
        </div>
      </div>
    </div>
  );
}

export default ResetPasswordPage;
