import { useCallback, useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  adminUploadPersonApplicationDocument,
  approvePersonApplicationForAdmin,
  completePersonApplicationOnboarding,
  getAdminApplicationFileUrl,
  getCombinedDriverApproveReadiness,
  getCompanyProfile,
  getPersonApplicationForAdmin,
  markAdminReviewEngaged,
  materializePersonForCombinedSetup,
  patchPersonApplicationReviewFields,
  rejectPersonApplicationForAdmin,
  requestPersonApplicationDocuments,
  setPersonApplicationDocumentAccepted,
  type ApplicantApplication,
  type CombinedDriverApproveReadiness,
  type PersonApplicationReviewPatchPayload,
} from "../api";
import DriverCompensationSetupAdminPanel from "../components/DriverCompensationSetupAdminPanel";
import DriverPersonExtensionAdminPanel from "../components/DriverPersonExtensionAdminPanel";

type WorkHistoryEntry = {
  company_name?: string;
  position_title?: string;
  start_date?: string;
  end_date?: string;
  reason_for_leaving?: string;
  supervisor_name?: string;
  supervisor_phone?: string;
  equipment_operated?: string;
  city_state?: string;
  subject_to_fmcsa?: string;
};

type ReferenceEntry = {
  full_name?: string;
  relationship?: string;
  company?: string;
  phone?: string;
  email?: string;
  known_duration?: string;
};

type IntakeDocMeta = {
  storage_key?: string;
  file_id?: string;
  original_filename?: string;
  uploaded_at?: string;
  workflow_status?: string;
  requested_at?: string;
  requested_by_member_id?: number;
  accepted_at?: string;
  accepted_by_member_id?: number;
  uploaded_by?: string;
};

type IntakeFileMeta = {
  storage_key?: string;
  file_id?: string;
  enh_file_id?: string;
  original_filename?: string;
  upload_status?: string;
};

type IntakePayload = {
  cdl_class?: string;
  endorsements?: string;
  restrictions?: string;
  conditions?: string;
  middle_name?: string;
  date_of_birth?: string;
  ssn?: string;
  nationality?: string;
  license_issue_date?: string;
  sex?: string;
  height?: string;
  years_experience?: string;
  total_miles?: string;
  equipment_types?: string;
  accidents_last_3_years?: string;
  violations_last_3_years?: string;
  dot_medical_card_expiry?: string;
  emergency_contact_name?: string;
  emergency_contact_relationship?: string;
  emergency_contact_phone?: string;
  jobs?: WorkHistoryEntry[];
  refs?: ReferenceEntry[];
  files?: Record<string, IntakeFileMeta>;
  documents?: Record<string, IntakeDocMeta>;
  agree_info_accurate?: boolean;
  agree_background_check?: boolean;
  agree_dot_compliance?: boolean;
};

function isoInputDate(v?: string | null): string {
  if (!v) return "";
  const s = String(v);
  return s.length >= 10 ? s.slice(0, 10) : s;
}

function buildReviewDraft(a: ApplicantApplication): PersonApplicationReviewPatchPayload {
  const p = (a.intake_payload || {}) as IntakePayload;
  return {
    first_name: a.first_name ?? "",
    last_name: a.last_name ?? "",
    phone: a.phone ?? "",
    email: a.email ?? "",
    address_street: a.address_street ?? "",
    address_city: a.address_city ?? "",
    address_region: a.address_region ?? "",
    address_postal: a.address_postal ?? "",
    zip_code: a.zip_code ?? "",
    address_country: a.address_country ?? "",
    notes: a.notes ?? "",
    driver_license_number: a.driver_license_number ?? "",
    license_region: a.license_region ?? "",
    license_expiry: isoInputDate(a.license_expiry),
    middle_name: typeof p.middle_name === "string" ? p.middle_name : "",
    date_of_birth: isoInputDate(p.date_of_birth as string | undefined),
    license_issue_date: isoInputDate(p.license_issue_date as string | undefined),
    cdl_class: typeof p.cdl_class === "string" ? p.cdl_class : "",
    endorsements: typeof p.endorsements === "string" ? p.endorsements : "",
    restrictions: typeof p.restrictions === "string" ? p.restrictions : "",
    conditions: typeof p.conditions === "string" ? p.conditions : "",
  };
}

function diffReviewPatch(
  baseline: PersonApplicationReviewPatchPayload,
  edited: PersonApplicationReviewPatchPayload,
): PersonApplicationReviewPatchPayload {
  const out: PersonApplicationReviewPatchPayload = {};
  (Object.keys(edited) as (keyof PersonApplicationReviewPatchPayload)[]).forEach((k) => {
    const prev = baseline[k];
    const cur = edited[k];
    if (String(prev ?? "") !== String(cur ?? "")) {
      (out as Record<string, unknown>)[k as string] = cur;
    }
  });
  return out;
}

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

const STATUS_CFG: Record<string, { label: string; color: string; glow: string }> = {
  DRAFT: { label: "Draft", color: "#94a3b8", glow: "rgba(148,163,184,0.15)" },
  SUBMITTED: { label: "Submitted", color: C.accent, glow: "rgba(245,166,35,0.2)" },
  APPROVED: { label: "Approved", color: C.green, glow: "rgba(46,204,113,0.2)" },
  REJECTED: { label: "Rejected", color: C.red, glow: "rgba(232,56,13,0.2)" },
};

const DOC_META: Record<string, { label: string; icon: string; required: boolean }> = {
  dot_medical: { label: "DOT Medical Certificate", icon: "🏥", required: true },
  mvr: { label: "MVR (Motor Vehicle Record)", icon: "🚛", required: true },
  drug_test: { label: "Drug & Alcohol Test", icon: "🧪", required: true },
  psp_report: { label: "PSP Report", icon: "🔍", required: true },
  ss_card: { label: "Social Security Card", icon: "🪪", required: false },
  employment_verification: { label: "Employment Verification", icon: "📋", required: false },
  certificates: { label: "Certificates & Training", icon: "🏆", required: false },
  void_cheque: { label: "Void Cheque / Direct Deposit", icon: "📜", required: false },
};

function docSlotStatus(meta?: IntakeDocMeta): "missing" | "requested" | "uploaded" | "accepted" {
  if (!meta) return "missing";
  if (meta.workflow_status === "accepted" || meta.accepted_at) return "accepted";
  if (meta.storage_key || meta.file_id) return "uploaded";
  if (meta.requested_at) return "requested";
  return "missing";
}

const fmt = (v?: string | null) => (v && String(v).trim() ? v : "—");

function fmtDate(v?: string | null) {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleDateString("en-CA", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return v;
  }
}

function fmtDT(v?: string | null) {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleString("en-CA", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return v;
  }
}

function yesNoTag(v?: string) {
  if (v === "yes") return <Tag label="Yes" variant="red" />;
  if (v === "no") return <Tag label="No" variant="green" />;
  return "—";
}

function last4(ssn?: string) {
  if (!ssn) return "—";
  const digits = ssn.replace(/\D/g, "");
  if (!digits) return "—";
  return `•••-••-${digits.slice(-4)}`;
}

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CFG[status] ?? STATUS_CFG.DRAFT;
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      padding: "4px 14px",
      borderRadius: 999,
      background: `${cfg.color}18`,
      border: `1px solid ${cfg.color}44`,
      color: cfg.color,
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: "0.1em",
      textTransform: "uppercase",
      fontFamily: "'Bebas Neue', sans-serif",
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: cfg.color, boxShadow: `0 0 6px ${cfg.color}` }} />
      {cfg.label}
    </span>
  );
}

