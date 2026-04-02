import { useSearchParams } from "react-router-dom";

/**
 * Component to display session expiration message on signin page
 * Reads the `reason` query parameter and shows appropriate message
 */
export function SessionExpiredMessage() {
  const [searchParams] = useSearchParams();
  const reason = searchParams.get("reason");

  if (!reason || reason !== "session_expired") {
    return null;
  }

  return (
    <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-md text-sm text-yellow-800">
      <p className="font-medium">Your session has expired</p>
      <p className="text-yellow-700 mt-1">Please sign in again to continue.</p>
    </div>
  );
}
