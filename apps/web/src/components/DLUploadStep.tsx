import { useEffect, useMemo, useState } from "react";

import DLCornerTool from "./DLCornerTool";
import { processDriverLicenseFile } from "../core/driverLicensePreprocessor";

type Side = "front" | "back";
type UploadState = "IDLE" | "UPLOADING" | "SCANNING" | "SUCCESS" | "FAILED";

type Props = {
  frontPreviewUrl: string | null;
  backPreviewUrl: string | null;
  frontState: UploadState;
  backState: UploadState;
  frontMessage?: string;
  backMessage?: string;
  onUploadSide: (side: Side, rawFile: File, processedBlob?: Blob, preprocessMetadata?: Record<string, unknown>) => Promise<boolean> | boolean;
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
  const [frontFile, setFrontFile] = useState<File | null>(null);
  const [backFile, setBackFile] = useState<File | null>(null);
  const [activeSide, setActiveSide] = useState<Side | null>(null);
  const [manualSide, setManualSide] = useState<Side | null>(null);
  const [processingAuto, setProcessingAuto] = useState(false);
  const [autoMessage, setAutoMessage] = useState("");
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

  const frontPreview = frontPreviewUrl ?? localPreview.front;
  const backPreview = backPreviewUrl ?? localPreview.back;
  const busy = frontState === "UPLOADING" || frontState === "SCANNING" || backState === "UPLOADING" || backState === "SCANNING" || processingAuto;
  const canReview = Boolean(frontPreview && backPreview);

  const handleFileSelect = (side: Side, file: File) => {
    const url = URL.createObjectURL(file);
    setLocalPreview((prev) => {
      const old = side === "front" ? prev.front : prev.back;
      if (old) URL.revokeObjectURL(old);
      return side === "front" ? { ...prev, front: url } : { ...prev, back: url };
    });
    if (side === "front") setFrontFile(file);
    else setBackFile(file);
    setManualSide(null);
    setActiveSide(side);
  };

  const handleAutoProcessAndUpload = async (side: Side) => {
    const file = side === "front" ? frontFile : backFile;
    if (!file) return;
    setProcessingAuto(true);
    setAutoMessage("Detecting card edges and straightening...");
    try {
      const result = await processDriverLicenseFile(file);
      if (result.status === "SUCCESS" && result.processedBlob) {
        setAutoMessage("Uploading original and processed image...");
        const saved = await onUploadSide(side, file, result.processedBlob, result.report as Record<string, unknown>);
        if (saved) {
          setActiveSide(null);
          setManualSide(null);
        }
        return;
      }
      setAutoMessage("");
      setManualSide(side);
    } finally {
      setProcessingAuto(false);
      setAutoMessage("");
    }
  };

  const handleManualConfirm = async (side: Side, blob: Blob) => {
    const file = side === "front" ? frontFile : backFile;
    if (!file) return;
    const manualFile = new File([blob], `${file.name.replace(/\.[^.]+$/, "")}_manual.jpg`, { type: "image/jpeg" });
    const saved = await onUploadSide(side, file, manualFile);
    if (saved) {
      setActiveSide(null);
      setManualSide(null);
    }
  };

  const promptReplacementFile = (side: Side) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.capture = "environment";
    input.onchange = () => {
      const file = input.files?.[0];
      if (file) handleFileSelect(side, file);
    };
    input.click();
  };

  const card = useMemo(() => ({
    background: "var(--trk-surface)",
    border: "1px solid var(--trk-border)",
    borderRadius: 12,
    padding: 16,
    cursor: "pointer",
  } as const), []);

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
              <div style={{ width: 38, height: 38, borderRadius: "50%", border: "2px solid var(--trk-border-strong)", borderTopColor: "var(--trk-heading)", animation: "spin 0.7s linear infinite" }} />
              <div style={{ fontWeight: 700 }}>{message || "Saving your licence..."}</div>
            </div>
          ) : (
            <div>
              <div style={{ fontSize: "0.78rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--trk-heading)", marginBottom: 10 }}>
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
              style={{ position: "absolute", inset: 0, opacity: 0, cursor: "pointer", width: "100%", height: "100%", borderRadius: 14 }}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) handleFileSelect(side, file);
                event.currentTarget.value = "";
              }}
            />
          )}
        </div>
      </div>
    );
  };

  if (manualSide && (manualSide === "front" ? frontFile : backFile)) {
    const file = manualSide === "front" ? frontFile! : backFile!;
    return (
      <div style={{ maxWidth: 980, margin: "0 auto" }}>
        <div style={{ marginBottom: 12, fontSize: "0.85rem", color: "var(--trk-warning, #fbbf24)" }}>
          Automatic straightening could not confirm all four edges. Adjust the corners manually below.
        </div>
        <DLCornerTool
          imageFile={file}
          label={manualSide === "front" ? "Front of Driver's Licence" : "Back of Driver's Licence"}
          confirmLabel={manualSide === "front" ? "Looks Good - Upload Front" : "Looks Good - Upload Back"}
          onConfirm={(blob) => void handleManualConfirm(manualSide, blob)}
          onCancel={() => setManualSide(null)}
        />
      </div>
    );
  }

  const reviewPanel = (side: Side, preview: string, label: string) => {
    const file = side === "front" ? frontFile : backFile;
    const state = side === "front" ? frontState : backState;
    const message = side === "front" ? frontMessage : backMessage;
    const stageBusy = state === "UPLOADING" || state === "SCANNING" || processingAuto;
    return (
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <div style={{ ...card, cursor: "default" }}>
          <div style={{ fontSize: "0.78rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--trk-heading)", marginBottom: 10 }}>
            {label}
          </div>
          <div style={{ borderRadius: 12, overflow: "hidden", border: "1px solid var(--trk-border)", background: "var(--trk-bg)", aspectRatio: "8 / 5", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 16 }}>
            <img src={preview} alt={`${side} preview`} style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }} />
          </div>
          <p style={{ fontSize: "0.85rem", color: "var(--trk-text-muted)", lineHeight: 1.6, marginBottom: 16 }}>
            Your original photo is preserved. TruckERP will detect the four card edges in your browser and upload a processed copy when geometry is confirmed.
          </p>
          {stageBusy && (
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, color: "var(--trk-text)" }}>
              <div style={{ width: 28, height: 28, borderRadius: "50%", border: "2px solid var(--trk-border-strong)", borderTopColor: "var(--trk-heading)", animation: "spin 0.7s linear infinite" }} />
              <span style={{ fontWeight: 700 }}>{autoMessage || message || "Processing..."}</span>
            </div>
          )}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={() => void handleAutoProcessAndUpload(side)}
              disabled={!file || stageBusy || busy}
              style={{ flex: 1, minWidth: 160, border: "none", borderRadius: 8, background: "var(--trk-heading)", color: "#fff", padding: "12px 18px", fontWeight: 800, fontSize: "0.85rem", cursor: !file || stageBusy || busy ? "default" : "pointer", opacity: !file || stageBusy || busy ? 0.6 : 1 }}
            >
              {side === "back" ? "Straighten & upload back" : "Straighten & upload front"}
            </button>
            <button
              type="button"
              onClick={() => file && setManualSide(side)}
              disabled={!file || stageBusy}
              style={{ border: "1px solid var(--trk-border)", borderRadius: 8, background: "transparent", color: "var(--trk-heading)", padding: "12px 18px", fontWeight: 700, fontSize: "0.85rem", cursor: !file || stageBusy ? "default" : "pointer" }}
            >
              Adjust corners manually
            </button>
          </div>
          {state === "FAILED" && (
            <p style={{ fontSize: "0.85rem", color: "var(--trk-danger)", marginTop: 12 }}>{message || "Upload failed. Please try again."}</p>
          )}
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  };

  if (activeSide === "front" && localPreview.front) {
    return reviewPanel("front", localPreview.front, "Front of driver's licence");
  }

  if (activeSide === "back" && localPreview.back) {
    return reviewPanel("back", localPreview.back, "Back of driver's licence");
  }

  if (!frontPreview) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {uploadStage("front", "Upload front of driver licence", "Take or choose a clear photo of the front. Edge detection runs in your browser; manual corner adjustment is available if needed.", frontMessage, frontState)}
        {frontState === "FAILED" && <p style={{ fontSize: "0.85rem", color: "var(--trk-danger)" }}>{frontMessage || "Upload failed. Please try again."}</p>}
      </div>
    );
  }

  if (!backPreview) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ ...card, textAlign: "center", cursor: "default" }}>
          <div style={{ fontSize: "0.78rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--trk-success)", marginBottom: 8 }}>
            Front saved
          </div>
          <div style={{ color: "var(--trk-text-muted)", lineHeight: 1.6 }}>
            The front original is on file. Continue with the back side for PDF417 barcode reading.
          </div>
          <button
            type="button"
            onClick={() => promptReplacementFile("front")}
            disabled={busy}
            style={{ marginTop: 14, background: "none", border: "1px solid var(--trk-border)", borderRadius: 6, color: "var(--trk-heading)", padding: "9px 18px", fontSize: "0.8rem", fontWeight: 700, cursor: !busy ? "pointer" : "default", opacity: busy ? 0.6 : 1 }}
          >
            Re-upload front
          </button>
        </div>
        {uploadStage("back", "Upload back of driver licence", "Automatic edge detection will straighten the card when all four edges are confirmed. Manual fallback is available.", backMessage, backState)}
        {backState === "FAILED" && <p style={{ fontSize: "0.85rem", color: "var(--trk-danger)" }}>{backMessage || "Upload failed. Please try again."}</p>}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {canReview && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 18 }}>
          <div style={{ ...card, border: "1px solid rgba(34,197,94,0.45)", boxShadow: "0 0 0 1px rgba(34,197,94,0.12) inset", cursor: "default" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--trk-success)" }}>Front preview</div>
              <div style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--trk-success)" }}>READY</div>
            </div>
            <div style={{ borderRadius: 12, overflow: "hidden", border: "2px solid rgba(34,197,94,0.45)", background: "var(--trk-bg)", aspectRatio: "8 / 5", display: "flex", alignItems: "center", justifyContent: "center" }}>
              {frontPreview && <img src={frontPreview} alt="Front preview" style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }} />}
            </div>
            <button type="button" onClick={() => promptReplacementFile("front")} disabled={busy} style={{ marginTop: 10, width: "100%", background: "none", border: "1px solid var(--trk-border)", borderRadius: 6, color: "var(--trk-heading)", padding: "8px 0", fontSize: "0.78rem", fontWeight: 700, cursor: busy ? "default" : "pointer", opacity: busy ? 0.6 : 1 }}>
              Re-upload front
            </button>
          </div>
          <div style={{ ...card, border: "1px solid rgba(34,197,94,0.45)", boxShadow: "0 0 0 1px rgba(34,197,94,0.12) inset", cursor: "default" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--trk-success)" }}>Back preview</div>
              <div style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--trk-success)" }}>READY</div>
            </div>
            <div style={{ borderRadius: 12, overflow: "hidden", border: "2px solid rgba(34,197,94,0.45)", background: "var(--trk-bg)", aspectRatio: "8 / 5", display: "flex", alignItems: "center", justifyContent: "center" }}>
              {backPreview && <img src={backPreview} alt="Back preview" style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }} />}
            </div>
            <button type="button" onClick={() => promptReplacementFile("back")} disabled={busy} style={{ marginTop: 10, width: "100%", background: "none", border: "1px solid var(--trk-border)", borderRadius: 6, color: "var(--trk-heading)", padding: "8px 0", fontSize: "0.78rem", fontWeight: 700, cursor: busy ? "default" : "pointer", opacity: busy ? 0.6 : 1 }}>
              Re-upload back
            </button>
          </div>
        </div>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
