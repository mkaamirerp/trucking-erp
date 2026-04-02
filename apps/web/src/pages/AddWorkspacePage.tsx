import React, { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { checkSlugAvailability, createWorkspace } from "../api";
import { useAuth } from "../contexts/AuthContext";

const COUNTRIES = [
  { value: "US", label: "United States" },
  { value: "CA", label: "Canada" },
];

/**
 * Existing signed-in users only: POST /auth/workspaces.
 * Not used for the public landing CTA; that is /create-workspace (SignupPage).
 */
export default function AddWorkspacePage() {
  const { authReady, isValid, isValidating } = useAuth();
  const [slug, setSlug] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [street, setStreet] = useState("");
  const [city, setCity] = useState("");
  const [region, setRegion] = useState("");
  const [postal, setPostal] = useState("");
  const [country, setCountry] = useState("US");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [slugHint, setSlugHint] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const s = slug.trim().toLowerCase();
    if (s.length < 3) {
      setSlugHint(null);
      return;
    }
    const t = window.setTimeout(async () => {
      try {
        const r = await checkSlugAvailability(s);
        if (!cancelled) setSlugHint(r.available ? "This workspace URL is available." : "This URL is not available.");
      } catch {
        if (!cancelled) setSlugHint(null);
      }
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [slug]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const ws = slug.trim().toLowerCase();
    if (ws.length < 3) {
      setError("Workspace URL must be at least 3 characters.");
      return;
    }
    setBusy(true);
    try {
      const raw = await createWorkspace({
        workspace_slug: ws,
        company_legal_name: companyName.trim(),
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone: phone.trim(),
        address: {
          street: street.trim(),
          city: city.trim(),
          region: region.trim(),
          postal: postal.trim(),
          country: country.trim().toUpperCase(),
        },
      });
      const url = (raw as { workspace_url?: string }).workspace_url;
      if (url) {
        window.location.href = url;
        return;
      }
      setError("Workspace created but no redirect URL was returned.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  if (!authReady || isValidating) {
    return (
      <div className="trk-auth">
        <div className="trk-auth-wrap text-center text-slate-400">Loading…</div>
      </div>
    );
  }

  if (!isValid) {
    return <Navigate to="/login" replace state={{ from: "/add-workspace" }} />;
  }

  return (
    <div className="trk-auth">
      <div className="trk-auth-wrap">
        <div className="trk-brand">
          <div className="trk-badge">🚚</div>
          <div>
            <h1>Trucking ERP</h1>
            <p>Add another company workspace</p>
          </div>
        </div>

        <div className="trk-card">
          <h2>New company workspace</h2>
          <p className="trk-foot">You’re signed in. Your other workspaces stay as they are.</p>

          <form onSubmit={onSubmit}>
            {error && <div className="trk-error">{error}</div>}

            <div className="trk-field">
              <label className="trk-label">Workspace URL (slug)</label>
              <input
                className="trk-input"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                placeholder="acme-freight"
                autoComplete="off"
                required
              />
              {slugHint && <p className="mt-1 text-xs text-slate-500">{slugHint}</p>}
            </div>

            <div className="trk-field">
              <label className="trk-label">Legal company name</label>
              <input
                className="trk-input"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="trk-field">
                <label className="trk-label">First name</label>
                <input className="trk-input" value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
              </div>
              <div className="trk-field">
                <label className="trk-label">Last name</label>
                <input className="trk-input" value={lastName} onChange={(e) => setLastName(e.target.value)} required />
              </div>
            </div>

            <div className="trk-field">
              <label className="trk-label">Phone</label>
              <input className="trk-input" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} required />
            </div>

            <div className="trk-field">
              <label className="trk-label">Street</label>
              <input className="trk-input" value={street} onChange={(e) => setStreet(e.target.value)} required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="trk-field">
                <label className="trk-label">City</label>
                <input className="trk-input" value={city} onChange={(e) => setCity(e.target.value)} required />
              </div>
              <div className="trk-field">
                <label className="trk-label">Region / state</label>
                <input className="trk-input" value={region} onChange={(e) => setRegion(e.target.value)} required />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="trk-field">
                <label className="trk-label">Postal</label>
                <input className="trk-input" value={postal} onChange={(e) => setPostal(e.target.value)} required />
              </div>
              <div className="trk-field">
                <label className="trk-label">Country</label>
                <select className="trk-input" value={country} onChange={(e) => setCountry(e.target.value)}>
                  {COUNTRIES.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <button type="submit" disabled={busy} className="trk-primary">
              {busy ? "Creating…" : "Create workspace"}
            </button>
          </form>

          <div className="trk-row mt-4">
            <Link to="/" className="trk-link">
              Back to home
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
