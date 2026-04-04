import { Routes, Route, Navigate, useLocation, useParams } from "react-router-dom";
import Layout from "./components/Layout";
import PayPeriodsPage from "./pages/PayPeriodsPage";
import PayRunsPage from "./pages/PayRunsPage";
import PayRunNewPage from "./pages/PayRunNewPage";
import PayRunDetailPage from "./pages/PayRunDetailPage";
import DocumentsPage from "./pages/DocumentsPage";
import LandingPage from "./pages/LandingPage";
import SignupPage from "./pages/SignupPage";
import WorkspaceIntakePage from "./pages/WorkspaceIntakePage";
import CompanySetupPage from "./pages/CompanySetupPage";
import LoginPage from "./pages/LoginPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import DashboardPage from "./pages/DashboardPage";
import FleetPage from "./pages/FleetPage";
import LoadsListPage from "./pages/LoadsListPage";
import DispatchPage from "./pages/DispatchPage";
import LoadCreatePage from "./pages/LoadCreatePage";
import LoadInboxPage from "./pages/LoadInboxPage";
import LoadDetailPage from "./pages/LoadDetailPage";
import DriverOnboardingPage from "./pages/DriverOnboardingPage";
import DriverOnboardingAdminListPage from "./pages/DriverOnboardingAdminListPage";
import DriverOnboardingAdminDetailPage from "./pages/DriverOnboardingAdminDetailPage";
import OnboardingApplicantPage from "./pages/OnboardingApplicantPage";
import ToolsDiagnosticsPage from "./pages/ToolsDiagnosticsPage";
import AdminLayout from "./components/AdminLayout";
import AdminCompanyProfilePage from "./pages/AdminCompanyProfilePage";
import AdminUsersPage from "./pages/AdminUsersPage";
import AdminRolesPage from "./pages/AdminRolesPage";
import AdminPlaceholderPage from "./pages/AdminPlaceholderPage";
import AcceptInvitePage from "./pages/AcceptInvitePage";
import AddWorkspacePage from "./pages/AddWorkspacePage";
import AdminIntegrationsPage from "./pages/AdminIntegrationsPage";
import AdminEmailConfigPage from "./pages/AdminEmailConfigPage";
import AdminRouteGuard from "./components/AdminRouteGuard";
import { useAuth } from "./contexts/AuthContext";
import { useMe } from "./hooks/useMe";
import { getTenantSlugFromHost } from "./tenant";
import { OPS } from "./routes";
import PlatformApexGate from "./components/PlatformApexGate";
import PlatformShellLayout from "./components/PlatformShellLayout";
import PlatformHomePage from "./pages/PlatformHomePage";
import PlatformTenantsPage from "./pages/PlatformTenantsPage";
import PlatformTenantDetailPage from "./pages/PlatformTenantDetailPage";
import PlatformLoginFailuresPage from "./pages/PlatformLoginFailuresPage";
import PlatformUnlockLoginPage from "./pages/PlatformUnlockLoginPage";

