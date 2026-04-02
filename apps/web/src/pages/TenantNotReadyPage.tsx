import { useTenant } from "../contexts/TenantContext";

export function TenantNotReadyPage() {
  const { tenantStatus, slug } = useTenant();
  const reason = tenantStatus?.reason || "The workspace is not ready yet.";
  const setupUrl = slug ? `https://${slug}.truckerp.me/company-setup` : "https://truckerp.me";

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full text-center">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">Workspace Not Ready</h1>
          <p className="text-lg text-gray-600">
            The workspace <span className="font-semibold">{slug}</span> is not available right now.
          </p>
        </div>

        <div className="bg-white rounded-lg shadow-md p-6 space-y-4">
          <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4 mb-4">
            <p className="text-sm text-yellow-800">{reason}</p>
          </div>

          <p className="text-gray-700 mb-6">
            Please try again later or contact support if this issue persists.
          </p>

          <div className="space-y-3">
            <a
              href={setupUrl}
              className="block w-full bg-blue-600 text-white py-3 px-4 rounded-md font-medium hover:bg-blue-700 transition-colors"
            >
              Continue Setup
            </a>

            <a
              href="https://truckerp.me"
              className="block w-full bg-gray-200 text-gray-800 py-3 px-4 rounded-md font-medium hover:bg-gray-300 transition-colors"
            >
              Back to Main Site
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
