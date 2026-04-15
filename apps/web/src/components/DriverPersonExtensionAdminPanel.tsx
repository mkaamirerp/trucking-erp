import { useCallback, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import {
  getDriverPersonExtension,
  getPersonWorkspaceDriverRoleConfiguration,
  patchPersonWorkspaceDriverRoleConfiguration,
  putDriverPersonExtension,
  type DriverPersonExtensionOut,
  type DriverPersonExtensionWrite,
} from "../api";

const C = {
  bg: "#0d0e11",
  surface: "#16181e",
  surf2: "#1e2029",
  border: "#2a2d36",
  accent: "#f5a623",
  red: "#e8380d",
  green: "#2ecc71",
  text: "#e8e9ec",
  muted: "#72747e",
  muted2: "#3a3d4a",
};

const DEFAULT_FORM: DriverPersonExtensionWrite = {
  employment_relationship_type: "company_driver",
  driver_operating_subtype: "long_haul",
  is_team_driver: false,
  team_role_type: null,
  provides_own_truck: false,
  provides_own_trailer: false,
  equipment_contribution_type: "company_equipment",
  insurance_commercial_approved: false,
};

const EMPLOYMENT = ["company_driver", "owner_operator"] as const;
const SUBTYPES = ["long_haul", "city_local", "shunt_yard"] as const;
const TEAM_ROLES = ["primary", "co_driver"] as const;
const EQUIPMENT = ["company_equipment", "driver_truck_only", "driver_truck_and_trailer", "unspecified"] as const;

function labelEmployment(v: string) {
  if (v === "company_driver") return "Company driver";
  if (v === "owner_operator") return "Owner operator";
  return v;
}

function labelSubtype(v: string) {
  if (v === "long_haul") return "Long haul";
  if (v === "city_local") return "City / local";
  if (v === "shunt_yard") return "Shunt / yard";
  return v;
}

function labelEquipment(v: string) {
  if (v === "company_equipment") return "Company equipment";
  if (v === "driver_truck_only") return "Driver truck only";
  if (v === "driver_truck_and_trailer") return "Driver truck and trailer";
  if (v === "unspecified") return "Unspecified";
  return v;
}

function outToForm(row: DriverPersonExtensionOut): DriverPersonExtensionWrite {
  return {
    employment_relationship_type: row.employment_relationship_type,
    driver_operating_subtype: row.driver_operating_subtype,
    is_team_driver: row.is_team_driver,
    team_role_type: row.team_role_type,
    provides_own_truck: row.provides_own_truck,
    provides_own_trailer: row.provides_own_trailer,
    equipment_contribution_type: row.equipment_contribution_type,
    insurance_commercial_approved: row.insurance_commercial_approved,
  };
}

/** Canonical values for hidden fields when employment is company driver (UI collapse; still sent on PUT). */
function applyCompanyDriverHiddenDefaults(f: DriverPersonExtensionWrite): DriverPersonExtensionWrite {
  return {
    ...f,
    equipment_contribution_type: "company_equipment",
    provides_own_truck: false,
    provides_own_trailer: false,
    insurance_commercial_approved: false,
  };
}

function validateDriverPersonExtensionForm(f: DriverPersonExtensionWrite): string | null {
  const ert = (f.employment_relationship_type || "").trim();
  if (!EMPLOYMENT.includes(ert as (typeof EMPLOYMENT)[number])) {
    return "Employment type must be company driver or owner operator.";
  }
  const st = (f.driver_operating_subtype || "").trim();
  if (st === "owner_operator") {
    return "Operating subtype cannot be owner operator; use employment type instead.";
  }
  if (!SUBTYPES.includes(st as (typeof SUBTYPES)[number])) {
    return "Operating subtype is not valid.";
  }
  if (f.is_team_driver) {
    const tr = (f.team_role_type || "").trim();
    if (!tr) return "Team role is required when team driver is enabled.";
    if (!TEAM_ROLES.includes(tr as (typeof TEAM_ROLES)[number])) return "Team role must be primary or co-driver.";
  } else if (f.team_role_type != null && String(f.team_role_type).trim() !== "") {
    return "Clear team role when not a team driver.";
  }
  const ect = (f.equipment_contribution_type || "").trim();
  if (!EQUIPMENT.includes(ect as (typeof EQUIPMENT)[number])) {
    return "Equipment contribution type is not valid.";
  }
  if (ect === "company_equipment" && (f.provides_own_truck || f.provides_own_trailer)) {
    return "Company equipment requires no driver-owned truck or trailer.";
  }
  if (ect === "driver_truck_only" && (!f.provides_own_truck || f.provides_own_trailer)) {
    return "Driver truck only requires own truck and not own trailer.";
  }
  if (ect === "driver_truck_and_trailer" && (!f.provides_own_truck || !f.provides_own_trailer)) {
    return "Driver truck and trailer requires both own truck and own trailer.";
  }
  return null;
}

function selectStyle(disabled: boolean): CSSProperties {
  return {
    width: "100%",
    boxSizing: "border-box",
    background: C.surf2,
    border: `1px solid ${C.border}`,
    borderRadius: 8,
    padding: "8px 10px",
    fontSize: 13,
    color: C.text,
    fontFamily: "inherit",
    outline: "none",
    opacity: disabled ? 0.55 : 1,
    cursor: disabled ? "not-allowed" : "pointer",
  };
}

function parseApiError(err: unknown): string {
  if (!(err instanceof Error) || !err.message) return "Request failed.";
  try {
    const j = JSON.parse(err.message) as { detail?: unknown };
    const d = j.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      const first = d[0] as { msg?: string } | undefined;
      return first?.msg || err.message;
    }
  } catch {
    /* ignore */
  }
  return err.message;
}

