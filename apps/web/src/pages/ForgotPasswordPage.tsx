import React, { useState } from "react";
import { Link } from "react-router-dom";
import { forgotPassword } from "../api";

function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = await forgotPassword({
        email: email.trim(),
        reset_base_url: window.location.origin,
      });
      if (data.sent) {
        setSent(true);
      } else {
        setError(data.message || "No account found with that email. Check the address or sign up.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  if (sent) {
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
            <h2>Check your email</h2>
            <p className="trk-foot">
              If an account exists for <strong>{email}</strong>, you will receive a password reset link shortly.
            </p>
            <p className="trk-foot" style={{ marginTop: "1rem" }}>
              The link expires in about an hour. Didn’t get it? Check spam or{" "}
              <button type="button" onClick={() => { setSent(false); setError(null); }} className="trk-link" style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}>try again</button>.
            </p>
            <div className="trk-row" style={{ marginTop: "1.5rem" }}>
              <Link to="/login" className="trk-link">Back to sign in</Link>
            </div>
          </div>
          <div className="trk-copyright">© {new Date().getFullYear()} Trucking ERP</div>
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
          <h2>Forgot password?</h2>
          <p className="trk-foot">Enter your email and we’ll send you a link to reset your password.</p>
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
                placeholder="you@company.com"
              />
            </div>
            <button type="submit" disabled={loading} className="trk-primary">
              {loading ? "Sending..." : "Send reset link"}
            </button>
            <div className="trk-row" style={{ marginTop: "1rem" }}>
              <Link to="/login" className="trk-link">Back to sign in</Link>
            </div>
          </form>
        </div>
        <div className="trk-copyright">© {new Date().getFullYear()} Trucking ERP</div>
      </div>
    </div>
  );
}

export default ForgotPasswordPage;
