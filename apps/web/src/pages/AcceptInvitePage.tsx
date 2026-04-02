import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { acceptInvite } from "../api";

export default function AcceptInvitePage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!token) setError("Invalid invite link. No token provided.");
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 12) {
      setError("Password must be at least 12 characters");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      const result = await acceptInvite({ token, new_password: password });
      setSuccess(result.message || "Welcome! Redirecting...");
      if (result.workspace_url) {
        window.location.href = result.workspace_url;
      } else {
        setTimeout(() => (window.location.href = "/dashboard"), 2000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept invite");
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="trk-auth">
        <div className="trk-auth-wrap">
          <div className="trk-card">
            <h2>Invalid invite link</h2>
            <p className="trk-foot">This link is invalid or expired. Ask your admin to send a new invite.</p>
            <a href="/" className="trk-primary block w-full text-center py-2 mt-4">
              Go to sign in
            </a>
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
            <p>Set your password</p>
          </div>
        </div>

        <div className="trk-card">
          <h2>Welcome</h2>
          <p className="trk-foot">Set a password to access your workspace</p>

          <form onSubmit={handleSubmit}>
            {error && <div className="trk-error">{error}</div>}
            {success && <div className="rounded-lg border border-emerald-700/50 bg-emerald-950/30 p-3 text-emerald-400 text-sm">{success}</div>}

            <div className="trk-field">
              <label className="trk-label">Password (min 12 characters)</label>
              <input
                type="password"
                required
                minLength={12}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="trk-input"
                placeholder="••••••••••••"
              />
            </div>

            <div className="trk-field">
              <label className="trk-label">Confirm password</label>
              <input
                type="password"
                required
                minLength={12}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="trk-input"
                placeholder="••••••••••••"
              />
            </div>

            <button type="submit" disabled={loading} className="trk-primary">
              {loading ? "Setting password..." : "Continue"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
