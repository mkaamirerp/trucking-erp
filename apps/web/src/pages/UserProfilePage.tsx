import { useMe } from "../hooks/useMe";
import { useTheme, type Theme } from "../contexts/ThemeContext";

// ─── Theme option definitions ─────────────────────────────────────────────────
// bg and accent are the swatch preview colors only — hardcoded intentionally so
// they always show the target theme regardless of which theme is currently active.

interface ThemeOption {
  value: Theme;
  label: string;
  bg: string;
  accent: string;
}

const THEME_OPTIONS: ThemeOption[] = [
  { value: "dark",      label: "Dark",      bg: "#0D0F14", accent: "#F59E0B" },
  { value: "dark-blue", label: "Dark blue", bg: "#0F1525", accent: "#F59E0B" },
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "11px 0",
        borderBottom: "1px solid var(--trk-border)",
      }}
    >
      <span style={{ color: "var(--trk-text-muted)", fontSize: 13 }}>{label}</span>
      <span style={{ color: "var(--trk-text)", fontSize: 13, fontWeight: 500 }}>{value}</span>
    </div>
  );
}

function ThemeCard({
  option,
  active,
  onSelect,
}: {
  option: ThemeOption;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      style={{
        flex: 1,
        padding: "14px 12px",
        borderRadius: 10,
        border: `2px solid ${active ? "#F59E0B" : "var(--trk-border)"}`,
        background: active ? "var(--trk-surface-2)" : "transparent",
        cursor: "pointer",
        textAlign: "left",
        transition: "border-color 0.15s, background 0.15s",
        outline: "none",
      }}
    >
      {/* Dual swatch: background colour + heading/accent colour */}
      <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 6,
            background: option.bg,
            border: "1px solid rgba(128,128,128,0.2)",
            flexShrink: 0,
          }}
        />
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 6,
            background: option.accent,
            flexShrink: 0,
          }}
        />
      </div>
      <span style={{ color: "var(--trk-text)", fontSize: 13, fontWeight: 500 }}>
        {option.label}
      </span>
    </button>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function UserProfilePage() {
  const { me } = useMe();
  const { theme, setTheme } = useTheme();

  const displayName =
    [me?.first_name, me?.last_name].filter(Boolean).join(" ") || "—";
  const role = me?.roles?.[0] ?? "—";

  return (
    <div style={{ padding: "32px 24px", maxWidth: 560, margin: "0 auto" }}>

      {/* ── Profile ─────────────────────────────────────────────── */}
      <section style={{ marginBottom: 40 }}>
        <h2
          style={{
            color: "var(--trk-heading)",
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            marginBottom: 12,
          }}
        >
          Profile
        </h2>
        <div
          style={{
            background: "var(--trk-surface)",
            border: "1px solid var(--trk-border)",
            borderRadius: 12,
            padding: "0 20px",
          }}
        >
          <InfoRow label="Name"      value={displayName} />
          <InfoRow label="Email"     value={me?.email ?? "—"} />
          <InfoRow label="Role"      value={role} />
          <InfoRow label="Workspace" value={me?.tenant_slug ?? "—"} />
          {/* Remove the bottom border on the last row */}
          <div style={{ padding: "11px 0" }}>
            <span style={{ color: "var(--trk-text-muted)", fontSize: 13 }}>Tenant ID</span>
            <span
              style={{
                float: "right",
                color: "var(--trk-text)",
                fontSize: 13,
                fontWeight: 500,
              }}
            >
              {me?.tenant_id ?? "—"}
            </span>
          </div>
        </div>
      </section>

      {/* ── Appearance ──────────────────────────────────────────── */}
      <section>
        <h2
          style={{
            color: "var(--trk-heading)",
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            marginBottom: 12,
          }}
        >
          Appearance
        </h2>
        <div
          style={{
            background: "var(--trk-surface)",
            border: "1px solid var(--trk-border)",
            borderRadius: 12,
            padding: 20,
          }}
        >
          <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
            {THEME_OPTIONS.map((opt) => (
              <ThemeCard
                key={opt.value}
                option={opt}
                active={theme === opt.value}
                onSelect={() => setTheme(opt.value)}
              />
            ))}
          </div>
          <p style={{ color: "var(--trk-text-muted)", fontSize: 12, margin: 0 }}>
            More themes coming soon.
          </p>
        </div>
      </section>

    </div>
  );
}
