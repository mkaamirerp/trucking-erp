import { useEffect, useState } from "react";
import QRCode from "react-qr-code";
import { getPersonApplicationByOnboardingToken, issueApplicantDlCaptureLink, type PersonApplication } from "../api";

type DlSide = "CDL_FRONT" | "CDL_BACK";

type Props = {
  onboardingToken: string;
  intake: Record<string, unknown>;
  disabled?: boolean;
  onApplicationUpdated: (app: PersonApplication) => void;
};

function dlPreprocessStatus(intake: Record<string, unknown>, side: DlSide): "MISSING" | "FAILED" | "PROCESSED" {
  const files = intake.files as Record<string, unknown> | undefined;
  const meta = files?.[side];
  if (!meta || typeof meta !== "object") return "MISSING";
  const status = (meta as { dl_preprocess_status?: string }).dl_preprocess_status;
  if (status === "PROCESSED") return "PROCESSED";
  if (status === "FAILED") return "FAILED";
  return "MISSING";
}

function sideStatusLabel(status: "MISSING" | "FAILED" | "PROCESSED"): string {
  if (status === "PROCESSED") return "✓ Received";
  if (status === "FAILED") return "Needs retry";
  return "Waiting...";
}

export default function DlPhoneCapturePanel({
  onboardingToken,
  intake,
  disabled = false,
  onApplicationUpdated,
}: Props) {
  const [captureLink, setCaptureLink] = useState<string | null>(null);
  const [issuing, setIssuing] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusIntake, setStatusIntake] = useState(intake);

  useEffect(() => {
    setStatusIntake(intake);
  }, [intake]);

  const frontStatus = dlPreprocessStatus(statusIntake, "CDL_FRONT");
  const backStatus = dlPreprocessStatus(statusIntake, "CDL_BACK");
  const bothProcessed = frontStatus === "PROCESSED" && backStatus === "PROCESSED";

  async function handleUsePhone() {
    if (issuing || disabled) return;
    setError(null);
    setIssuing(true);
    try {
      const resp = await issueApplicantDlCaptureLink(onboardingToken);
      setCaptureLink(resp.link);
    } catch (e: unknown) {
      const message = e instanceof Error && e.message ? e.message : "Could not create phone capture link.";
      setError(message);
    } finally {
      setIssuing(false);
    }
  }

  async function handleCheckStatus() {
    if (checking || disabled) return;
    setError(null);
    setChecking(true);
    try {
      const data = await getPersonApplicationByOnboardingToken(onboardingToken);
      const freshIntake = (data.intake_payload as Record<string, unknown>) || {};
      setStatusIntake(freshIntake);
      onApplicationUpdated(data);
    } catch (e: unknown) {
      const message = e instanceof Error && e.message ? e.message : "Could not refresh application status.";
      setError(message);
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="rounded-2xl border border-gray-700 bg-gray-800/40 p-5 space-y-4">
      <div className="text-center text-xs font-bold uppercase tracking-[0.2em] text-gray-500">— Or —</div>
      <div>
        <div className="text-sm font-bold uppercase tracking-widest text-orange-400 mb-1">Use your phone</div>
        <p className="text-gray-400 text-sm">
          Scan a QR code on your phone to take or choose photos of the front and back of your driver licence.
        </p>
      </div>

      {!captureLink ? (
        <button
          type="button"
          onClick={() => void handleUsePhone()}
          disabled={disabled || issuing}
          className="w-full rounded-xl bg-orange-500 px-4 py-3 text-sm font-bold uppercase tracking-widest text-gray-900 transition hover:bg-orange-400 disabled:opacity-50"
        >
          {issuing ? "Creating link…" : "Use your phone"}
        </button>
      ) : (
        <div className="space-y-4">
          <div className="flex justify-center rounded-xl bg-white p-4">
            <QRCode value={captureLink} size={200} />
          </div>
          <p className="text-center text-sm text-gray-400 leading-relaxed">
            Scan this code with your phone to take or choose photos of the front and back of your driver licence.
          </p>
        </div>
      )}

      <div className="rounded-xl border border-gray-700 bg-gray-900/50 px-4 py-3 space-y-1 text-sm">
        <div className="flex justify-between gap-3">
          <span className="text-gray-400">Front:</span>
          <span className={frontStatus === "PROCESSED" ? "text-emerald-400 font-semibold" : "text-gray-300"}>
            {sideStatusLabel(frontStatus)}
          </span>
        </div>
        <div className="flex justify-between gap-3">
          <span className="text-gray-400">Back:</span>
          <span className={backStatus === "PROCESSED" ? "text-emerald-400 font-semibold" : "text-gray-300"}>
            {sideStatusLabel(backStatus)}
          </span>
        </div>
        {bothProcessed && (
          <div className="pt-2 text-emerald-400 font-semibold">✓ Driver licence received</div>
        )}
      </div>

      <button
        type="button"
        onClick={() => void handleCheckStatus()}
        disabled={disabled || checking}
        className="w-full rounded-xl border border-gray-600 px-4 py-3 text-sm font-bold uppercase tracking-widest text-gray-200 transition hover:bg-gray-700/50 disabled:opacity-50"
      >
        {checking ? "Checking…" : "Check status"}
      </button>

      {error && <p className="text-sm text-rose-400">{error}</p>}
    </div>
  );
}