function DriverSetupTabBtn({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        fontFamily: "'Bebas Neue', sans-serif",
        fontSize: 11,
        letterSpacing: "0.1em",
        padding: "6px 14px",
        borderRadius: 6,
        border: active ? `1px solid ${C.accent}99` : `1px solid ${C.border}`,
        cursor: "pointer",
        background: active ? "rgba(245,166,35,0.14)" : C.surf2,
        color: active ? C.accent : C.muted,
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </button>
  );
}

function Tag({ label, variant = "default" }: { label: string; variant?: "default" | "green" | "red" | "orange" }) {
  const map = {
    default: { bg: C.surf2, color: C.muted, border: C.border },
    green: { bg: "rgba(46,204,113,0.1)", color: C.green, border: "rgba(46,204,113,0.35)" },
    red: { bg: "rgba(232,56,13,0.1)", color: C.red, border: "rgba(232,56,13,0.35)" },
    orange: { bg: "rgba(245,166,35,0.1)", color: C.accent, border: "rgba(245,166,35,0.35)" },
  };
  const s = map[variant];
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 9px",
      borderRadius: 5,
      background: s.bg,
      color: s.color,
      border: `1px solid ${s.border}`,
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: "0.08em",
      textTransform: "uppercase",
    }}>{label}</span>
  );
}

function Field({ label, value, mono = false, wide = false }: {
  label: string;
  value?: ReactNode;
  mono?: boolean;
  wide?: boolean;
}) {
  const empty = !value || value === "—";
  return (
    <div style={{ gridColumn: wide ? "1/-1" : undefined }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 3 }}>
        {label}
      </div>
      <div style={{
        fontSize: 13,
        color: empty ? C.muted2 : C.text,
        fontFamily: mono ? "'Courier New', monospace" : undefined,
        fontWeight: mono ? 600 : 400,
        lineHeight: 1.45,
        overflowWrap: "anywhere",
      }}>
        {empty ? "—" : value}
      </div>
    </div>
  );
}

function Grid({ children }: { children: ReactNode }) {
  return <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))", gap: "14px 22px" }}>{children}</div>;
}

function Divider() {
  return <div style={{ height: 1, background: C.border, margin: "14px 0" }} />;
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div style={{
      fontFamily: "'Bebas Neue', sans-serif",
      fontSize: 13,
      letterSpacing: 2,
      color: C.accent,
      display: "flex",
      alignItems: "center",
      gap: 8,
      marginBottom: 12,
    }}>
      <span style={{ width: 3, height: 14, background: C.accent, borderRadius: 2, display: "inline-block" }} />
      {children}
    </div>
  );
}

function Panel({ title, icon, children, defaultOpen = true, headerRight }: {
  title: string;
  icon: string;
  children: ReactNode;
  defaultOpen?: boolean;
  headerRight?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden", marginBottom: 10 }}>
      <div
        style={{
          display: "flex",
          alignItems: "stretch",
          borderBottom: open ? `1px solid ${C.border}` : "none",
        }}
      >
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          style={{
            flex: 1,
            minWidth: 0,
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: "13px 18px",
            display: "flex",
            alignItems: "center",
            gap: 9,
          }}
        >
          <span style={{ fontSize: 15 }}>{icon}</span>
          <span style={{ flex: 1, textAlign: "left", fontFamily: "'Bebas Neue', sans-serif", fontSize: 15, letterSpacing: "0.1em", color: C.text }}>
            {title}
          </span>
          <span style={{ color: C.muted, fontSize: 11, transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>▼</span>
        </button>
        {headerRight ? (
          <div
            style={{ display: "flex", alignItems: "center", paddingRight: 14, flexShrink: 0 }}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            {headerRight}
          </div>
        ) : null}
      </div>
      {open && <div style={{ padding: "16px 18px" }}>{children}</div>}
    </div>
  );
}

function Btn({
  label,
  variant,
  onClick,
  disabled,
  loading,
  title,
}: {
  label: ReactNode;
  variant: "approve" | "reject" | "ghost";
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
  title?: string;
}) {
  const s = {
    approve: { background: `linear-gradient(135deg,${C.green},#27ae60)`, color: "#000", border: "none" },
    reject: { background: "transparent", color: C.red, border: `1.5px solid ${C.red}66` },
    ghost: { background: "transparent", color: C.muted, border: `1px solid ${C.border}` },
  }[variant];

  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled || loading}
      style={{
        ...s,
        padding: "9px 18px",
        borderRadius: 8,
        fontFamily: "'Bebas Neue', sans-serif",
        fontSize: 14,
        letterSpacing: "0.08em",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.4 : 1,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 6,
        transition: "opacity 0.15s",
        width: "100%",
      }}
    >
      {loading ? "…" : label}
    </button>
  );
}