function RedirectDriverOnboardingDetail() {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/operations/driver-onboarding-review/${id ?? ""}`} replace />;
}

function App() {
  const { authReady, isValid } = useAuth();
  const { me, loading, error } = useMe();
  const location = useLocation();

  const isAppRoute =
    /^\/payroll\//.test(location.pathname) ||
    /^\/dashboard/.test(location.pathname) ||
    /^\/dispatch/.test(location.pathname) ||
    /^\/intake/.test(location.pathname) ||
    /^\/inbox/.test(location.pathname) ||
    /^\/fleet/.test(location.pathname) ||
    /^\/loads/.test(location.pathname) ||
    /^\/driver-onboarding/.test(location.pathname) ||
    /^\/operations/.test(location.pathname) ||
    /^\/admin/.test(location.pathname);
  const accountSetupPath = "/account-setup";
  const onAccountSetupRoute =
    location.pathname.startsWith(accountSetupPath) || location.pathname.startsWith("/company-setup");
  const hostSlug = getTenantSlugFromHost();

  // If user hits subdomain root, send them to the right place
  if (hostSlug && location.pathname === "/") {
    const target = me?.requires_account_setup ? "/company-setup" : "/dashboard";
    return <Navigate to={target} replace />;
  }

  // Setup pages require a tenant (subdomain). On main domain, send to landing/signup.
  const onSetupRoute =
    location.pathname.startsWith("/company-setup") || location.pathname.startsWith("/account-setup");
  if (!hostSlug && onSetupRoute) {
    return <Navigate to="/" replace />;
  }

  // Wait for auth bootstrap before making auth decisions
  if (isAppRoute && !authReady) {
    return (
      <div className="flex items-center justify-center min-h-screen text-sm text-gray-700">
        Loading session...
      </div>
    );
  }

  // Not authenticated -> redirect to login
  if (isAppRoute && authReady && !isValid) {
    return <Navigate to="/login" replace />;
  }

  // Authenticated; wait for /me to check requires_account_setup
  if (isAppRoute && authReady && isValid && loading) {
    return (
      <div className="flex items-center justify-center min-h-screen text-sm text-gray-700">
        Loading session...
      </div>
    );
  }

  if (isAppRoute && authReady && isValid && error) {
    return <Navigate to="/login" replace state={{ sessionError: error }} />;
  }

  if (isAppRoute && authReady && isValid && !loading && !error && me?.requires_account_setup && !onAccountSetupRoute) {
    return <Navigate to={accountSetupPath} replace />;
  }

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/signup/*" element={<SignupPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/workspace-intake" element={<WorkspaceIntakePage />} />
      <Route path="/create-workspace" element={<SignupPage publicWorkspaceEntry />} />
      <Route path="/add-workspace" element={<AddWorkspacePage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/accept-invite" element={<AcceptInvitePage />} />
      <Route path="/onboarding" element={<OnboardingApplicantPage />} />
      <Route path="/company-setup" element={<CompanySetupPage />} />
      <Route path="/account-setup" element={<CompanySetupPage />} />
      <Route
        path="/dashboard"
        element={
          <Layout>
            <DashboardPage />
          </Layout>
        }
      />
      <Route
        path="/dispatch"
        element={<DispatchPage />}
      />
      <Route
        path="/inbox"
        element={
          <Layout>
            <LoadInboxPage />
          </Layout>
        }
      />
      <Route
        path="/intake"
        element={
          <Layout>
            <LoadInboxPage />
          </Layout>
        }
      />
      <Route
        path="/fleet"
        element={
          <Layout>
            <FleetPage />
          </Layout>
        }
      />
      <Route
        path="/loads"
        element={
          <Layout>
            <LoadsListPage />
          </Layout>
        }
      />
      <Route
        path="/loads/new"
        element={
          <Layout>
            <LoadCreatePage />
          </Layout>
        }
      />
      <Route
        path="/loads/:id"
        element={
          <Layout>
            <LoadDetailPage />
          </Layout>
        }
      />
      <Route
        path="/payroll/pay-periods"
        element={
          <Layout>
            <PayPeriodsPage />
          </Layout>
        }
      />
      <Route
        path="/payroll/pay-runs"
        element={
          <Layout>
            <PayRunsPage />
          </Layout>
        }
      />
      <Route
        path="/payroll/pay-runs/new"
        element={
          <Layout>
            <PayRunNewPage />
          </Layout>
        }
      />
      <Route
        path="/payroll/pay-runs/:id"
        element={
          <Layout>
            <PayRunDetailPage />
          </Layout>
        }
      />
      <Route
        path="/payroll/documents"
        element={
          <Layout>
            <DocumentsPage />
          </Layout>
        }
      />
      <Route
        path="/driver-onboarding"
        element={
          <Layout>
            <DriverOnboardingPage />
          </Layout>
        }
      />
      <Route path="/operations/driver-onboarding-review" element={<Layout><DriverOnboardingAdminListPage /></Layout>} />
      <Route path="/operations/driver-onboarding-review/:id" element={<Layout><DriverOnboardingAdminDetailPage /></Layout>} />
      {/* Redirect legacy /admin/driver-onboarding to operations namespace */}
      <Route path="/admin/driver-onboarding" element={<Navigate to={OPS.DRIVER_ONBOARDING_REVIEW} replace />} />
      <Route path="/admin/driver-onboarding/:id" element={<RedirectDriverOnboardingDetail />} />
      {/* Tenant Admin (config) shell — company profile, users, settings. Role-gated. */}
      <Route
        path="/admin"
        element={
          <AdminRouteGuard>
            <AdminLayout />
          </AdminRouteGuard>
        }
      >
        <Route index element={<Navigate to="/admin/company-profile" replace />} />
        <Route path="company-profile" element={<AdminCompanyProfilePage />} />
        <Route path="users" element={<AdminUsersPage />} />
        <Route path="roles" element={<AdminRolesPage />} />
        <Route path="payroll" element={<AdminPlaceholderPage title="Payroll Settings" description="Payroll configuration and defaults." />} />
        <Route path="settings/email" element={<AdminEmailConfigPage />} />
        <Route path="integrations/smtp" element={<Navigate to="/admin/settings/email" replace />} />
        <Route path="integrations/eld" element={<AdminIntegrationsPage />} />
        <Route path="integrations/fuel" element={<AdminIntegrationsPage />} />
        <Route path="onboarding" element={<AdminPlaceholderPage title="Onboarding Settings" description="Onboarding workflow and invite defaults." />} />
        <Route path="documents" element={<AdminPlaceholderPage title="Document Rules" description="Required documents and expiry rules." />} />
      </Route>
      <Route path="/tools/diagnostics" element={<ToolsDiagnosticsPage />} />
      <Route
        path="/platform"
        element={
          <PlatformApexGate>
            <PlatformShellLayout />
          </PlatformApexGate>
        }
      >
        <Route index element={<PlatformHomePage />} />
        <Route path="tenants" element={<PlatformTenantsPage />} />
        <Route path="tenants/:id" element={<PlatformTenantDetailPage />} />
        <Route path="login-failures" element={<PlatformLoginFailuresPage />} />
        <Route path="testing/unlock-login" element={<PlatformUnlockLoginPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
