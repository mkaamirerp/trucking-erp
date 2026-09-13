import { inp, inpErr } from "./onboardingFieldStyles";

/** Small required marker inside the control, far right. */
export function RequiredGlyph() {
  return (
    <span
      className="pointer-events-none absolute right-3 top-1/2 z-[1] h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-orange-400/90"
      aria-hidden
      title="Required"
    />
  );
}

export function FieldErrorText({ show, message }: { show: boolean; message?: string }) {
  if (!show || !message) return null;
  return <p className="mt-1 text-xs text-rose-400">{message}</p>;
}

export function Field({
  label,
  children,
  half,
  required,
  invalid,
  error,
  skipShell,
}: {
  label: string;
  children: React.ReactNode;
  half?: boolean;
  required?: boolean;
  invalid?: boolean;
  error?: string;
  skipShell?: boolean;
}) {
  return (
    <div className={half ? "col-span-1" : "col-span-2 sm:col-span-1"}>
      <label className="mb-1 block text-xs font-semibold uppercase tracking-widest text-gray-400">{label}</label>
      {skipShell ? (
        children
      ) : (
        <>
          <ControlShell required={required} invalid={invalid}>
            {children}
          </ControlShell>
          <FieldErrorText show={!!(invalid && error)} message={error} />
        </>
      )}
    </div>
  );
}

type BoxProps = {
  required?: boolean;
  invalid?: boolean;
  extraClass?: string;
  children: React.ReactNode;
};

export function ControlShell({ required, invalid, extraClass, children }: BoxProps) {
  return (
    <div className="relative">
      {children}
      {required ? <RequiredGlyph /> : null}
    </div>
  );
}

export function controlClass(required: boolean, invalid: boolean, extra = ""): string {
  const pad = required ? "pr-9" : "";
  return `${inp} ${pad} ${invalid ? inpErr : ""} ${extra}`.trim();
}

export function selectClass(required: boolean, invalid: boolean, extra = ""): string {
  return `${controlClass(required, invalid, extra)} appearance-none`;
}