function DlViewCard({
  label,
  meta,
  applicationId,
  onView,
}: {
  label: string;
  meta: IntakeFileMeta;
  applicationId: number;
  onView: (applicationId: number, fileId: string, filename?: string) => void;
}) {
  const fileId = meta.storage_key || meta.file_id || meta.enh_file_id;
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!fileId) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    getAdminApplicationFileUrl(applicationId, fileId)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        setThumbUrl(url);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
      setThumbUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [applicationId, fileId]);

  if (!fileId) return null;
  return (
    <div style={{ background: C.surf2, border: `1px solid ${C.border}`, borderRadius: 10, padding: "12px 16px", minWidth: 140 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: C.text, marginBottom: 6 }}>CDL {label}</div>
      <div
        style={{
          width: 140,
          height: 88,
          borderRadius: 8,
          background: C.bg,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
          marginBottom: 8,
          cursor: "pointer",
        }}
        onClick={() => onView(applicationId, fileId, meta.original_filename)}
      >
        {loading && <span style={{ fontSize: 10, color: C.muted }}>Loading…</span>}
        {error && <span style={{ fontSize: 10, color: C.red }}>Failed to load</span>}
        {thumbUrl && !loading && !error && (
          <img
            src={thumbUrl}
            alt={`CDL ${label}`}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        )}
      </div>
      <div style={{ fontSize: 10, color: C.muted, marginBottom: 6, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {meta.original_filename || "Uploaded"}
      </div>
      <button
        type="button"
        onClick={() => onView(applicationId, fileId, meta.original_filename)}
        style={{
          fontSize: 11,
          color: C.accent,
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: 0,
          textDecoration: "underline",
        }}
      >
        View full size →
      </button>
    </div>
  );
}

function DocsGrid({
  docs,
  applicationId,
  onViewFile,
  canAdminAct,
  onAdminUpload,
  onAcceptToggle,
}: {
  docs?: Record<string, IntakeDocMeta>;
  applicationId: number;
  onViewFile: (applicationId: number, fileId: string, filename?: string) => void;
  canAdminAct: boolean;
  onAdminUpload: (docType: string, file: File) => Promise<void>;
  onAcceptToggle: (docType: string, accepted: boolean) => Promise<void>;
}) {
  const [uploadingKey, setUploadingKey] = useState<string | null>(null);
  const [acceptBusy, setAcceptBusy] = useState<string | null>(null);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
      {Object.entries(DOC_META).map(([key, meta]) => {
        const slot = docs?.[key];
        const status = docSlotStatus(slot);
        const fileId = slot?.storage_key || slot?.file_id;
        const border =
          status === "accepted"
            ? `${C.green}88`
            : status === "uploaded"
              ? `${C.green}55`
              : status === "requested"
                ? `${C.accent}66`
                : C.border;
        const statusTag =
          status === "accepted" ? (
            <Tag label="Accepted" variant="green" />
          ) : status === "uploaded" ? (
            <Tag label="Uploaded" variant="green" />
          ) : status === "requested" ? (
            <Tag label="Requested" variant="orange" />
          ) : (
            <Tag label="Missing" variant={meta.required ? "red" : "default"} />
          );
        return (
          <div
            key={key}
            style={{
              background: C.surf2,
              border: `1px solid ${border}`,
              borderRadius: 10,
              padding: "13px 15px",
              display: "flex",
              alignItems: "flex-start",
              gap: 11,
            }}
          >
            <span style={{ fontSize: 20, flexShrink: 0 }}>{meta.icon}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: C.text, marginBottom: 5 }}>{meta.label}</div>
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center" }}>
                {meta.required ? <Tag label="Required" variant="red" /> : <Tag label="Optional" />}
                {statusTag}
              </div>
              {slot?.original_filename && (
                <div style={{ fontSize: 10, color: C.muted, marginTop: 5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {slot.original_filename}
                </div>
              )}
              {fileId && (
                <button
                  type="button"
                  onClick={() => onViewFile(applicationId, fileId, slot?.original_filename)}
                  style={{
                    marginTop: 8,
                    fontSize: 11,
                    color: C.accent,
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                    textDecoration: "underline",
                  }}
                >
                  View document →
                </button>
              )}
              {canAdminAct && (
                <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
                  <label
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      letterSpacing: "0.06em",
                      textTransform: "uppercase",
                      color: C.muted,
                      cursor: uploadingKey === key ? "wait" : "pointer",
                      border: `1px dashed ${C.border}`,
                      borderRadius: 6,
                      padding: "6px 8px",
                      textAlign: "center",
                    }}
                  >
                    <input
                      type="file"
                      accept=".pdf,image/*"
                      className="sr-only"
                      style={{ position: "absolute", width: 0, height: 0, opacity: 0 }}
                      disabled={uploadingKey === key}
                      onChange={async (e) => {
                        const f = e.target.files?.[0];
                        e.target.value = "";
                        if (!f) return;
                        setUploadingKey(key);
                        try {
                          await onAdminUpload(key, f);
                        } finally {
                          setUploadingKey(null);
                        }
                      }}
                    />
                    {uploadingKey === key ? "Uploading…" : "Admin upload"}
                  </label>
                  {status === "uploaded" && (
                    <button
                      type="button"
                      disabled={acceptBusy === key}
                      onClick={async () => {
                        setAcceptBusy(key);
                        try {
                          await onAcceptToggle(key, true);
                        } finally {
                          setAcceptBusy(null);
                        }
                      }}
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        padding: "5px 8px",
                        borderRadius: 6,
                        border: `1px solid ${C.green}55`,
                        background: "rgba(46,204,113,0.12)",
                        color: C.green,
                        cursor: "pointer",
                      }}
                    >
                      Mark accepted
                    </button>
                  )}
                  {status === "accepted" && (
                    <button
                      type="button"
                      disabled={acceptBusy === key}
                      onClick={async () => {
                        setAcceptBusy(key);
                        try {
                          await onAcceptToggle(key, false);
                        } finally {
                          setAcceptBusy(null);
                        }
                      }}
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        padding: "5px 8px",
                        borderRadius: 6,
                        border: `1px solid ${C.border}`,
                        background: "transparent",
                        color: C.muted,
                        cursor: "pointer",
                      }}
                    >
                      Clear acceptance
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function WorkCard({ e, i }: { e: WorkHistoryEntry; i: number }) {
  return (
    <div style={{ background: C.surf2, border: `1px solid ${C.border}`, borderRadius: 10, padding: "16px 18px", marginBottom: 10 }}>
      <div style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: 12, letterSpacing: 2, color: C.accent, marginBottom: 12 }}>
        Employer {i + 1}
      </div>
      <Grid>
        <Field label="Company" value={fmt(e.company_name)} />
        <Field label="Position" value={fmt(e.position_title)} />
        <Field label="Start Date" value={fmtDate(e.start_date)} />
        <Field label="End Date" value={fmtDate(e.end_date)} />
        <Field label="Reason for Leaving" value={fmt(e.reason_for_leaving)} />
        <Field label="Equipment" value={fmt(e.equipment_operated)} />
        <Field label="Supervisor" value={fmt(e.supervisor_name)} />
        <Field label="Contact Phone" value={fmt(e.supervisor_phone)} mono />
        <Field label="City / State" value={fmt(e.city_state)} />
        <Field label="FMCSA Regulated" value={yesNoTag(e.subject_to_fmcsa)} />
      </Grid>
    </div>
  );
}

function RefCard({ e, i }: { e: ReferenceEntry; i: number }) {
  return (
    <div style={{ background: C.surf2, border: `1px solid ${C.border}`, borderRadius: 10, padding: "16px 18px", marginBottom: 10 }}>
      <div style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: 12, letterSpacing: 2, color: C.accent, marginBottom: 12 }}>
        Reference {i + 1}
      </div>
      <Grid>
        <Field label="Name" value={fmt(e.full_name)} />
        <Field label="Relationship" value={fmt(e.relationship)} />
        <Field label="Company" value={fmt(e.company)} />
        <Field label="Phone" value={fmt(e.phone)} mono />
        <Field label="Email" value={fmt(e.email)} />
        <Field label="Known Duration" value={fmt(e.known_duration)} />
      </Grid>
    </div>
  );
}

