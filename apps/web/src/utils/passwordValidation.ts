/**
 * NIST SP 800-63B aligned password validation:
 * - Length 12–256 (trimmed), no mandatory composition rules
 * - zxcvbn strength score (min 3) with actionable feedback
 * - Have I Been Pwned breach check (k-anonymity, no plaintext sent)
 */

import zxcvbn from "zxcvbn";

export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 256;
export const MIN_STRENGTH_SCORE = 3; // zxcvbn 0–4; 3 = reasonably secure

export type PasswordValidationResult = {
  valid: boolean;
  message: string | null;
  /** Trimmed value used for checks; submit this to the server. */
  trimmed: string;
};

/**
 * Synchronous validation: required, length (trimmed), zxcvbn strength.
 * Use trimmed value when submitting the form.
 */
export function getPasswordValidation(value: string): PasswordValidationResult {
  const trimmed = (value ?? "").trim();

  if (!trimmed) {
    return { valid: false, message: "Password is required.", trimmed };
  }

  if (trimmed.length < PASSWORD_MIN_LENGTH) {
    return {
      valid: false,
      message: `Use at least ${PASSWORD_MIN_LENGTH} characters (passphrases are encouraged).`,
      trimmed,
    };
  }

  if (trimmed.length > PASSWORD_MAX_LENGTH) {
    return {
      valid: false,
      message: `Use at most ${PASSWORD_MAX_LENGTH} characters.`,
      trimmed,
    };
  }

  const result = zxcvbn(trimmed);
  if (result.score < MIN_STRENGTH_SCORE) {
    const suggestion =
      result.feedback.suggestions?.[0] ||
      result.feedback.warning ||
      "Make it longer or less predictable.";
    return {
      valid: false,
      message: `Password is too weak: ${suggestion}`,
      trimmed,
    };
  }

  return { valid: true, message: null, trimmed };
}

/**
 * Check if password appears in Have I Been Pwned breaches (k-anonymity).
 * Only the first 5 chars of the SHA-1 hash are sent; full password never leaves the client.
 */
export async function checkHaveIBeenPwned(password: string): Promise<boolean> {
  const trimmed = (password ?? "").trim();
  if (!trimmed) return false;

  const hashHex = await sha1Hex(trimmed);
  const prefix = hashHex.substring(0, 5).toLowerCase();
  const suffix = hashHex.substring(5).toUpperCase();

  const url = `https://api.pwnedpasswords.com/range/${prefix}`;
  const res = await fetch(url, { method: "GET" });
  if (!res.ok) return false;

  const text = await res.text();
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    const [foundSuffix] = line.split(":");
    if (foundSuffix?.trim().toUpperCase() === suffix) return true;
  }
  return false;
}

async function sha1Hex(message: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(message);
  const hashBuffer = await crypto.subtle.digest("SHA-1", data);
  const hashArray = new Uint8Array(hashBuffer);
  return Array.from(hashArray)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
