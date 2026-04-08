import { emailBtnFocus } from "./focusStyle";

type Props = {
  variant: "success" | "error";
  message: string;
  onDismiss: () => void;
};

export default function ProviderPanelFlash({ variant, message, onDismiss }: Props) {
  const styles =
    variant === "success"
      ? "border-emerald-900/50 bg-emerald-950/25 text-emerald-100"
      : "border-red-900/50 bg-red-950/20 text-red-200";

  return (
    <div
      className={`mb-5 flex gap-3 rounded-lg border p-3 text-sm ${styles}`}
      role={variant === "error" ? "alert" : "status"}
      aria-live={variant === "error" ? "assertive" : "polite"}
    >
      <p className="min-w-0 flex-1 leading-relaxed">{message}</p>
      <button
        type="button"
        onClick={onDismiss}
        className={`flex h-11 min-w-11 shrink-0 items-center justify-center rounded text-lg leading-none text-[#94a3b8] transition hover:bg-white/5 hover:text-[#e8edf5] ${emailBtnFocus}`}
        aria-label="Dismiss this message"
      >
        <span aria-hidden="true">×</span>
      </button>
    </div>
  );
}
