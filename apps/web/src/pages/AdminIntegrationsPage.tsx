import { useLocation } from "react-router-dom";
import AdminPlaceholderPage from "./AdminPlaceholderPage";

const INTEGRATIONS: Record<string, string> = {
  smtp: "SMTP / Email settings for notifications and onboarding invites.",
  eld: "ELD (Electronic Logging Device) integration settings.",
  fuel: "Fuel API and card integration settings.",
};

export default function AdminIntegrationsPage() {
  const loc = useLocation();
  const match = loc.pathname.match(/\/admin\/integrations\/(\w+)/);
  const key = (match?.[1] || "").toLowerCase();
  const desc = INTEGRATIONS[key] || "Integration settings.";

  return <AdminPlaceholderPage title={key ? `${key.toUpperCase()} Settings` : "Integrations"} description={desc} />;
}
