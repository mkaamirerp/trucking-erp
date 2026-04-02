import { useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  approvePersonApplicationForAdmin,
  getAdminApplicationFileUrl,
  getPersonApplicationForAdmin,
  rejectPersonApplicationForAdmin,
  type ApplicantApplication,
} from "../api";

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

function Panel({ title, icon, children, defaultOpen = true }: {
  title: string;
  icon: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, overflow: "hidden", marginBottom: 10 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%",
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: "13px 18px",
          display: "flex",
          alignItems: "center",
          gap: 9,
          borderBottom: open ? `1px solid ${C.border}` : "none",
        }}
      >
        <span style={{ fontSize: 15 }}>{icon}</span>
        <span style={{ flex: 1, textAlign: "left", fontFamily: "'Bebas Neue', sans-serif", fontSize: 15, letterSpacing: "0.1em", color: C.text }}>
          {title}
        </span>
        <span style={{ color: C.muted, fontSize: 11, transform: open ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>▼</span>
      </button>
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
}: {
  label: ReactNode;
  variant: "approve" | "reject" | "ghost";
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
}) {
  const s = {
    approve: { background: `linear-gradient(135deg,${C.green},#27ae60)`, color: "#000", border: "none" },
    reject: { background: "transparent", color: C.red, border: `1.5px solid ${C.red}66` },
    ghost: { background: "transparent", color: C.muted, border: `1px solid ${C.border}` },
  }[variant];

  return (
    <button
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
}: {
  docs?: Record<string, IntakeDocMeta>;
  applicationId: number;
  onViewFile: (applicationId: number, fileId: string, filename?: string) => void;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
      {Object.entries(DOC_META).map(([key, meta]) => {
        const uploaded = docs?.[key];
        const fileId = uploaded?.storage_key || uploaded?.file_id;
        return (
          <div key={key} style={{ background: C.surf2, border: `1px solid ${uploaded ? `${C.green}55` : C.border}`, borderRadius: 10, padding: "13px 15px", display: "flex", alignItems: "flex-start", gap: 11 }}>
            <span style={{ fontSize: 20, flexShrink: 0 }}>{meta.icon}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: C.text, marginBottom: 5 }}>{meta.label}</div>
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                {meta.required ? <Tag label="Required" variant="red" /> : <Tag label="Optional" />}
                {uploaded ? <Tag label="Uploaded" variant="green" /> : <Tag label="Missing" variant={meta.required ? "red" : "default"} />}
              </div>
              {uploaded?.original_filename && (
                <div style={{ fontSize: 10, color: C.muted, marginTop: 5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {uploaded.original_filename}
                </div>
              )}
              {fileId && (
                <button
                  type="button"
                  onClick={() => onViewFile(applicationId, fileId, uploaded?.original_filename)}
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

  useEffect(() => {
    const load = async () => {
      if (!id) return;
      setLoading(true);
      setError(null);
      try {
        const data = await getPersonApplicationForAdmin(Number(id));
        setApplication(data);
      } catch (err: any) {
        setError(err?.message || "Unable to load application.");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [id]);

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

  const showNotice = (type: "success" | "error", message: string) => {
    setActionNotice({ type, message });
    window.setTimeout(() => {
      setActionNotice((current) => (current?.message === message ? null : current));
    }, 3500);
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
      setShowReject(false);
      setRejectReason("");
      showNotice("success", "Application approved.");
    } catch (err: any) {
      showNotice("error", err?.message || "Unable to approve application.");
    } finally {
      setActionLoading(false);
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
            <span style={{ fontSize: 11, color: C.muted2 }}>{application.application_type || "DRIVER"}</span>
            <span style={{ fontSize: 11, color: C.muted2 }}>#{application.id}</span>
          </div>
          {isSubmitted && (
            <div style={{ display: "flex", gap: 8, width: 260, flexShrink: 0 }}>
              <Btn label="APPROVE" variant="approve" onClick={approve} loading={actionLoading} />
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
              <Grid>
                <Field label="Email" value={fmt(application.email)} />
                <Field label="Phone" value={fmt(application.phone)} mono />
                <Field label="Street" value={fmt(application.address_street)} />
                <Field label="City" value={fmt(application.address_city)} />
                <Field label="Province/State" value={fmt(application.address_region)} />
                <Field label="Postal Code" value={fmt(application.address_postal)} mono />
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

            <Panel title="Step 4 — Uploaded Documents" icon="📁">
              <DocsGrid docs={p.documents} applicationId={application.id} onViewFile={handleViewFile} />
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
              </div>
            </div>

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
              {isSubmitted && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <Btn label="APPROVE APPLICATION" variant="approve" onClick={approve} loading={actionLoading} />
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
