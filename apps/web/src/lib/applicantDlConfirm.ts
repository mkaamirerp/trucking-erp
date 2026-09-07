import { API_BASE, fetchWithTenant } from "../api";

export type ApplicantDlConfirmResult = {
  intake_payload?: Record<string, unknown>;
  file_id?: string;
  sanitized_file_id?: string;
  license_extract_status?: string;
};

const DL_CONFIRM_PATH = "driver-onboarding/applicant/application/dl-confirm";

/**
 * Build the laptop dl-confirm request URL.
 * fetchWithTenant/fetch accept same-origin relative paths and absolute URLs.
 * Always resolve with pageOrigin so relative API_BASE (including "") is valid.
 */
export function applicantDlConfirmRequestUrl(params: {
  onboardingToken: string;
  apiBase?: string;
  pageOrigin?: string;
}): string {
  const apiBase = params.apiBase ?? API_BASE;
  const pageOrigin = params.pageOrigin ?? window.location.origin;
  const endpoint = new URL(`${apiBase.replace(/\/$/, "")}/${DL_CONFIRM_PATH}`, pageOrigin);
  endpoint.searchParams.set("token", params.onboardingToken);
  return endpoint.origin === pageOrigin
    ? `${endpoint.pathname}${endpoint.search}`
    : endpoint.toString();
}

async function handleJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    const err = new Error(text || res.statusText);
    (err as Error & { status?: number }).status = res.status;
    throw err;
  }
  return res.json();
}

/** Confirm the processed DL preview (Use This Photo). PDF417 runs on confirmed CDL_BACK. */
export async function confirmPersonApplicationDlSide(params: {
  onboardingToken: string;
  docType: string;
}): Promise<ApplicantDlConfirmResult> {
  const requestUrl = applicantDlConfirmRequestUrl({ onboardingToken: params.onboardingToken });
  const form = new FormData();
  form.append("doc_type", params.docType);
  const res = await fetchWithTenant(requestUrl, {
    method: "POST",
    body: form,
  });
  const data = await handleJson<{ intake_payload?: Record<string, unknown> }>(res);
  const fileMeta = (data.intake_payload as { files?: Record<string, { file_id?: string; storage_key?: string; enh_file_id?: string }> } | undefined)
    ?.files?.[params.docType];
  const processedMeta = (data.intake_payload as { files?: Record<string, { storage_key?: string; file_id?: string; enh_file_id?: string }> } | undefined)
    ?.files?.[`${params.docType}_PROCESSED`];
  const fileId = fileMeta?.file_id ?? fileMeta?.storage_key;
  const sanitizedFileId =
    fileMeta?.enh_file_id ??
    processedMeta?.enh_file_id ??
    processedMeta?.file_id ??
    processedMeta?.storage_key ??
    fileId;
  return {
    intake_payload: data.intake_payload as Record<string, unknown> | undefined,
    file_id: fileId,
    sanitized_file_id: sanitizedFileId,
    license_extract_status: (data.intake_payload as { license_extract_status?: string } | undefined)
      ?.license_extract_status,
  };
}
