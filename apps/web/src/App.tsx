import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import PayPeriodsPage from "./pages/PayPeriodsPage";
import PayRunsPage from "./pages/PayRunsPage";
import PayRunNewPage from "./pages/PayRunNewPage";
import PayRunDetailPage from "./pages/PayRunDetailPage";
import DocumentsPage from "./pages/DocumentsPage";
import LandingPage from "./pages/LandingPage";
import { useMe } from "./hooks/useMe";

function App() {
  const { loading, error } = useMe();
  const location = useLocation();
  const isAppRoute = location.pathname.startsWith("/payroll");

  if (isAppRoute && loading) {
    return (
      <div className="flex items-center justify-center min-h-screen text-sm text-gray-700">
        Loading session...
      </div>
    );
  }

  if (isAppRoute && error) {
    return (
      <div className="flex items-center justify-center min-h-screen text-sm text-red-600">
        Unable to load your session. Please try again later.
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
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
