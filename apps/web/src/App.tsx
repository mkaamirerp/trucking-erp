import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import PayPeriodsPage from "./pages/PayPeriodsPage";
import PayRunsPage from "./pages/PayRunsPage";
import PayRunNewPage from "./pages/PayRunNewPage";
import PayRunDetailPage from "./pages/PayRunDetailPage";
import DocumentsPage from "./pages/DocumentsPage";
import LandingPage from "./pages/LandingPage";
import SignupPage from "./pages/SignupPage";
import CompanySetupPage from "./pages/CompanySetupPage";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import { useMe } from "./hooks/useMe";
import { getTenantSlugFromHost } from "./tenant";

function App() {
  const { me, loading, error } = useMe();
  const location = useLocation();
  const isAppRoute = /^\/payroll\//.test(location.pathname) || /^\/dashboard/.test(location.pathname);
  const accountSetupPath = "/account-setup";
  const onAccountSetupRoute =
    location.pathname.startsWith(accountSetupPath) || location.pathname.startsWith("/company-setup");
  const hostSlug = getTenantSlugFromHost();

  // If user hits subdomain root, send them to the right place
  if (hostSlug && location.pathname === "/") {
    const target = me?.requires_account_setup ? "/company-setup" : "/dashboard";
    return <Navigate to={target} replace />;
  }

  if (isAppRoute && loading) {
    return (
      <div className="flex items-center justify-center min-h-screen text-sm text-gray-700">
        Loading session...
      </div>
    );
  }

  if (isAppRoute && error) {
    return <Navigate to="/login" replace />;
  }

  if (isAppRoute && !loading && !error && me?.requires_account_setup && !onAccountSetupRoute) {
    return <Navigate to={accountSetupPath} replace />;
  }

  if (isAppRoute && error) {
    return <Navigate to="/login" replace />;
  }

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/signup/*" element={<SignupPage />} />
      <Route path="/login" element={<LoginPage />} />
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
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
