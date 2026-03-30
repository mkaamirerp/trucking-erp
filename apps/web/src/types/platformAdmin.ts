/** Mirrors app.schemas.platform.PlatformTenantOut (JSON). */
export type PlatformTenantRow = {
  id: number;
  name: string;
  slug: string;
  status: string;
  plan?: string | null;
  db_status?: string | null;
  db_last_error?: string | null;
  db_last_error_at?: string | null;
  provisioned_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};
