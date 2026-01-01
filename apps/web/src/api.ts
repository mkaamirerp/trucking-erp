const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export async function getPayPeriods() {
  const res = await fetch(`${API_BASE}/payroll/pay-periods`);
  return handle<PayPeriod[]>(res);
}

export async function getMe() {
  const res = await fetch(`/api/v1/me`);
  return handle<Me>(res);
}

export async function createPayPeriod(payload: PayPeriodCreate) {
  const res = await fetch(`${API_BASE}/payroll/pay-periods`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<PayPeriod>(res);
}

export async function closePayPeriod(id: number) {
  const res = await fetch(`${API_BASE}/payroll/pay-periods/${id}/close`, { method: "POST" });
  return handle<PayPeriod>(res);
}

export async function listPayRuns() {
  // NOTE: backend currently lacks a list endpoint; this will fail until implemented.
  const res = await fetch(`${API_BASE}/payroll/pay-runs`);
  return handle<PayRunSummary[]>(res);
}

export async function createPayRun(payload: PayRunCreatePayload) {
  const res = await fetch(`${API_BASE}/payroll/pay-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<PayRun>(res);
}

export async function generatePayRun(id: number) {
  const res = await fetch(`${API_BASE}/payroll/pay-runs/${id}/generate`, { method: "POST" });
  return handle<{ pay_run_id: number; item_count: number }>(res);
}

export async function finalizePayRun(id: number) {
  const res = await fetch(`${API_BASE}/payroll/pay-runs/${id}/finalize`, { method: "POST" });
  return handle<{ pay_run_id: number; status: string; totals_snapshot?: unknown }>(res);
}

export async function getPayRun(id: number) {
  const res = await fetch(`${API_BASE}/payroll/pay-runs/${id}`);
  return handle<PayRunDetail>(res);
}

export async function getPayRunPayees(runId: number) {
  const res = await fetch(`${API_BASE}/payroll/pay-runs/${runId}/payees`);
  return handle<PayRunPayeeRow[]>(res);
}

export async function getPayRunItems(runId: number, payeeId?: number) {
  const url = new URL(`${API_BASE}/payroll/pay-runs/${runId}/items`, window.location.origin);
  if (payeeId) url.searchParams.set("payee_id", String(payeeId));
  const res = await fetch(url.toString().replace(window.location.origin, ""));
  return handle<PayRunItem[]>(res);
}

export async function listDocuments() {
  const res = await fetch(`${API_BASE}/payroll/documents`);
  return handle<PayDocument[]>(res);
}

// ---- Types ----
export type PayPeriod = {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  status: string;
  created_at: string;
  updated_at: string;
  closed_at?: string | null;
};

export type PayPeriodCreate = {
  name: string;
  start_date: string;
  end_date: string;
};

export type PayRunItem = {
  id: number;
  payee_id: number;
  source_type: string;
  description: string;
  amount_signed: number;
  currency: string;
  quantity?: number | null;
  unit_rate?: number | null;
  charge_category_id?: number | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
};

export type PayRun = {
  id: number;
  pay_period_id: number;
  pay_document_type: string;
  worker_type_snapshot: string;
  base_currency_snapshot: string;
  pay_date: string;
  status: string;
  payout_status: string;
  calculation_snapshot_json?: Record<string, unknown> | null;
  totals_snapshot?: Record<string, unknown> | null;
  finalized_at?: string | null;
  finalized_by?: number | null;
  created_at: string;
  updated_at: string;
  items?: PayRunItem[];
};

export type PayRunSummary = PayRun;

export type PayRunDetail = Omit<PayRun, "items">;

export type PayRunPayeeRow = {
  payee_id: number;
  display_name: string;
  net_amount: number;
  flags: {
    negative_net: boolean;
    has_overrides: boolean;
    missing_payout_preference: boolean;
  };
};

export type PayRunCreatePayload = {
  pay_period_id: number;
  pay_document_type: string;
  worker_type_snapshot: string;
  pay_date: string;
  base_currency_snapshot: string;
};

export type PayDocument = {
  id: number;
  tenant_id: number;
  pay_run_id: number;
  payee_id: number;
  document_type: string;
  file_storage_key: string;
  version: number;
  sha256?: string | null;
  generated_at: string;
  generated_by?: number | null;
};

export type Me = {
  user_id: number | null;
  tenant_id: number;
  roles: string[];
};
