import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { setupTenant, getSetupPrefill } from "../api";
import { getTenantSlugFromHost } from "../tenant";
import { COUNTRIES } from "../data/countries";

export default function CompanySetupPage() {
  const slug = getTenantSlugFromHost();

  // Setup requires a tenant subdomain (e.g. demo.truckerp.me). Main domain has no tenant.
  if (!slug) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6">
        <div className="max-w-md rounded-xl border border-slate-700 bg-slate-900/60 p-6 text-center">
          <h1 className="text-lg font-semibold text-slate-200">No workspace in URL</h1>
          <p className="mt-2 text-sm text-slate-400">
            Open this page from your workspace subdomain, e.g.{" "}
            <strong className="text-slate-300">https://your-slug.truckerp.me/account-setup</strong>
          </p>
          <Link
            to="/"
            className="mt-4 inline-block rounded-lg bg-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-600"
          >
            Back to home
          </Link>
        </div>
      </div>
    );
  }

  const [form, setForm] = useState({
    street: "",
    city: "",
    region: "",
    postal: "",
    dot_number: "",
    mc_number: "",
    cvor_number: "",
    hst_number: "",
    operator_license: "",
    fleet_size: "",
  });
  const [country, setCountry] = useState("");
  const [prefill, setPrefill] = useState<{
    company_legal_name?: string;
    country?: string;
    owner_email?: string;
    owner_phone?: string;
    address?: { street?: string; city?: string; region?: string; postal?: string; country?: string };
  } | null>(null);
  const [geoCountry, setGeoCountry] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // Prefill from onboarding payload (server-side); read-only company name/email, editable address + DOT/MC/CVOR (only when we have a tenant slug)
  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    getSetupPrefill()
      .then((res) => {
        if (cancelled) return;
        if (res?.prefill && Object.keys(res.prefill).length > 0) {
          setPrefill(res.prefill);
          setCountry((prev) => prev || res.prefill?.country || res.country || "");
          const addr = res.prefill?.address;
          if (addr) {
            setForm((f) => ({
              ...f,
              street: f.street || addr.street || "",
              city: f.city || addr.city || "",
              region: f.region || addr.region || "",
              postal: f.postal || addr.postal || "",
            }));
          }
          if (res.country) setCountry((prev) => prev || res.country);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const browserRegion = useMemo(() => {
    if (typeof navigator === "undefined") return "";
    const languages =
      navigator.languages && navigator.languages.length > 0
        ? navigator.languages
        : [navigator.language];
    for (const lang of languages) {
      const region = lang.split("-")[1];
      if (region) return region.toUpperCase();
    }
    return "";
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("https://ipapi.co/json/")
      .then((res) => res.json())
      .then((data) => {
        if (cancelled) return;
        const code = String(data?.country_code || "").toUpperCase();
        if (code) {
          setGeoCountry(code);
          const preferred = code === "US" && browserRegion === "CA" ? "CA" : code;
          setCountry((prev) => prev || preferred);
        }
      })
      .catch(() => {
        // ignore geo failures
      });
    return () => {
      cancelled = true;
    };
  }, [browserRegion]);

  const geoCountryName = useMemo(() => {
    if (!geoCountry) return "Unknown";
    const match = COUNTRIES.find((entry) => entry.code === geoCountry);
    return match ? match.name : geoCountry;
  }, [geoCountry]);

  const browserRegionName = useMemo(() => {
    if (!browserRegion) return "Unknown";
    const match = COUNTRIES.find((entry) => entry.code === browserRegion);
    return match ? match.name : browserRegion;
  }, [browserRegion]);

  const submit = async () => {
    setError(null);
    setFieldErrors({});
    if (!slug) {
      setError("Missing tenant slug.");
      return;
    }

    const trim = (value: string) => value.trim();
    const errors: Record<string, string> = {};
    const dot = trim(form.dot_number);
    const mc = trim(form.mc_number);
    const cvor = trim(form.cvor_number);
    const street = trim(form.street);
    const city = trim(form.city);
    const region = trim(form.region);
    const postal = trim(form.postal);

    if (!country) errors.country = "Please select a country.";
    if (!street) errors.street = "Street address is required.";
    if (!city) errors.city = "City is required.";
    if (!region) errors.region = "State / Province is required.";
    if (!postal) errors.postal = "Postal / ZIP code is required.";

    if (country === "US") {
      if (!dot) errors.dot_number = "USDOT number is required for USA.";
    }
    if (country === "CA") {
      if (!cvor) errors.cvor_number = "CVOR number is required for Canada.";
    }

    if (dot && !/^\d{1,8}$/.test(dot)) errors.dot_number = "USDOT must be 1–8 digits (US).";
    if (mc && !/^\d{6,7}$/.test(mc)) errors.mc_number = "MC must be 6–7 digits (US).";
    if (cvor && !/^\d{9}$/.test(cvor)) errors.cvor_number = "CVOR must be exactly 9 digits (CA/ON).";

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setBusy(true);
    try {
      const c = (country || "US").substring(0, 2).toUpperCase();
      await setupTenant({
        legal_name: prefill?.company_legal_name || "Company",
        address: { street, city, region, postal, country: c },
        company_phone: prefill?.owner_phone?.trim() || undefined,
        company_email: prefill?.owner_email?.trim() || undefined,
        dot_number: form.dot_number.trim() || undefined,
        mc_number: form.mc_number.trim() || undefined,
        cvor_number: form.cvor_number.trim() || undefined,
        hst_number: form.hst_number.trim() || undefined,
        operator_license: form.operator_license.trim() || undefined,
        country: c,
      });
      window.location.assign("/dashboard");
    } catch (err: any) {
      setError(err?.message?.slice(0, 300) || "Setup failed");
    } finally {
      setBusy(false);
    }
  };

  const missing: string[] = [];
  if (!country) missing.push("Country");
  if (!form.street.trim()) missing.push("Address");
  if (country === "US" && !form.dot_number.trim()) missing.push("USDOT number");
  if (country === "CA" && !form.cvor_number.trim()) missing.push("CVOR (CA)");

  return (
    <div className="trk-setup">
      <div className="trk-setup-wrap">
        <div className="trk-setup-top">
          <div className="trk-brand">
            <div className="trk-badge">TE</div>
            <div>
              <h1>Trucking ERP</h1>
              <p>Finish your company profile</p>
            </div>
          </div>
          <button type="button" className="trk-back" onClick={() => window.location.assign("/")}>
            Back to home
          </button>
        </div>

        <div className="trk-setup-card">
          <div className="trk-step">STEP 2</div>
          <h2 className="trk-title">Tell us about your company</h2>
          <p className="trk-sub">
            Complete the required fields to activate your workspace. You’ll stay on this page
            until everything is filled, then we’ll drop you into the dashboard.
          </p>

          {error ? <div className="trk-warning">{error}</div> : null}

          {prefill?.company_legal_name || prefill?.owner_email || prefill?.owner_phone ? (
            <div className="trk-grid trk-full mb-4 p-3 rounded-lg bg-slate-800/50 border border-slate-700 text-sm text-slate-300">
              <div className="trk-label text-slate-400">From signup (read-only)</div>
              {prefill.company_legal_name ? (
                <div className="font-medium text-slate-200">{prefill.company_legal_name}</div>
              ) : null}
              {prefill.owner_email ? (
                <div className="text-slate-300">Email: {prefill.owner_email}</div>
              ) : null}
              {prefill.owner_phone ? (
                <div className="text-slate-300">Phone: {prefill.owner_phone}</div>
              ) : null}
            </div>
          ) : null}

          <div className="trk-grid">
            <div className="trk-grid trk-grid-3 trk-full">
              <div className="trk-field">
                <label className="trk-label" htmlFor="country_select">Country</label>
                <select
                  id="country_select"
                  className="trk-select"
                  value={country}
                  onChange={(e) => {
                    setCountry(e.target.value);
                    if (fieldErrors.country) {
                      setFieldErrors((prev) => {
                        const next = { ...prev };
                        delete next.country;
                        return next;
                      });
                    }
                  }}
                  aria-invalid={Boolean(fieldErrors.country)}
                  aria-describedby={fieldErrors.country ? "country_error" : undefined}
                >
                  <option value="">Select a country</option>
                  <option value="US">United States</option>
                  <option value="CA">Canada</option>
                  {COUNTRIES.filter((c) => c.code !== "US" && c.code !== "CA").map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.name}
                    </option>
                  ))}
                </select>
                <div className="mt-2 text-xs text-slate-300">
                  Detected from IP: {geoCountryName}
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  Browser region: {browserRegionName}
                </div>
                {fieldErrors.country ? (
                  <p id="country_error" className="mt-1 text-xs text-rose-200" role="alert">
                    {fieldErrors.country}
                  </p>
                ) : null}
              </div>
            </div>

            <div className="trk-field trk-full">
              <label className="trk-label" htmlFor="street">Street address</label>
              <input
                id="street"
                className="trk-input"
                value={form.street}
                onChange={(e) => {
                  setForm({ ...form, street: e.target.value });
                  if (fieldErrors.street) setFieldErrors((prev) => ({ ...prev, street: undefined }));
                }}
                placeholder="123 Main St"
                aria-invalid={Boolean(fieldErrors.street)}
              />
              {fieldErrors.street ? (
                <p className="mt-1 text-xs text-rose-200" role="alert">{fieldErrors.street}</p>
              ) : null}
            </div>
            <div className="trk-field">
              <label className="trk-label" htmlFor="city">City</label>
              <input
                id="city"
                className="trk-input"
                value={form.city}
                onChange={(e) => {
                  setForm({ ...form, city: e.target.value });
                  if (fieldErrors.city) setFieldErrors((prev) => ({ ...prev, city: undefined }));
                }}
                placeholder="City"
                aria-invalid={Boolean(fieldErrors.city)}
              />
              {fieldErrors.city ? (
                <p className="mt-1 text-xs text-rose-200" role="alert">{fieldErrors.city}</p>
              ) : null}
            </div>
            <div className="trk-field">
              <label className="trk-label" htmlFor="region">State / Province</label>
              <input
                id="region"
                className="trk-input"
                value={form.region}
                onChange={(e) => {
                  setForm({ ...form, region: e.target.value });
                  if (fieldErrors.region) setFieldErrors((prev) => ({ ...prev, region: undefined }));
                }}
                placeholder="ON"
                aria-invalid={Boolean(fieldErrors.region)}
              />
              {fieldErrors.region ? (
                <p className="mt-1 text-xs text-rose-200" role="alert">{fieldErrors.region}</p>
              ) : null}
            </div>
            <div className="trk-field">
              <label className="trk-label" htmlFor="postal">Postal / ZIP</label>
              <input
                id="postal"
                className="trk-input"
                value={form.postal}
                onChange={(e) => {
                  setForm({ ...form, postal: e.target.value });
                  if (fieldErrors.postal) setFieldErrors((prev) => ({ ...prev, postal: undefined }));
                }}
                placeholder="M5V 1A1"
                aria-invalid={Boolean(fieldErrors.postal)}
              />
              {fieldErrors.postal ? (
                <p className="mt-1 text-xs text-rose-200" role="alert">{fieldErrors.postal}</p>
              ) : null}
            </div>

            <div className="trk-field">
              <label className="trk-label" htmlFor="dot_number">
                USDOT number {country === "US" ? <span className="text-rose-300">*</span> : null}
              </label>
              <input
                id="dot_number"
                className="trk-input"
                value={form.dot_number}
                onChange={(e) => {
                  setForm({ ...form, dot_number: e.target.value });
                  if (fieldErrors.dot_number) {
                    setFieldErrors((prev) => {
                      const next = { ...prev };
                      delete next.dot_number;
                      return next;
                    });
                  }
                }}
                placeholder="USDOT number"
                aria-required={country === "US"}
                aria-invalid={Boolean(fieldErrors.dot_number)}
                aria-describedby={fieldErrors.dot_number ? "dot_number_error" : undefined}
              />
              {fieldErrors.dot_number ? (
                <p id="dot_number_error" className="mt-1 text-xs text-rose-200" role="alert">
                  {fieldErrors.dot_number}
                </p>
              ) : null}
            </div>
            <div className="trk-field">
              <label className="trk-label" htmlFor="mc_number">
                MC number (optional)
              </label>
              <input
                id="mc_number"
                className="trk-input"
                value={form.mc_number}
                onChange={(e) => {
                  setForm({ ...form, mc_number: e.target.value });
                  if (fieldErrors.mc_number) {
                    setFieldErrors((prev) => {
                      const next = { ...prev };
                      delete next.mc_number;
                      return next;
                    });
                  }
                }}
                placeholder="MC number (optional)"
                aria-invalid={Boolean(fieldErrors.mc_number)}
                aria-describedby={fieldErrors.mc_number ? "mc_number_error" : undefined}
              />
              {fieldErrors.mc_number ? (
                <p id="mc_number_error" className="mt-1 text-xs text-rose-200" role="alert">
                  {fieldErrors.mc_number}
                </p>
              ) : null}
            </div>

            <div className="trk-field">
              <label className="trk-label" htmlFor="cvor_number">
                CVOR number (CA carriers) {country === "CA" ? <span className="text-rose-300">*</span> : null}
              </label>
              <input
                id="cvor_number"
                className="trk-input"
                value={form.cvor_number}
                onChange={(e) => {
                  setForm({ ...form, cvor_number: e.target.value });
                  if (fieldErrors.cvor_number) {
                    setFieldErrors((prev) => {
                      const next = { ...prev };
                      delete next.cvor_number;
                      return next;
                    });
                  }
                }}
                placeholder="CVOR number"
                aria-required={country === "CA"}
                aria-invalid={Boolean(fieldErrors.cvor_number)}
                aria-describedby={fieldErrors.cvor_number ? "cvor_number_error" : undefined}
              />
              {fieldErrors.cvor_number ? (
                <p id="cvor_number_error" className="mt-1 text-xs text-rose-200" role="alert">
                  {fieldErrors.cvor_number}
                </p>
              ) : null}
            </div>
            <div className="trk-field">
              <label className="trk-label" htmlFor="hst_number">HST number (optional)</label>
              <input
                id="hst_number"
                className="trk-input"
                value={form.hst_number}
                onChange={(e) => setForm({ ...form, hst_number: e.target.value })}
                placeholder="HST number"
              />
            </div>

            <div className="trk-field trk-full">
              <label className="trk-label">Operator license</label>
              <input
                className="trk-input"
                value={form.operator_license}
                onChange={(e) => setForm({ ...form, operator_license: e.target.value })}
                placeholder="Operator license"
              />
            </div>
          </div>

          {missing.length > 0 ? (
            <div className="trk-warning">
              <strong>Account setup required before the dashboard unlocks. Missing:</strong>
              <ul>
                {missing.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="trk-setup-actions">
            <button className="trk-primary" disabled={busy} onClick={submit}>
              {busy ? "Saving..." : "Save and continue"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
