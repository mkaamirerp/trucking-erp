import { useRef } from "react";
import { FieldErrorText, RequiredGlyph } from "./onboardingFields";
import { inp, inpErr } from "./onboardingFieldStyles";
import { formatDateAsTyped } from "../core/onboardingFieldRules";

type Props = {
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  invalid?: boolean;
  error?: string;
  showError?: boolean;
  extraClass?: string;
};

export function OnboardingDateField({
  value,
  onChange,
  required = false,
  invalid = false,
  error,
  showError = false,
  extraClass = "",
}: Props) {
  const pickerRef = useRef<HTMLInputElement>(null);
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.test(value) ? value : "";

  function openPicker() {
    const el = pickerRef.current;
    if (!el) return;
    try {
      el.showPicker();
    } catch {
      el.click();
    }
  }

  const pad = required ? "pr-16" : "pr-10";

  return (
    <div>
      <div className="relative">
        <input
          className={`${inp} ${pad} ${invalid ? inpErr : ""} ${extraClass}`.trim()}
          type="text"
          inputMode="numeric"
          maxLength={10}
          placeholder="YYYY-MM-DD"
          value={value}
          onChange={(e) => onChange(formatDateAsTyped(e.target.value))}
          autoComplete="off"
        />
        <input
          ref={pickerRef}
          type="date"
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          value={iso}
          onChange={(e) => onChange(e.target.value)}
        />
        <button
          type="button"
          className={`absolute top-1/2 z-[1] -translate-y-1/2 text-gray-400 hover:text-orange-400 ${required ? "right-8" : "right-3"}`}
          aria-label="Open calendar"
          onClick={openPicker}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <rect x="3" y="5" width="18" height="16" rx="2" />
            <path d="M3 10h18M8 3v4M16 3v4" />
          </svg>
        </button>
        {required ? <RequiredGlyph /> : null}
      </div>
      <FieldErrorText show={showError} message={error} />
    </div>
  );
}
