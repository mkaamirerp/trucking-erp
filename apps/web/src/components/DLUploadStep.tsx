import { useEffect, useMemo, useState } from "react";

type Side = "front" | "back";
type UploadState = "IDLE" | "UPLOADING" | "SCANNING" | "SUCCESS" | "FAILED";

type Props = {
  frontPreviewUrl: string | null;
  backPreviewUrl: string | null;
  frontState: UploadState;
  backState: UploadState;
  frontMessage?: string;
  backMessage?: string;
  onUploadSide: (side: Side, file: File) => Promise<boolean> | boolean;
};

type LocalPreviewState = { front: string | null; back: string | null };

export default function DLUploadStep({
  frontPreviewUrl,
  backPreviewUrl,
  frontState,
  backState,
  frontMessage = "",
  backMessage = "",
  onUploadSide,
}: Props) {
  const [localPreview, setLocalPreview] = useState<LocalPreviewState>({ front: null, back: null });

  useEffect(() => {
    return () => {
      if (localPreview.front) URL.revokeObjectURL(localPreview.front);
      if (localPreview.back) URL.revokeObjectURL(localPreview.back);
    };
  }, [localPreview.back, localPreview.front]);

  useEffect(() => {
    if (!frontPreviewUrl || !localPreview.front) return;
    URL.revokeObjectURL(localPreview.front);
    setLocalPreview((prev) => ({ ...prev, front: null }));
  }, [frontPreviewUrl, localPreview.front]);

  useEffect(() => {
    if (!backPreviewUrl || !localPreview.back) return;
    URL.revokeObjectURL(localPreview.back);
    setLocalPreview((prev) => ({ ...prev, back: null }));
  }, [backPreviewUrl, localPreview.back]);

  const frontPreview = useMemo(() => {
    if (frontState === "SUCCESS") return frontPreviewUrl;
    if (frontState === "FAILED") return frontPreviewUrl;
    if (frontState === "UPLOADING" || frontState === "SCANNING") return localPreview.front ?? frontPreviewUrl;
    return frontPreviewUrl ?? localPreview.front;
  }, [frontPreviewUrl, frontState, localPreview.front]);

  const backPreview = useMemo(() => {
    if (backState === "SUCCESS") return backPreviewUrl;
    if (backState === "FAILED") return backPreviewUrl;
    if (backState === "UPLOADING" || backState === "SCANNING") return localPreview.back ?? backPreviewUrl;
    return backPreviewUrl ?? localPreview.back;
  }, [backPreviewUrl, backState, localPreview.back]);
  const busy =
    frontState === "UPLOADING" ||
    frontState === "SCANNING" ||
    backState === "UPLOADING" ||
    backState === "SCANNING";
  const canReview = Boolean(frontPreview && backPreview);

  const handleFileSelect = async (side: Side, file: File) => {
    const url = URL.createObjectURL(file);
    setLocalPreview((prev) => {
      const old = side === "front" ? prev.front : prev.back;
      if (old) URL.revokeObjectURL(old);
      return side === "front" ? { ...prev, front: url } : { ...prev, back: url };
    });
    await onUploadSide(side, file);
  };

  const promptReplacementFile = (side: Side) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.capture = "environment";
    input.onchange = () => {
      const file = input.files?.[0];
      if (file) void handleFileSelect(side, file);
    };
    input.click();
  };

  const card = useMemo(
    () =>
      ({
        background: "var(--trk-surface)",
        border: "1px solid var(--trk-border)",
        borderRadius: 12,
        padding: 16,
        cursor: "pointer",
      }) as const,
    [],
  );

  const uploadStage = (
    side: Side,
    title: string,
    subtitle: string,
    message: string,
    state: UploadState,
  ) => {
    const stageBusy = state === "UPLOADING" || state === "SCANNING";
    return (
      <div style={card}>
        <div
          style={{
            border: "2px dashed",
            borderColor: stageBusy ? "var(--trk-heading)" : "var(--trk-border)",
            borderRadius: 14,
            minHeight: 320,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "0.9rem",
            color: "var(--trk-text-muted)",
            cursor: stageBusy ? "default" : "pointer",
            position: "relative",
            overflow: "hidden",
            background: "var(--trk-bg)",
            textAlign: "center",
            padding: 28,
          }}
        >
          {stageBusy ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, color: "var(--trk-text)" }}>
              <div
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: "50%",
                  border: "2px solid var(--trk-border-strong)",
                  borderTopColor: "var(--trk-heading)",
                  animation: "spin 0.7s linear infinite",
                }}
              />
              <div style={{ fontWeight: 700 }}>{message || "Saving your licence..."}</div>
            </div>
          ) : (
            <div>
              <div
                style={{
                  fontSize: "0.78rem",
                  fontWeight: 800,
                  textTransform: "uppercase",
                  letterSpacing: "0.12em",
                  color: "var(--trk-heading)",
                  marginBottom: 10,
                }}
              >
                {side === "front" ? "Step 1" : "Step 2"}
              </div>
              <div style={{ color: "var(--trk-text)", fontSize: "1.5rem", fontWeight: 800, marginBottom: 10 }}>{title}</div>
              <div style={{ color: "var(--trk-text-muted)", maxWidth: 420, lineHeight: 1.6 }}>{subtitle}</div>
            </div>
          )}
          {!stageBusy && (
            <input
              type="file"
              accept="image/*"
              capture="environment"
              style={{
                position: "absolute",
                inset: 0,
                opacity: 0,
                cursor: "pointer",
                width: "100%",
                height: "100%",
                borderRadius: 14,
              }}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleFileSelect(side, file);
                event.currentTarget.value = "";
              }}
            />
          )}
        </div>
      </div>
    );
  };

  if (!frontPreview) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {uploadStage(
          "front",
          "Upload front of driver licence",
          "Take or choose a clear photo of the front of your licence.",
          frontMessage,
          frontState,
        )}
        {frontState === "FAILED" && (
          <p style={{ fontSize: "0.85rem", color: "var(--trk-danger)" }}>{frontMessage || "Upload failed. Please try again."}</p>
        )}
      </div>
    );
  }

  if (!backPreview) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ ...card, textAlign: "center", cursor: "default" }}>
          <div
            style={{
              fontSize: "0.78rem",
              fontWeight: 800,
              textTransform: "uppercase",
              letterSpacing: "0.12em",
              color: "var(--trk-success)",
              marginBottom: 8,
            }}
          >
            Front saved
          </div>
          <div style={{ color: "var(--trk-text-muted)", lineHeight: 1.6 }}>Continue with the back side for PDF417 barcode reading.</div>
          <button
            type="button"
            onClick={() => promptReplacementFile("front")}
            disabled={busy}
            style={{
              marginTop: 14,
              background: "none",
              border: "1px solid var(--trk-border)",
              borderRadius: 6,
              color: "var(--trk-heading)",
              padding: "9px 18px",
              fontSize: "0.8rem",
              fontWeight: 700,
              cursor: !busy ? "pointer" : "default",
              opacity: busy ? 0.6 : 1,
            }}
          >
            Re-upload front
          </button>
        </div>
        {uploadStage(
          "back",
          "Upload back of driver licence",
          "Take or choose a clear photo of the back. The barcode will be read after upload.",
          backMessage,
          backState,
        )}
        {backState === "FAILED" && (
          <p style={{ fontSize: "0.85rem", color: "var(--trk-danger)" }}>{backMessage || "Upload failed. Please try again."}</p>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {canReview && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 18 }}>
          {(
            [
              ["front", "Front preview", frontPreview],
              ["back", "Back preview", backPreview],
            ] as const
          ).map(([side, label, preview]) => (
            <div
              key={side}
              style={{
                ...card,
                border: "1px solid rgba(34,197,94,0.45)",
                boxShadow: "0 0 0 1px rgba(34,197,94,0.12) inset",
                cursor: "default",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <div
                  style={{
                    fontSize: "0.72rem",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                    color: "var(--trk-success)",
                  }}
                >
                  {label}
                </div>
                <div style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--trk-success)" }}>READY</div>
              </div>
              <div
                style={{
                  borderRadius: 12,
                  overflow: "hidden",
                  border: "2px solid rgba(34,197,94,0.45)",
                  background: "var(--trk-bg)",
                  aspectRatio: "8 / 5",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {preview && (
                  <img src={preview} alt={`${label}`} style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }} />
                )}
              </div>
              <button
                type="button"
                onClick={() => promptReplacementFile(side)}
                disabled={busy}
                style={{
                  marginTop: 10,
                  width: "100%",
                  background: "none",
                  border: "1px solid var(--trk-border)",
                  borderRadius: 6,
                  color: "var(--trk-heading)",
                  padding: "8px 0",
                  fontSize: "0.78rem",
                  fontWeight: 700,
                  cursor: busy ? "default" : "pointer",
                  opacity: busy ? 0.6 : 1,
                }}
              >
                Re-upload {side}
              </button>
            </div>
          ))}
        </div>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
