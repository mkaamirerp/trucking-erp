import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import PayPeriodsPage from "./pages/PayPeriodsPage";
import PayRunsPage from "./pages/PayRunsPage";
import PayRunNewPage from "./pages/PayRunNewPage";
import PayRunDetailPage from "./pages/PayRunDetailPage";
import DocumentsPage from "./pages/DocumentsPage";
import { useMe } from "./hooks/useMe";

function App() {
  const { loading, error } = useMe();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen text-sm text-gray-700">
        Loading session...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen text-sm text-red-600">
        Failed to load session: {error}
      </div>
    );
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/payroll/pay-periods" replace />} />
        <Route path="/payroll/pay-periods" element={<PayPeriodsPage />} />
        <Route path="/payroll/pay-runs" element={<PayRunsPage />} />
        <Route path="/payroll/pay-runs/new" element={<PayRunNewPage />} />
        <Route path="/payroll/pay-runs/:id" element={<PayRunDetailPage />} />
        <Route path="/payroll/documents" element={<DocumentsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

export default App;