const fieldLabel: CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: C.muted,
  textTransform: "uppercase",
  letterSpacing: "0.12em",
  marginBottom: 6,
};

function CheckboxRow({
  checked,
  onChange,
  disabled,
  children,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled: boolean;
  children: string;
}) {
  return (
    <label
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "11px 12px",
        borderRadius: 8,
        border: `1px solid ${checked ? `${C.accent}55` : C.border}`,
        background: checked ? "rgba(245,166,35,0.06)" : C.surf2,
        cursor: disabled ? "default" : "pointer",
        transition: "border-color 0.15s, background 0.15s",
      }}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        style={{
          width: 18,
          height: 18,
          flexShrink: 0,
          margin: 0,
          accentColor: C.accent,
          cursor: disabled ? "not-allowed" : "pointer",
        }}
      />
      <span style={{ fontSize: 13, color: disabled ? C.muted : C.text, lineHeight: 1.35, userSelect: "none" }}>{children}</span>
    </label>
  );
}

export type DriverPersonExtensionAdminPanelProps =
  | { mode: "onboarding"; personId: number; editable: boolean; onAfterPersist?: () => void }
  | { mode: "people"; personId: number; editable: boolean; onAfterPersist?: () => void };

export default function DriverPersonExtensionAdminPanel(props: DriverPersonExtensionAdminPanelProps) {
  const { personId, editable, onAfterPersist } = props;
  const [loading, setLoading] = useState(editable);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<DriverPersonExtensionWrite>(DEFAULT_FORM);
  const [clientError, setClientError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!editable) return;
    setLoading(true);
    setServerError(null);
    setClientError(null);
    try {
      const row =
        props.mode === "onboarding"
          ? await getDriverPersonExtension(personId)
          : await getPersonWorkspaceDriverRoleConfiguration(personId);
      if (row) {
        const mapped = outToForm(row);
        setForm(
          mapped.employment_relationship_type.trim() === "company_driver"
            ? applyCompanyDriverHiddenDefaults(mapped)
            : mapped,
        );
      } else {
        setForm(DEFAULT_FORM);
      }
    } catch (e: unknown) {
      setServerError(parseApiError(e));
      setForm(DEFAULT_FORM);
    } finally {
      setLoading(false);
    }
  }, [personId, editable, props.mode]);

  useEffect(() => {
    if (!editable) {
      setLoading(false);
      setForm(DEFAULT_FORM);
      setClientError(null);
      setServerError(null);
      return;
    }
    void load();
  }, [editable, load]);

  const disabled = !editable || saving;
  const showForm = !loading || !editable;
  const isCompanyDriver = form.employment_relationship_type.trim() === "company_driver";

  const setField = <K extends keyof DriverPersonExtensionWrite>(key: K, value: DriverPersonExtensionWrite[K]) => {
    if (!editable) return;
    setForm((prev) => {
      let next = { ...prev, [key]: value };
      if (key === "employment_relationship_type" && String(value).trim() === "company_driver") {
        next = applyCompanyDriverHiddenDefaults(next);
      }
      if (key === "is_team_driver" && !value) {
        next.team_role_type = null;
      }
      if (key === "equipment_contribution_type") {
        const ect = value as string;
        if (ect === "company_equipment") {
          next.provides_own_truck = false;
          next.provides_own_trailer = false;
        } else if (ect === "driver_truck_only") {
          next.provides_own_truck = true;
          next.provides_own_trailer = false;
        } else if (ect === "driver_truck_and_trailer") {
          next.provides_own_truck = true;
          next.provides_own_trailer = true;
        }
      }
      return next;
    });
    setClientError(null);
    setServerError(null);
  };

  const saveDisabled = saving || loading;

  const onSave = async () => {
    if (!editable) return;
    let base: DriverPersonExtensionWrite = {
      ...form,
      team_role_type: form.is_team_driver ? (form.team_role_type || "").trim() || null : null,
    };
    if (base.employment_relationship_type.trim() === "company_driver") {
      base = applyCompanyDriverHiddenDefaults(base);
    }
    const payload = base;
    const v = validateDriverPersonExtensionForm(payload);
    if (v) {
      setClientError(v);
      return;
    }
    setSaving(true);
    setClientError(null);
    setServerError(null);
    try {
      if (props.mode === "onboarding") {
        const row = await putDriverPersonExtension(personId, payload);
        setForm(outToForm(row));
      } else {
        await patchPersonWorkspaceDriverRoleConfiguration(personId, payload);
        await load();
      }
      onAfterPersist?.();
    } catch (e: unknown) {
      setServerError(parseApiError(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        background: C.surface,
        border: `1px solid ${editable ? `${C.accent}44` : C.border}`,
        borderRadius: 12,
        padding: "16px 18px",
        marginBottom: 10,
        boxShadow: editable ? "0 0 20px rgba(245,166,35,0.08)" : undefined,
      }}
    >
      <div style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: 12, letterSpacing: 2, color: C.muted, marginBottom: 8 }}>
        {props.mode === "people" ? "Role-attached configuration" : "Driver Configuration"}
      </div>
      {props.mode === "people" && (
        <div style={{ fontSize: 11, color: C.muted2, marginBottom: 12, lineHeight: 1.45 }}>
          Driver role configuration stored on <span style={{ color: C.text }}>driver_person_extensions</span> (people-first correction
          path). Onboarding remains workflow only.
        </div>
      )}

      {!editable && (
        <div
          style={{
            fontSize: 12,
            color: C.muted,
            background: "rgba(245,166,35,0.08)",
            border: `1px solid ${C.accent}40`,
            borderRadius: 8,
            padding: "10px 12px",
            marginBottom: 16,
            lineHeight: 1.45,
          }}
        >
          Available after approval — fields preview defaults only.
        </div>
      )}

      {editable && (
        <>
          <div style={{ fontSize: 12, color: C.muted2, marginBottom: 12, lineHeight: 1.45 }}>
            {props.mode === "people" ? (
              <>
                Edit role-attached fields here; first save creates the row if needed. Same validation as workflow — use{" "}
                <strong style={{ color: C.text }}>Save</strong> to persist.
              </>
            ) : (
              <>
                Admin-only driver setup. Defaults are shown until saved — use <strong style={{ color: C.text }}>Save</strong> to persist.
              </>
            )}
          </div>
          <div
            style={{
              display: "flex",
              gap: 10,
              marginBottom: 16,
              flexWrap: "wrap",
              alignItems: "stretch",
            }}
          >
            <button
              type="button"
              onClick={() => void onSave()}
              disabled={saveDisabled}
              style={{
                flex: "1 1 120px",
                padding: "11px 16px",
                borderRadius: 8,
                border: "none",
                cursor: saveDisabled ? "not-allowed" : "pointer",
                opacity: saveDisabled ? 0.65 : 1,
                fontFamily: "'Bebas Neue', sans-serif",
                fontSize: 14,
                letterSpacing: "0.1em",
                background: `linear-gradient(135deg,${C.green},#27ae60)`,
                color: "#000",
                boxShadow: saveDisabled ? "none" : "0 2px 12px rgba(46,204,113,0.25)",
              }}
            >
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={() => void load()}
              disabled={saveDisabled}
              style={{
                flex: "0 0 auto",
                padding: "10px 16px",
                borderRadius: 8,
                border: `1px solid ${C.muted2}`,
                background: C.bg,
                color: C.text,
                cursor: saveDisabled ? "not-allowed" : "pointer",
                fontSize: 12,
                fontWeight: 600,
                letterSpacing: "0.04em",
                opacity: saveDisabled ? 0.5 : 1,
              }}
            >
              Reload
            </button>
          </div>
        </>
      )}

      {loading && editable && <div style={{ fontSize: 13, color: C.muted2, marginBottom: 8 }}>Loading…</div>}

      {showForm && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {(clientError || serverError) && editable && (
            <div
              style={{
                background: "rgba(232,56,13,0.1)",
                border: `1px solid ${C.red}55`,
                borderRadius: 8,
                padding: "10px 12px",
                fontSize: 13,
                color: "#fca5a5",
              }}
            >
              {clientError || serverError}
            </div>
          )}

          <div>
            <div style={fieldLabel}>Employment relationship</div>
            <select
              value={form.employment_relationship_type}
              onChange={(e) => setField("employment_relationship_type", e.target.value)}
              disabled={disabled}
              style={selectStyle(disabled)}
            >
              {EMPLOYMENT.map((v) => (
                <option key={v} value={v}>
                  {labelEmployment(v)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <div style={fieldLabel}>Operating subtype</div>
            <select
              value={form.driver_operating_subtype}
              onChange={(e) => setField("driver_operating_subtype", e.target.value)}
              disabled={disabled}
              style={selectStyle(disabled)}
            >
              {SUBTYPES.map((v) => (
                <option key={v} value={v}>
                  {labelSubtype(v)}
                </option>
              ))}
            </select>
          </div>

          <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 12 }}>
            <CheckboxRow
              checked={form.is_team_driver}
              onChange={(v) => setField("is_team_driver", v)}
              disabled={disabled}
            >
              Team driver
            </CheckboxRow>

            {form.is_team_driver && (
              <div style={{ paddingLeft: 2 }}>
                <div style={fieldLabel}>Team role</div>
                <select
                  value={form.team_role_type || ""}
                  onChange={(e) => setField("team_role_type", e.target.value || null)}
                  disabled={disabled}
                  style={selectStyle(disabled)}
                >
                  <option value="">Select…</option>
                  {TEAM_ROLES.map((v) => (
                    <option key={v} value={v}>
                      {v === "primary" ? "Primary" : "Co-driver"}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {!isCompanyDriver && (
            <>
              <div style={{ marginTop: 14 }}>
                <div style={fieldLabel}>Equipment contribution</div>
                <select
                  value={form.equipment_contribution_type}
                  onChange={(e) => setField("equipment_contribution_type", e.target.value)}
                  disabled={disabled}
                  style={selectStyle(disabled)}
                >
                  {EQUIPMENT.map((v) => (
                    <option key={v} value={v}>
                      {labelEquipment(v)}
                    </option>
                  ))}
                </select>
                <div style={{ fontSize: 11, color: C.muted, marginTop: 8, lineHeight: 1.5 }}>
                  Some presets auto-set own truck and own trailer to match backend rules.
                </div>
              </div>

              <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                <CheckboxRow
                  checked={form.provides_own_truck}
                  onChange={(v) => setField("provides_own_truck", v)}
                  disabled={disabled}
                >
                  Provides own truck
                </CheckboxRow>
                <CheckboxRow
                  checked={form.provides_own_trailer}
                  onChange={(v) => setField("provides_own_trailer", v)}
                  disabled={disabled}
                >
                  Provides own trailer
                </CheckboxRow>
                <CheckboxRow
                  checked={form.insurance_commercial_approved}
                  onChange={(v) => setField("insurance_commercial_approved", v)}
                  disabled={disabled}
                >
                  Commercial insurance approved
                </CheckboxRow>
              </div>
            </>
          )}

          {editable && (
            <div
              style={{
                display: "flex",
                gap: 10,
                marginTop: 22,
                paddingTop: 4,
                flexWrap: "wrap",
                alignItems: "stretch",
              }}
            >
              <button
                type="button"
                onClick={() => void onSave()}
                disabled={saveDisabled}
                style={{
                  flex: "1 1 120px",
                  padding: "11px 16px",
                  borderRadius: 8,
                  border: "none",
                  cursor: saveDisabled ? "not-allowed" : "pointer",
                  opacity: saveDisabled ? 0.65 : 1,
                  fontFamily: "'Bebas Neue', sans-serif",
                  fontSize: 14,
                  letterSpacing: "0.1em",
                  background: `linear-gradient(135deg,${C.green},#27ae60)`,
                  color: "#000",
                  boxShadow: saveDisabled ? "none" : "0 2px 12px rgba(46,204,113,0.25)",
                }}
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                type="button"
                onClick={() => void load()}
                disabled={saveDisabled}
                style={{
                  flex: "0 0 auto",
                  padding: "10px 16px",
                  borderRadius: 8,
                  border: `1px solid ${C.muted2}`,
                  background: C.bg,
                  color: C.text,
                  cursor: saveDisabled ? "not-allowed" : "pointer",
                  fontSize: 12,
                  fontWeight: 600,
                  letterSpacing: "0.04em",
                  opacity: saveDisabled ? 0.5 : 1,
                }}
              >
                Reload
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