export default function DriverOnboardingAdminDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [application, setApplication] = useState<ApplicantApplication | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [showReject, setShowReject] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [actionNotice, setActionNotice] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [fileViewer, setFileViewer] = useState<{ url: string; title: string; isPdf: boolean; isImage: boolean } | null>(null);
  const [personSetupUiMode, setPersonSetupUiMode] = useState<"combined" | "segmented" | null>(null);
  const [reviewDraft, setReviewDraft] = useState<PersonApplicationReviewPatchPayload | null>(null);
  const [reviewBaseline, setReviewBaseline] = useState<PersonApplicationReviewPatchPayload | null>(null);
  const [reviewSaving, setReviewSaving] = useState(false);
  const [requestModalOpen, setRequestModalOpen] = useState(false);
  const [requestDocSelection, setRequestDocSelection] = useState<Record<string, boolean>>({});
  const [requestSubject, setRequestSubject] = useState("");
  const [requestBody, setRequestBody] = useState("");
  const [requestSending, setRequestSending] = useState(false);
  /** Header tabs: switch Driver extension vs Compensation when both panels exist. */
  const [driverSetupTab, setDriverSetupTab] = useState<"driver" | "compensation">("driver");
  const [approveReadiness, setApproveReadiness] = useState<CombinedDriverApproveReadiness | null>(null);
  const [onboardingCompleteLoading, setOnboardingCompleteLoading] = useState(false);
  const [readinessNonce, setReadinessNonce] = useState(0);
  const bumpApproveReadiness = useCallback(() => setReadinessNonce((n) => n + 1), []);

  useEffect(() => {
    const load = async () => {
      if (!id) return;
      setLoading(true);
      setError(null);
      try {
        const [data, co] = await Promise.all([
          getPersonApplicationForAdmin(Number(id)),
          getCompanyProfile().catch(() => null),
        ]);
        setApplication(data);
        const raw = co?.person_setup_ui_mode;
        if (raw === "combined" || raw === "segmented") {
          setPersonSetupUiMode(raw);
        } else {
          setPersonSetupUiMode("combined");
        }
      } catch (err: any) {
        setError(err?.message || "Unable to load application.");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [id]);

  /** SUBMITTED + no prior engagement → mark reviewed so the admin queue shows Processing (not Submitted). */
  useEffect(() => {
    if (!application?.id) return;
    if (application.status !== "SUBMITTED") return;
    if (application.reviewed_at) return;
    let cancelled = false;
    void (async () => {
      try {
        const next = await markAdminReviewEngaged(application.id);
        if (!cancelled) setApplication(next);
      } catch {
        /* non-fatal */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [application?.id, application?.status, application?.reviewed_at]);

  useEffect(() => {
    if (!application) {
      setReviewDraft(null);
      setReviewBaseline(null);
      return;
    }
    if (application.status === "SUBMITTED" || application.status === "APPROVED") {
      const d = buildReviewDraft(application);
      setReviewDraft(d);
      setReviewBaseline(d);
    } else {
      setReviewDraft(null);
      setReviewBaseline(null);
    }
  }, [application]);

  useEffect(() => {
    setDriverSetupTab("driver");
  }, [application?.id]);

  useEffect(() => {
    if (!application?.id || personSetupUiMode !== "combined") return;
    if (application.status !== "SUBMITTED") return;
    const isDd =
      (application.application_type || "DRIVER") === "DRIVER" &&
      (application.requested_role_code || "DRIVER").trim().toUpperCase() === "DRIVER";
    if (!isDd || application.person_id != null) return;
    let cancelled = false;
    void (async () => {
      try {
        const next = await materializePersonForCombinedSetup(application.id);
        if (!cancelled) setApplication(next);
      } catch {
        /* Saving review corrections can also materialize the person. */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    application?.id,
    application?.status,
    application?.person_id,
    application?.application_type,
    application?.requested_role_code,
    personSetupUiMode,
  ]);

  useEffect(() => {
    if (!application || personSetupUiMode !== "combined") {
      setApproveReadiness(null);
      return;
    }
    if (application.status !== "SUBMITTED") {
      setApproveReadiness(null);
      return;
    }
    const isDd =
      (application.application_type || "DRIVER") === "DRIVER" &&
      (application.requested_role_code || "DRIVER").trim().toUpperCase() === "DRIVER";
    if (!isDd) {
      setApproveReadiness(null);
      return;
    }
    let cancelled = false;
    void getCombinedDriverApproveReadiness(application.id).then((r) => {
      if (!cancelled) setApproveReadiness(r);
    });
    return () => {
      cancelled = true;
    };
  }, [
    application?.id,
    application?.status,
    application?.person_id,
    application?.application_type,
    application?.requested_role_code,
    personSetupUiMode,
    readinessNonce,
  ]);

  const base: CSSProperties = {
    minHeight: "100vh",
    background: C.bg,
    color: C.text,
    fontFamily: "'DM Sans', system-ui, sans-serif",
    backgroundImage: "repeating-linear-gradient(0deg,transparent,transparent 59px,#1a1c22 59px,#1a1c22 60px),repeating-linear-gradient(90deg,transparent,transparent 59px,#1a1c22 59px,#1a1c22 60px)",
  };

  if (loading) {
    return <div style={{ ...base, display: "flex", alignItems: "center", justifyContent: "center" }}><span style={{ color: C.muted }}>Loading…</span></div>;
  }

  if (error || !application) {
    return (
      <div style={{ ...base, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
          <div style={{ color: C.red, fontSize: 14 }}>{error ?? "Not found"}</div>
          <button
            onClick={() => navigate("/operations/driver-onboarding-review")}
            style={{ marginTop: 16, color: C.accent, background: "none", border: "none", cursor: "pointer", fontSize: 13 }}
          >
            ← Back
          </button>
        </div>
      </div>
    );
  }

  const p = (application.intake_payload || {}) as IntakePayload;
  const cfg = STATUS_CFG[application.status] ?? STATUS_CFG.DRAFT;
  const isSubmitted = application.status === "SUBMITTED";
  const isDriver = (application.application_type || "DRIVER") === "DRIVER";
  const requestedRole = (application.requested_role_code || "DRIVER").trim().toUpperCase();
  const tenantCombined = personSetupUiMode === "combined";
  const isDriverDriverSetup = isDriver && requestedRole === "DRIVER";
  /** Combined tenant: setup tabs/cards on this page (not gated on SUBMITTED vs APPROVED). Segmented: hidden entirely. */
  const showCombinedSetupChrome =
    tenantCombined &&
    isDriverDriverSetup &&
    application.status !== "REJECTED" &&
    (application.status === "SUBMITTED" || application.status === "APPROVED");
  const showDriverSetupTabs = showCombinedSetupChrome && application.person_id != null;
  const driverConfigurationEditable = showCombinedSetupChrome && application.person_id != null;
  const reviewWorkspaceOpen =
    !!reviewDraft && (application.status === "SUBMITTED" || application.status === "APPROVED");
  const approveCombinedBlocked =
    Boolean(
      isSubmitted &&
        tenantCombined &&
        isDriverDriverSetup &&
        approveReadiness?.applies &&
        !approveReadiness.ready,
    );
  const showMarkOnboardingComplete =
    application.status === "APPROVED" &&
    tenantCombined &&
    isDriverDriverSetup &&
    (application.setup_status ?? "") !== "complete";
  const ri: CSSProperties = {
    padding: "8px 10px",
    borderRadius: 8,
    border: `1px solid ${C.border}`,
    background: C.surf2,
    color: C.text,
    fontSize: 13,
  };

  const showNotice = (type: "success" | "error", message: string) => {
    setActionNotice({ type, message });
    window.setTimeout(() => {
      setActionNotice((current) => (current?.message === message ? null : current));
    }, 3500);
  };

  const saveReviewCorrections = async () => {
    if (!application || !reviewDraft || !reviewBaseline) return;
    const patch = diffReviewPatch(reviewBaseline, reviewDraft);
    if (Object.keys(patch).length === 0) {
      showNotice("error", "No changes to save.");
      return;
    }
    setReviewSaving(true);
    try {
      const next = await patchPersonApplicationReviewFields(application.id, patch);
      setApplication(next);
      showNotice("success", "Corrections saved.");
    } catch (err: unknown) {
      showNotice("error", err instanceof Error ? err.message : "Save failed");
    } finally {
      setReviewSaving(false);
    }
  };

  const handleViewFile = async (appId: number, fileId: string, filename?: string) => {
    try {
      const url = await getAdminApplicationFileUrl(appId, fileId);
      const lower = (filename || "").toLowerCase();
      const isPdf = lower.endsWith(".pdf");
      const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(filename || "");
      setFileViewer({ url, title: filename || "Document", isPdf, isImage });
    } catch {
      showNotice("error", "Could not load file");
    }
  };

  const closeFileViewer = () => {
    if (fileViewer?.url) URL.revokeObjectURL(fileViewer.url);
    setFileViewer(null);
  };

  const approve = async () => {
    if (!application) return;
    setActionLoading(true);
    setActionNotice(null);
    try {
      const next = await approvePersonApplicationForAdmin(application.id);
      setApplication(next);
      setApproveReadiness(null);
      setShowReject(false);
      setRejectReason("");
      showNotice("success", "Application approved.");
    } catch (err: any) {
      showNotice("error", err?.message || "Unable to approve application.");
    } finally {
      setActionLoading(false);
    }
  };

  const markOnboardingComplete = async () => {
    if (!application) return;
    setOnboardingCompleteLoading(true);
    setActionNotice(null);
    try {
      const next = await completePersonApplicationOnboarding(application.id);
      setApplication(next);
      showNotice("success", "Onboarding marked complete.");
    } catch (err: unknown) {
      showNotice("error", err instanceof Error ? err.message : "Could not complete onboarding.");
    } finally {
      setOnboardingCompleteLoading(false);
    }
  };

  const reject = async () => {
    if (!application) return;
    setActionLoading(true);
    setActionNotice(null);
    try {
      const next = await rejectPersonApplicationForAdmin(application.id, { rejection_reason: rejectReason.trim() });
      setApplication(next);
      setShowReject(false);
      setRejectReason("");
      showNotice("success", "Application rejected.");
    } catch (err: any) {
      showNotice("error", err?.message || "Unable to reject application.");
    } finally {
      setActionLoading(false);
    }
  };

  const reloadApplication = async () => {
    if (!id) return;
    const data = await getPersonApplicationForAdmin(Number(id));
    setApplication(data);
  };

  const openRequestDocumentsModal = () => {
    if (!application) return;
    const docs = ((application.intake_payload || {}) as IntakePayload).documents;
    const sel: Record<string, boolean> = {};
    for (const key of Object.keys(DOC_META)) {
      const dm = DOC_META[key];
      const st = docSlotStatus(docs?.[key]);
      sel[key] = !!(dm?.required && st !== "uploaded" && st !== "accepted");
    }
    setRequestDocSelection(sel);
    setRequestSubject("Documents needed for your application");
    setRequestBody(
      "Hello,\n\nWe need you to upload some documents so we can continue processing your application. When you are finished, resubmit from the onboarding page using the link below.\n\nThank you,",
    );
    setRequestModalOpen(true);
  };

  const sendDocumentRequest = async () => {
    if (!application) return;
    const doc_types = Object.entries(requestDocSelection).filter(([, v]) => v).map(([k]) => k);
    if (doc_types.length === 0) {
      showNotice("error", "Select at least one document type.");
      return;
    }
    setRequestSending(true);
    try {
      const res = await requestPersonApplicationDocuments(application.id, {
        doc_types,
        subject: requestSubject.trim(),
        body: requestBody.trim(),
      });
      setRequestModalOpen(false);
      await reloadApplication();
      if (res.email_sent) {
        showNotice("success", "Request sent and applicant link updated.");
      } else {
        showNotice("error", res.email_error || "Token updated but email was not sent.");
      }
    } catch (err: unknown) {
      showNotice("error", err instanceof Error ? err.message : "Request failed.");
    } finally {
      setRequestSending(false);
    }
  };

  return (
    <div style={base}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap');`}</style>

      {actionNotice && (
        <div
          style={{
            position: "fixed",
            top: 20,
            right: 20,
            zIndex: 2000,
            background: actionNotice.type === "success" ? C.green : C.red,
            color: "#000",
            padding: "10px 18px",
            borderRadius: 8,
            fontSize: 13,
            fontWeight: 700,
            boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
          }}
        >
          {actionNotice.message}
        </div>
      )}

      {fileViewer && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="File preview"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 3000,
            background: "rgba(0,0,0,0.9)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 24,
          }}
          onClick={closeFileViewer}
        >
          <div
            style={{
              background: C.surface,
              borderRadius: 12,
              maxWidth: "95vw",
              maxHeight: "95vh",
              overflow: "auto",
              position: "relative",
              boxShadow: "0 8px 48px rgba(0,0,0,0.6)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={closeFileViewer}
              aria-label="Close"
              style={{
                position: "absolute",
                top: 12,
                right: 12,
                width: 36,
                height: 36,
                borderRadius: 8,
                border: `1px solid ${C.border}`,
                background: C.surf2,
                color: C.text,
                fontSize: 18,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 1,
              }}
            >
              ✕
            </button>
            <div style={{ padding: "48px 24px 24px" }}>
              {fileViewer.isImage ? (
                <img
                  src={fileViewer.url}
                  alt={fileViewer.title}
                  style={{ maxWidth: "100%", maxHeight: "85vh", objectFit: "contain", display: "block" }}
                />
              ) : (
                <iframe
                  src={fileViewer.url}
                  title={fileViewer.title}
                  style={{ width: "min(85vw, 900px)", height: "85vh", border: "none", borderRadius: 8 }}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {requestModalOpen && application && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Request documents"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 2900,
            background: "rgba(0,0,0,0.85)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 20,
          }}
          onClick={() => setRequestModalOpen(false)}
        >
          <div
            style={{
              background: C.surface,
              border: `1px solid ${C.border}`,
              borderRadius: 12,
              maxWidth: 520,
              width: "100%",
              maxHeight: "90vh",
              overflow: "auto",
              padding: "20px 22px",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: 18, letterSpacing: 2, color: C.accent, marginBottom: 12 }}>
              Request documents
            </div>
            <div style={{ fontSize: 12, color: C.muted, marginBottom: 16, lineHeight: 1.5 }}>
              One combined email. Required items that still need follow-up are preselected; add optional items as needed.
              A new applicant link is issued when you send (previous links stop working).
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
              {Object.entries(DOC_META).map(([key, dm]) => (
                <label key={key} style={{ display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer", fontSize: 13, color: C.text }}>
                  <input
                    type="checkbox"
                    checked={!!requestDocSelection[key]}
                    onChange={(e) =>
                      setRequestDocSelection((prev) => ({ ...prev, [key]: e.target.checked }))
                    }
                  />
                  <span>
                    <strong>{dm.label}</strong>
                    {dm.required ? <span style={{ color: C.red, fontSize: 10, marginLeft: 6 }}>REQUIRED</span> : null}
                  </span>
                </label>
              ))}
            </div>
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", marginBottom: 4 }}>Email subject</div>
              <input
                value={requestSubject}
                onChange={(e) => setRequestSubject(e.target.value)}
                style={{ ...ri, width: "100%", boxSizing: "border-box" }}
              />
            </div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", marginBottom: 4 }}>Email body</div>
              <textarea
                value={requestBody}
                onChange={(e) => setRequestBody(e.target.value)}
                rows={8}
                style={{
                  width: "100%",
                  boxSizing: "border-box",
                  ...ri,
                  resize: "vertical",
                  minHeight: 140,
                }}
              />
            </div>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button
                type="button"
                onClick={() => setRequestModalOpen(false)}
                style={{
                  padding: "10px 18px",
                  borderRadius: 8,
                  border: `1px solid ${C.border}`,
                  background: "transparent",
                  color: C.muted,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void sendDocumentRequest()}
                disabled={requestSending}
                style={{
                  padding: "10px 18px",
                  borderRadius: 8,
                  border: "none",
                  background: C.accent,
                  color: "#000",
                  fontWeight: 700,
                  cursor: requestSending ? "wait" : "pointer",
                }}
              >
                {requestSending ? "Sending…" : "Send email"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div style={{ background: C.surface, borderBottom: `2px solid ${C.accent}`, padding: "0 28px", position: "sticky", top: 0, zIndex: 100 }}>
        <div style={{ maxWidth: 1060, margin: "0 auto", height: 64, display: "flex", alignItems: "center", gap: 14 }}>
          <button
            onClick={() => navigate("/operations/driver-onboarding-review")}
            style={{ background: "none", border: "none", cursor: "pointer", color: C.muted, fontSize: 13, display: "flex", alignItems: "center", gap: 4, padding: "6px 0", flexShrink: 0 }}
          >
            ← Back
          </button>
          <div style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: 22, letterSpacing: 3, color: C.accent, flexShrink: 0 }}>
            FLEET<span style={{ color: C.text }}>PRO</span>
          </div>
          <div style={{ width: 1, height: 26, background: C.border }} />
          <div style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: 19, letterSpacing: 2, color: C.text, whiteSpace: "nowrap" }}>
              {[application.first_name, p.middle_name, application.last_name].filter(Boolean).join(" ") || "Unnamed applicant"}
            </span>
            <StatusBadge status={application.status} />
            {showDriverSetupTabs && (
              <div style={{ display: "inline-flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                <DriverSetupTabBtn active={driverSetupTab === "driver"} onClick={() => setDriverSetupTab("driver")}>
                  Driver setup
                </DriverSetupTabBtn>
                <DriverSetupTabBtn active={driverSetupTab === "compensation"} onClick={() => setDriverSetupTab("compensation")}>
                  Compensation
                </DriverSetupTabBtn>
              </div>
            )}
            <span style={{ fontSize: 11, color: C.muted2 }}>{application.application_type || "DRIVER"}</span>
            <span style={{ fontSize: 11, color: C.muted2 }}>#{application.id}</span>
          </div>
          {isSubmitted && (
            <div style={{ display: "flex", gap: 8, width: 260, flexShrink: 0 }}>
              <Btn
                label="APPROVE"
                variant="approve"
                onClick={approve}
                loading={actionLoading}
                disabled={approveCombinedBlocked}
                title={
                  approveCombinedBlocked
                    ? (approveReadiness?.detail ?? "Complete Driver and Compensation setup on this page before approving.")
                    : undefined
                }
              />
              <Btn label="REJECT" variant="reject" onClick={() => setShowReject((current) => !current)} disabled={actionLoading} />
            </div>
          )}
        </div>
      </div>

      <div style={{ maxWidth: 1060, margin: "0 auto", padding: "24px 20px 80px" }}>
        {application.status === "REJECTED" && application.rejection_reason && (
          <div style={{ background: "rgba(232,56,13,0.08)", border: `1px solid ${C.red}44`, borderRadius: 10, padding: "14px 18px", marginBottom: 16 }}>
            <div style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: 12, letterSpacing: 2, color: C.red, marginBottom: 4 }}>Rejection Reason</div>
            <div style={{ fontSize: 13, color: "#fca5a5", lineHeight: 1.6 }}>{application.rejection_reason}</div>
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 10, alignItems: "start" }}>
          <div>
            {reviewWorkspaceOpen && reviewDraft && (
              <Panel title="Admin · Review corrections" icon="✏️" defaultOpen>
                <div style={{ fontSize: 12, color: C.muted2, lineHeight: 1.55, marginBottom: 14 }}>
                  Correct structured fields before or after approval. Uploaded files, agreements, work history, and
                  references stay as the applicant submitted them. A frozen snapshot is kept when the applicant first
                  submitted (or on first admin edit for older records); each save appends an audit entry.
                </div>
                <Grid>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>First name</span>
                    <input value={reviewDraft.first_name ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, first_name: e.target.value } : d))} style={ri} />
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Last name</span>
                    <input value={reviewDraft.last_name ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, last_name: e.target.value } : d))} style={ri} />
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Phone</span>
                    <input value={reviewDraft.phone ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, phone: e.target.value } : d))} style={ri} />
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Email</span>
                    <input value={reviewDraft.email ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, email: e.target.value } : d))} style={ri} />
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4, gridColumn: "1 / -1" }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Street</span>
                    <input value={reviewDraft.address_street ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, address_street: e.target.value } : d))} style={ri} />
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>City</span>
                    <input value={reviewDraft.address_city ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, address_city: e.target.value } : d))} style={ri} />
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Province / state</span>
                    <input value={reviewDraft.address_region ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, address_region: e.target.value } : d))} style={ri} />
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Postal</span>
                    <input value={reviewDraft.address_postal ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, address_postal: e.target.value } : d))} style={ri} />
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>ZIP</span>
                    <input value={reviewDraft.zip_code ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, zip_code: e.target.value } : d))} style={ri} />
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Country</span>
                    <input value={reviewDraft.address_country ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, address_country: e.target.value } : d))} style={ri} />
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4, gridColumn: "1 / -1" }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Internal notes</span>
                    <input value={reviewDraft.notes ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, notes: e.target.value } : d))} style={ri} />
                  </label>
                </Grid>
                {isDriver && (
                  <>
                    <Divider />
                    <SectionLabel>License & CDL (structured)</SectionLabel>
                    <Grid>
                      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>License number</span>
                        <input value={reviewDraft.driver_license_number ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, driver_license_number: e.target.value } : d))} style={{ ...ri, fontFamily: "'Courier New', monospace" }} />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Issuing region</span>
                        <input value={reviewDraft.license_region ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, license_region: e.target.value } : d))} style={ri} />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Expiry</span>
                        <input type="date" value={reviewDraft.license_expiry ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, license_expiry: e.target.value } : d))} style={ri} />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Middle name</span>
                        <input value={reviewDraft.middle_name ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, middle_name: e.target.value } : d))} style={ri} />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Date of birth</span>
                        <input type="date" value={reviewDraft.date_of_birth ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, date_of_birth: e.target.value } : d))} style={ri} />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>License issue date</span>
                        <input type="date" value={reviewDraft.license_issue_date ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, license_issue_date: e.target.value } : d))} style={ri} />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>CDL class</span>
                        <input value={reviewDraft.cdl_class ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, cdl_class: e.target.value } : d))} style={ri} />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: 4, gridColumn: "1 / -1" }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Endorsements</span>
                        <input value={reviewDraft.endorsements ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, endorsements: e.target.value } : d))} style={ri} />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: 4, gridColumn: "1 / -1" }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Restrictions</span>
                        <input value={reviewDraft.restrictions ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, restrictions: e.target.value } : d))} style={ri} />
                      </label>
                      <label style={{ display: "flex", flexDirection: "column", gap: 4, gridColumn: "1 / -1" }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: C.muted, textTransform: "uppercase", letterSpacing: "0.1em" }}>Conditions</span>
                        <input value={reviewDraft.conditions ?? ""} onChange={(e) => setReviewDraft((d) => (d ? { ...d, conditions: e.target.value } : d))} style={ri} />
                      </label>
                    </Grid>
                  </>
                )}
                <div style={{ marginTop: 16, display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
                  <button
                    type="button"
                    onClick={() => void saveReviewCorrections()}
                    disabled={reviewSaving}
                    style={{
                      padding: "10px 18px",
                      borderRadius: 8,
                      border: "none",
                      background: C.accent,
                      color: "#0d0e11",
                      fontWeight: 700,
                      fontSize: 12,
                      cursor: reviewSaving ? "wait" : "pointer",
                    }}
                  >
                    {reviewSaving ? "Saving…" : "Save corrections"}
                  </button>
                  {application.status === "APPROVED" && (
                    <span style={{ fontSize: 11, color: C.muted }}>Saving also refreshes the linked person / driver profile from corrected values.</span>
                  )}
                </div>
                {(application.intake_submitted_snapshot && Object.keys(application.intake_submitted_snapshot).length > 0) || (application.intake_review_audit && application.intake_review_audit.length > 0) ? (
                  <div style={{ marginTop: 18, display: "flex", flexDirection: "column", gap: 10 }}>
                    {application.intake_submitted_snapshot && Object.keys(application.intake_submitted_snapshot).length > 0 && (
                      <details style={{ fontSize: 12, color: C.muted2 }}>
                        <summary style={{ cursor: "pointer", color: C.muted }}>Original submission snapshot (frozen JSON)</summary>
                        <pre style={{ marginTop: 8, padding: 10, background: C.bg, borderRadius: 8, overflow: "auto", maxHeight: 220, fontSize: 11, color: C.text }}>
                          {JSON.stringify(application.intake_submitted_snapshot, null, 2)}
                        </pre>
                      </details>
                    )}
                    {application.intake_review_audit && application.intake_review_audit.length > 0 && (
                      <details style={{ fontSize: 12, color: C.muted2 }}>
                        <summary style={{ cursor: "pointer", color: C.muted }}>Review edit audit ({application.intake_review_audit.length})</summary>
                        <ul style={{ margin: "8px 0 0", paddingLeft: 18, lineHeight: 1.5 }}>
                          {application.intake_review_audit.slice(-8).map((row, i) => (
                            <li key={i}>
                              {(row.at || "").replace("T", " ").slice(0, 19)} — user #{row.by_user_id ?? "?"}{" "}
                              {Array.isArray(row.changed_keys) && row.changed_keys.length > 0
                                ? `(${row.changed_keys.join(", ")})`
                                : ""}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </div>
                ) : null}
              </Panel>
            )}
            {isDriver && (
            <Panel title="Step 1 — Driver's License" icon="🪪">
              <Grid>
                <Field label="License Number" value={fmt(application.driver_license_number)} mono />
                <Field label="Issuing Region" value={fmt(application.license_region)} />
                <Field label="Expiry Date" value={fmtDate(application.license_expiry)} />
                <Field label="Issue Date" value={fmtDate(p.license_issue_date)} />
                <Field label="CDL Class" value={p.cdl_class ? <Tag label={`Class ${p.cdl_class}`} variant="orange" /> : "—"} />
                <Field label="Endorsements" value={fmt(p.endorsements)} />
                <Field label="Restrictions" value={fmt(p.restrictions)} />
                <Field label="Conditions" value={fmt(p.conditions)} />
              </Grid>
              {(p.files?.CDL_FRONT || p.files?.CDL_BACK) && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: 11, letterSpacing: 2, color: C.muted, marginBottom: 10 }}>License Images</div>
                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                    {p.files.CDL_FRONT && (
                      <DlViewCard
                        label="Front"
                        meta={p.files.CDL_FRONT}
                        applicationId={application.id}
                        onView={handleViewFile}
                      />
                    )}
                    {p.files.CDL_BACK && (
                      <DlViewCard
                        label="Back"
                        meta={p.files.CDL_BACK}
                        applicationId={application.id}
                        onView={handleViewFile}
                      />
                    )}
                  </div>
                </div>
              )}
            </Panel>
            )}

            <Panel title={isDriver ? "Step 2 — Personal Information" : "Contact & Address"} icon="👤">
              {isDriver ? (
                <>
                  <SectionLabel>Basic Info</SectionLabel>
                  <Grid>
                    <Field label="First Name" value={fmt(application.first_name)} />
                    <Field label="Middle Name" value={fmt(p.middle_name)} />
                    <Field label="Last Name" value={fmt(application.last_name)} />
                    <Field label="Date of Birth" value={fmtDate(p.date_of_birth)} />
                    <Field label="SSN" value={last4(p.ssn)} mono />
                    <Field label="Nationality" value={fmt(p.nationality)} />
                    <Field label="Sex" value={fmt(p.sex)} />
                    <Field label="Height" value={fmt(p.height)} />
                  </Grid>
                  <Divider />
                  <SectionLabel>Contact & Address</SectionLabel>
                </>
              ) : (
                <>
                  <SectionLabel>Name</SectionLabel>
                  <Grid>
                    <Field label="First Name" value={fmt(application.first_name)} />
                    <Field label="Last Name" value={fmt(application.last_name)} />
                  </Grid>
                  <Divider />
                  <SectionLabel>Contact & Address</SectionLabel>
                </>
              )}
              <Grid>
                <Field label="Email" value={fmt(application.email)} />
                <Field label="Phone" value={fmt(application.phone)} mono />
                <Field label="Street" value={fmt(application.address_street)} />
                <Field label="City" value={fmt(application.address_city)} />
                <Field label="Province/State" value={fmt(application.address_region)} />
                <Field label="Postal Code" value={fmt(application.address_postal)} mono />
                <Field label="ZIP Code" value={fmt(application.zip_code)} mono />
                <Field label="Country" value={fmt(application.address_country)} />
              </Grid>
              {isDriver && (
              <>
              <Divider />
              <SectionLabel>Driving Background</SectionLabel>
              <Grid>
                <Field label="CDL Experience" value={fmt(p.years_experience)} />
                <Field label="Total Miles" value={fmt(p.total_miles)} />
                <Field label="Equipment Types" value={fmt(p.equipment_types)} wide />
                <Field label="DOT Medical Expiry" value={fmtDate(p.dot_medical_card_expiry)} />
                <Field label="Accidents (3yr)" value={yesNoTag(p.accidents_last_3_years)} />
                <Field label="Violations (3yr)" value={yesNoTag(p.violations_last_3_years)} />
              </Grid>
              <Divider />
              <SectionLabel>Emergency Contact</SectionLabel>
              <Grid>
                <Field label="Name" value={fmt(p.emergency_contact_name)} />
                <Field label="Relationship" value={fmt(p.emergency_contact_relationship)} />
                <Field label="Phone" value={fmt(p.emergency_contact_phone)} mono />
              </Grid>
              </>
              )}
            </Panel>

            {isDriver && (
            <>
            <Panel title={`Step 3 — Work History (${p.jobs?.length ?? 0} employers)`} icon="🏢">
              {(p.jobs?.length ?? 0) > 0
                ? p.jobs!.map((e, i) => <WorkCard key={i} e={e} i={i} />)
                : <div style={{ fontSize: 13, color: C.muted2, padding: "6px 0" }}>No employment history recorded.</div>}
            </Panel>

            <Panel title={`Step 3 — Professional References (${p.refs?.length ?? 0})`} icon="👥">
              {(p.refs?.length ?? 0) > 0
                ? p.refs!.map((e, i) => <RefCard key={i} e={e} i={i} />)
                : <div style={{ fontSize: 13, color: C.muted2, padding: "6px 0" }}>No references recorded.</div>}
            </Panel>

            <Panel
              title="Step 4 — Uploaded Documents"
              icon="📁"
              headerRight={
                isSubmitted || application.status === "APPROVED" ? (
                  <button
                    type="button"
                    onClick={() => openRequestDocumentsModal()}
                    style={{
                      fontFamily: "'Bebas Neue', sans-serif",
                      fontSize: 13,
                      letterSpacing: "0.08em",
                      padding: "8px 14px",
                      borderRadius: 8,
                      border: `1px solid ${C.accent}`,
                      background: `linear-gradient(135deg, rgba(245,166,35,0.2), rgba(245,166,35,0.08))`,
                      color: C.accent,
                      cursor: "pointer",
                      whiteSpace: "nowrap",
                    }}
                  >
                    Request documents
                  </button>
                ) : null
              }
            >
              <DocsGrid
                docs={p.documents}
                applicationId={application.id}
                onViewFile={handleViewFile}
                canAdminAct={isSubmitted || application.status === "APPROVED"}
                onAdminUpload={async (docType, file) => {
                  await adminUploadPersonApplicationDocument({
                    applicationId: application.id,
                    docType,
                    file,
                  });
                  await reloadApplication();
                  showNotice("success", "Document uploaded.");
                }}
                onAcceptToggle={async (docType, accepted) => {
                  await setPersonApplicationDocumentAccepted({
                    applicationId: application.id,
                    docType,
                    accepted,
                  });
                  await reloadApplication();
                  showNotice("success", accepted ? "Marked accepted." : "Acceptance cleared.");
                }}
              />
            </Panel>

            <Panel title="Step 4 — Agreements & Certifications" icon="✍️">
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {[
                  { value: p.agree_info_accurate, label: "Certified all information is accurate and complete" },
                  { value: p.agree_background_check, label: "Authorized company to run background / MVR / PSP checks" },
                  { value: p.agree_dot_compliance, label: "Agreed to comply with DOT regulations and company policies" },
                ].map((a, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{ fontSize: 17 }}>{a.value ? "✅" : "⬜"}</span>
                    <span style={{ fontSize: 13, color: a.value ? C.text : C.muted }}>{a.label}</span>
                  </div>
                ))}
              </div>
            </Panel>
            </>
            )}

            {application.notes && (
              <Panel title="Internal Notes" icon="📝">
                <div style={{ fontSize: 13, color: C.text, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{application.notes}</div>
              </Panel>
            )}
          </div>

          <div style={{ position: "sticky", top: 76 }}>
            <div style={{ background: C.surface, border: `1px solid ${cfg.color}44`, borderRadius: 12, padding: "16px 18px", marginBottom: 10, boxShadow: `0 0 28px ${cfg.glow}` }}>
              <div style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: 12, letterSpacing: 2, color: C.muted, marginBottom: 10 }}>Application Status</div>
              <div style={{ marginBottom: 14 }}><StatusBadge status={application.status} /></div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <Field label="Application ID" value={`#${application.id}`} mono />
                <Field label="Application Type" value={fmt(application.application_type) || "DRIVER"} />
                <Field label="Requested Role" value={fmt(application.requested_role_code) || "DRIVER"} />
                <Field label="Source" value={fmt(application.source)} />
                <Field label="Person ID" value={application.person_id ? `#${application.person_id}` : "—"} mono />
                <Field label="Created" value={fmtDT(application.created_at)} />
                <Field label="Submitted" value={fmtDT(application.submitted_at)} />
                <Field label="Last Updated" value={fmtDT(application.updated_at)} />
                <Field label="Setup status" value={fmt(application.setup_status) || "—"} mono />
              </div>
            </div>

            {showCombinedSetupChrome && !application.person_id && application.status === "SUBMITTED" && (
              <div
                style={{
                  background: C.surface,
                  border: `1px solid ${C.border}`,
                  borderRadius: 12,
                  padding: "14px 16px",
                  marginBottom: 10,
                  fontSize: 12,
                  color: C.muted2,
                  lineHeight: 1.5,
                }}
              >
                Linking this application to a tenant person record so Driver setup and Compensation can be saved
                (combined onboarding mode).
              </div>
            )}

            {showDriverSetupTabs && (
              <>
                {driverSetupTab === "driver" && (
                  <DriverPersonExtensionAdminPanel
                    key={`dpe-${application.person_id}-${application.status}`}
                    mode="onboarding"
                    personId={application.person_id!}
                    editable={driverConfigurationEditable}
                    onAfterPersist={bumpApproveReadiness}
                  />
                )}
                {driverSetupTab === "compensation" && (
                  <DriverCompensationSetupAdminPanel
                    key={`dcs-${application.id}-${application.person_id}`}
                    mode="application"
                    applicationId={application.id}
                    editable={driverConfigurationEditable}
                    onAfterPersist={bumpApproveReadiness}
                  />
                )}
              </>
            )}

            {(application.reviewed_at || application.reviewed_by_user_id || application.approved_at || application.approved_by_user_id) && (
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: "16px 18px", marginBottom: 10 }}>
                <div style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: 12, letterSpacing: 2, color: C.muted, marginBottom: 10 }}>Review Details</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <Field label="Reviewed At" value={fmtDT(application.reviewed_at)} />
                  <Field label="Reviewed By (ID)" value={application.reviewed_by_user_id ? `#${application.reviewed_by_user_id}` : "—"} mono />
                  <Field label="Approved At" value={fmtDT(application.approved_at)} />
                  <Field label="Approved By (ID)" value={application.approved_by_user_id ? `#${application.approved_by_user_id}` : "—"} mono />
                </div>
              </div>
            )}

            <div style={{ background: "rgba(245,166,35,0.06)", border: `1px solid ${C.accent}44`, borderRadius: 12, padding: "16px 18px" }}>
              <div style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: 13, letterSpacing: 2, color: C.accent, marginBottom: 6 }}>Review Flow</div>
              <div style={{ fontSize: 12, color: C.muted, lineHeight: 1.6, marginBottom: isSubmitted ? 14 : 0 }}>
                `PersonApplication` is now the canonical admin review object. Legacy `DriverOnboardingSubmission` approval remains in place temporarily for compatibility only.
              </div>
              {approveCombinedBlocked && approveReadiness?.detail && (
                <div
                  style={{
                    fontSize: 12,
                    color: "#fca5a5",
                    background: "rgba(232,56,13,0.12)",
                    border: `1px solid ${C.red}44`,
                    borderRadius: 8,
                    padding: "10px 12px",
                    marginBottom: 12,
                    lineHeight: 1.45,
                  }}
                >
                  <strong style={{ color: C.text }}>Approve is blocked:</strong> {approveReadiness.detail} You can still save review corrections and setup cards.
                </div>
              )}
              {application.status === "APPROVED" && personSetupUiMode === "segmented" && (application.setup_status ?? "") === "pending_downstream" && (
                <div style={{ fontSize: 12, color: C.muted2, marginBottom: 12, lineHeight: 1.5 }}>
                  <strong style={{ color: C.text }}>Downstream setup pending.</strong> HR/Payroll will finish onboarding later; this page does not own those fields in segmented mode.
                </div>
              )}
              {showMarkOnboardingComplete && (
                <div style={{ marginBottom: 12 }}>
                  <Btn
                    label="MARK ONBOARDING COMPLETE"
                    variant="approve"
                    onClick={() => void markOnboardingComplete()}
                    loading={onboardingCompleteLoading}
                    title="Confirms required combined-mode setup is finished (separate from Approve)."
                  />
                </div>
              )}
              {isSubmitted && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <Btn
                    label="APPROVE APPLICATION"
                    variant="approve"
                    onClick={approve}
                    loading={actionLoading}
                    disabled={approveCombinedBlocked}
                    title={
                      approveCombinedBlocked
                        ? (approveReadiness?.detail ?? "Complete Driver and Compensation setup before approving.")
                        : undefined
                    }
                  />
                  <Btn label={showReject ? "CANCEL REJECT" : "REJECT APPLICATION"} variant={showReject ? "ghost" : "reject"} onClick={() => setShowReject((current) => !current)} disabled={actionLoading} />
                  {showReject && (
                    <>
                      <textarea
                        value={rejectReason}
                        onChange={(event) => setRejectReason(event.target.value)}
                        placeholder="Reason the applicant should see"
                        rows={4}
                        style={{
                          width: "100%",
                          background: C.surf2,
                          border: `1px solid ${C.border}`,
                          borderRadius: 8,
                          padding: "10px 12px",
                          fontSize: 13,
                          color: C.text,
                          fontFamily: "inherit",
                          resize: "vertical",
                          outline: "none",
                          boxSizing: "border-box",
                        }}
                      />
                      <Btn
                        label="CONFIRM REJECT"
                        variant="reject"
                        onClick={reject}
                        disabled={!rejectReason.trim()}
                        loading={actionLoading}
                      />
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
