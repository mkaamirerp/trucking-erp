import { useTenant } from "../contexts/TenantContext";

export function TenantNotFoundPage() {
  const { slug } = useTenant();

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full text-center">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">Workspace Not Found</h1>
          <p className="text-lg text-gray-600">
            {slug ? (
              <>
                We could not find a workspace for <span className="font-semibold">{slug}</span>.
              </>
            ) : (
              <>We could not find that workspace.</>
            )}
          </p>
        </div>

        <div className="bg-white rounded-lg shadow-md p-6 space-y-4">
          <p className="text-gray-700">
            Double-check the URL or create a new workspace on the main site.
          </p>

          <div className="space-y-3">
            <a
              href="https://truckerp.me"
              className="block w-full bg-blue-600 text-white py-3 px-4 rounded-md font-medium hover:bg-blue-700 transition-colors"
            >
              Go to Main Site
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
