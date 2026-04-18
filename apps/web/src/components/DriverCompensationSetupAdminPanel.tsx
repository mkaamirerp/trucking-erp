import { useCallback, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import {
  getApplicationDriverCompensationSetup,
  getPersonWorkspaceCompensationSetup,
  patchPersonWorkspaceCompensationSetup,
  putApplicationDriverCompensationSetup,
  type DriverCompensationSetupOut,
  type DriverCompensationSetupWrite,
} from "../api";

const C = {
  bg:      "var(--trk-bg)",
  surface: "var(--trk-surface)",
  surf2:   "var(--trk-surface-2)",
  border:  "var(--trk-border)",
  accent:  "var(--trk-accent)",
  red:     "var(--trk-danger)",
  green:   "var(--trk-success)",
  text:    "var(--trk-text)",
  muted:   "var(--trk-text-muted)",
  muted2:  "var(--trk-border-strong)",
};

const GROSS_MODELS: DriverCompensationSetupWrite["gross_calc_type"][] = [
  "CPM",
  "PERCENT_REVENUE",
  "FLAT_PER_LOAD",
  "HOURLY",
  "SALARY",
];

const SETTLEMENT_FREQ = ["WEEKLY", "BIWEEKLY", "SEMI_MONTHLY", "MONTHLY"] as const;

const DISPATCH_FEE_BASIS = ["GROSS", "NET"] as const;

function labelModel(m: string) {
  switch (m) {
    case "CPM":
      return "CPM (loaded / empty)";
    case "PERCENT_REVENUE":
      return "% of revenue";
    case "FLAT_PER_LOAD":
      return "Flat per load / trip";
    case "HOURLY":
      return "Hourly";
    case "SALARY":
      return "Salary";
    default:
      return m;
  }
}

function outToForm(row: DriverCompensationSetupOut): DriverCompensationSetupWrite {
  const g = (row.gross_calc_type || "CPM") as DriverCompensationSetupWrite["gross_calc_type"];
  return {
    gross_calc_type: GROSS_MODELS.includes(g) ? g : "CPM",
    percent_rate: row.percent_rate ?? null,
    cpm_loaded: row.cpm_loaded ?? null,
    cpm_empty: row.cpm_empty ?? null,
    hourly_rate: row.hourly_rate ?? null,
    salary_amount: row.salary_amount ?? null,
    flat_amount: row.flat_amount ?? null,
    settlement_frequency: row.settlement_frequency || "BIWEEKLY",
    participates_in_fuel_discount_program: row.participates_in_fuel_discount_program ?? false,
    dispatch_fee_enabled: row.dispatch_fee_enabled ?? false,
    dispatch_fee_rate: row.dispatch_fee_rate ?? "0",
    dispatch_fee_basis: row.dispatch_fee_basis || "GROSS",
  };
}

const cardStyle: CSSProperties = {
  background: C.surface,
  border: `1px solid ${C.border}`,
  borderRadius: 12,
  padding: "16px 18px",
  marginBottom: 10,
};

const labelStyle: CSSProperties = {
  fontFamily: "'Bebas Neue', sans-serif",
  fontSize: 12,
  letterSpacing: 2,
  color: C.muted,
  marginBottom: 10,
};

export type DriverCompensationSetupAdminPanelProps =
  | { mode: "application"; applicationId: number; editable: boolean; onAfterPersist?: () => void }
  | { mode: "person"; personId: number; editable: boolean; onAfterPersist?: () => void };

export default function DriverCompensationSetupAdminPanel(props: DriverCompensationSetupAdminPanelProps) {
  const { editable, onAfterPersist } = props;
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [out, setOut] = useState<DriverCompensationSetupOut | null>(null);
  const [form, setForm] = useState<DriverCompensationSetupWrite | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data =
        props.mode === "application"
          ? await getApplicationDriverCompensationSetup(props.applicationId)
          : await getPersonWorkspaceCompensationSetup(props.personId);
      setOut(data);
      setForm(outToForm(data));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unable to load compensation setup.";
      setError(msg);
      setOut(null);
      setForm(null);
    } finally {
      setLoading(false);
    }
  }, [props]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    if (!form) return;
    setSaving(true);
    setNotice(null);
    setError(null);
    try {
      if (props.mode === "application") {
        const data = await putApplicationDriverCompensationSetup(props.applicationId, form);
        setOut(data);
        setForm(outToForm(data));
      } else {
        await patchPersonWorkspaceCompensationSetup(props.personId, form);
        await load();
      }
      onAfterPersist?.();
      setNotice("Saved");
      window.setTimeout(() => setNotice(null), 2500);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={cardStyle}>
        <div style={labelStyle}>Compensation setup</div>
        <div style={{ fontSize: 13, color: C.muted }}>Loading…</div>
      </div>
    );
  }

  if (error && !out) {
    const combinedModeOnly =
      props.mode === "application" &&
      (error.includes("404") || error.toLowerCase().includes("not available"));
    return (
      <div style={cardStyle}>
        <div style={labelStyle}>Compensation setup</div>
        <div style={{ fontSize: 13, color: C.muted2, lineHeight: 1.5 }}>
          {combinedModeOnly
            ? "Compensation setup is only available when the tenant is in combined person setup mode."
            : error}
        </div>
      </div>
    );
  }

  if (!form) return null;

  const isOO = (out?.employment_relationship_type || "").toLowerCase() === "owner_operator";

  return (
    <div style={{ ...cardStyle, borderColor: `${C.accent}55`, boxShadow: `0 0 20px rgba(91,159,212,0.08)` }}>
      <div style={{ ...labelStyle, color: C.accent }}>Compensation setup</div>
      <div style={{ fontSize: 12, color: C.muted2, marginBottom: 14, lineHeight: 1.5 }}>
        Pay model and settlement defaults are stored on the tenant <strong style={{ color: C.text }}>payee</strong> and{" "}
        <strong style={{ color: C.text }}>compensation profile</strong> for this driver — not in driver configuration.
        {out?.employment_relationship_type ? (
          <>
            {" "}
            Driver configuration: <span style={{ color: C.text }}>{out.employment_relationship_type}</span>.
          </>
        ) : null}
      </div>

      {notice && (
        <div style={{ fontSize: 12, color: C.green, marginBottom: 10 }}>{notice}</div>
      )}
      {error && (
        <div style={{ fontSize: 12, color: C.red, marginBottom: 10 }}>{error}</div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Field>
          <span>Compensation model</span>
          <select
            disabled={!editable}
            value={form.gross_calc_type}
            onChange={(e) =>
              setForm((f) =>
                f ? { ...f, gross_calc_type: e.target.value as DriverCompensationSetupWrite["gross_calc_type"] } : f,
              )
            }
            style={selectStyle}
          >
            {GROSS_MODELS.map((m) => (
              <option key={m} value={m}>
                {labelModel(m)}
              </option>
            ))}
          </select>
        </Field>

        {form.gross_calc_type === "CPM" && (
          <>
            <Field>
              <span>CPM loaded ($)</span>
              <input
                disabled={!editable}
                value={form.cpm_loaded ?? ""}
                onChange={(e) => setForm((f) => (f ? { ...f, cpm_loaded: e.target.value || null } : f))}
                style={inputStyle}
                inputMode="decimal"
              />
            </Field>
            <Field>
              <span>CPM empty ($) — optional</span>
              <input
                disabled={!editable}
                value={form.cpm_empty ?? ""}
                onChange={(e) => setForm((f) => (f ? { ...f, cpm_empty: e.target.value || null } : f))}
                style={inputStyle}
                inputMode="decimal"
              />
            </Field>
          </>
        )}

        {form.gross_calc_type === "PERCENT_REVENUE" && (
          <Field>
            <span>Percent of revenue (0–1, e.g. 0.82)</span>
            <input
              disabled={!editable}
              value={form.percent_rate ?? ""}
              onChange={(e) => setForm((f) => (f ? { ...f, percent_rate: e.target.value || null } : f))}
              style={inputStyle}
              inputMode="decimal"
            />
          </Field>
        )}

        {form.gross_calc_type === "HOURLY" && (
          <Field>
            <span>Hourly rate ($)</span>
            <input
              disabled={!editable}
              value={form.hourly_rate ?? ""}
              onChange={(e) => setForm((f) => (f ? { ...f, hourly_rate: e.target.value || null } : f))}
              style={inputStyle}
              inputMode="decimal"
            />
          </Field>
        )}

        {form.gross_calc_type === "SALARY" && (
          <Field>
            <span>Salary amount ($ / period)</span>
            <input
              disabled={!editable}
              value={form.salary_amount ?? ""}
              onChange={(e) => setForm((f) => (f ? { ...f, salary_amount: e.target.value || null } : f))}
              style={inputStyle}
              inputMode="decimal"
            />
          </Field>
        )}

        {form.gross_calc_type === "FLAT_PER_LOAD" && (
          <Field>
            <span>Flat per load ($)</span>
            <input
              disabled={!editable}
              value={form.flat_amount ?? ""}
              onChange={(e) => setForm((f) => (f ? { ...f, flat_amount: e.target.value || null } : f))}
              style={inputStyle}
              inputMode="decimal"
            />
          </Field>
        )}

        <Field>
          <span>Settlement frequency</span>
          <select
            disabled={!editable}
            value={form.settlement_frequency}
            onChange={(e) => setForm((f) => (f ? { ...f, settlement_frequency: e.target.value } : f))}
            style={selectStyle}
          >
            {SETTLEMENT_FREQ.map((s) => (
              <option key={s} value={s}>
                {s.replace("_", " ")}
              </option>
            ))}
          </select>
        </Field>

        <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: C.text, cursor: editable ? "pointer" : "default" }}>
          <input
            type="checkbox"
            disabled={!editable}
            checked={form.participates_in_fuel_discount_program}
            onChange={(e) =>
              setForm((f) => (f ? { ...f, participates_in_fuel_discount_program: e.target.checked } : f))
            }
          />
          Participates in company fuel discount / fuel program
        </label>

        {isOO && (
          <div
            style={{
              borderTop: `1px solid ${C.border}`,
              paddingTop: 12,
              marginTop: 4,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            <div style={{ fontSize: 12, color: C.muted }}>Owner-operator: company fee / commission (dispatch fee fields)</div>
            <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: C.text, cursor: editable ? "pointer" : "default" }}>
              <input
                type="checkbox"
                disabled={!editable}
                checked={form.dispatch_fee_enabled}
                onChange={(e) => setForm((f) => (f ? { ...f, dispatch_fee_enabled: e.target.checked } : f))}
              />
              Company dispatch / admin fee enabled
            </label>
            {form.dispatch_fee_enabled && (
              <>
                <Field>
                  <span>Fee rate (0–1 of basis)</span>
                  <input
                    disabled={!editable}
                    value={form.dispatch_fee_rate}
                    onChange={(e) => setForm((f) => (f ? { ...f, dispatch_fee_rate: e.target.value } : f))}
                    style={inputStyle}
                    inputMode="decimal"
                  />
                </Field>
                <Field>
                  <span>Fee basis</span>
                  <select
                    disabled={!editable}
                    value={DISPATCH_FEE_BASIS.includes(form.dispatch_fee_basis as (typeof DISPATCH_FEE_BASIS)[number]) ? form.dispatch_fee_basis : "GROSS"}
                    onChange={(e) => setForm((f) => (f ? { ...f, dispatch_fee_basis: e.target.value } : f))}
                    style={selectStyle}
                  >
                    {DISPATCH_FEE_BASIS.map((b) => (
                      <option key={b} value={b}>
                        {b}
                      </option>
                    ))}
                  </select>
                </Field>
              </>
            )}
          </div>
        )}

        {out?.payee_id != null && (
          <div style={{ fontSize: 11, color: C.muted2, fontFamily: "ui-monospace, monospace" }}>
            Payee #{out.payee_id}
            {out.worker_type ? ` · ${out.worker_type}` : ""}
          </div>
        )}

        {editable && (
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving}
            style={{
              marginTop: 6,
              padding: "10px 14px",
              borderRadius: 8,
              border: "none",
              background: C.accent,
              color: "var(--trk-btn-text)",
              fontWeight: 700,
              fontSize: 12,
              letterSpacing: 0.5,
              cursor: saving ? "wait" : "pointer",
            }}
          >
            {saving ? "Saving…" : "Save compensation setup"}
          </button>
        )}
      </div>
    </div>
  );
}

function Field({ children }: { children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12, color: C.muted }}>
      {children}
    </label>
  );
}

const inputStyle: CSSProperties = {
  padding: "8px 10px",
  borderRadius: 8,
  border: `1px solid ${C.border}`,
  background: C.surf2,
  color: C.text,
  fontSize: 13,
};

const selectStyle: CSSProperties = {
  ...inputStyle,
  cursor: "pointer",
};
