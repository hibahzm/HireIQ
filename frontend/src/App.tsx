import { BrowserRouter, Navigate, Outlet, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import PrivateRoute from "./components/PrivateRoute";
import AppShell from "./components/AppShell";

import LoginPage from "./pages/auth/LoginPage";
import RegisterPage from "./pages/auth/RegisterPage";
import SetPasswordPage from "./pages/auth/SetPasswordPage";
import JobListPage from "./pages/jobs/JobListPage";
import JobSetupPage from "./pages/jobs/JobSetupPage";
import ApplicationListPage from "./pages/applications/ApplicationListPage";
import ApplicationDetailPage from "./pages/applications/ApplicationDetailPage";
import JobApplicationPage from "./pages/applications/JobApplicationPage";
import InterviewRoomPage from "./pages/interview/InterviewRoomPage";
import UserManagementPage from "./pages/company/UserManagementPage";
import ShortlistPage from "./pages/evaluations/ShortlistPage";
import EvaluationDetailPage from "./pages/evaluations/EvaluationDetailPage";
import FeedbackReportPage from "./pages/feedback/FeedbackReportPage";
import CompanyOverviewPage from "./pages/analytics/CompanyOverviewPage";
import JobAnalyticsPage from "./pages/analytics/JobAnalyticsPage";

// ── Page wrappers that pull route params and auth token ──────────────────────

function JobSetupWrapper() {
  const { jobId = "" } = useParams();
  const token = useAuth().token ?? "";
  const navigate = useNavigate();
  return (
    <JobSetupPage
      token={token}
      jobId={jobId}
      onActivated={() => navigate("/jobs")}
      onBack={() => navigate("/jobs")}
    />
  );
}

function ApplicationListWrapper() {
  const { jobId = "" } = useParams();
  const token = useAuth().token ?? "";
  const navigate = useNavigate();
  return (
    <ApplicationListPage
      token={token}
      jobId={jobId}
      onSelectApplication={(id) => navigate(`/applications/${id}`)}
      onBack={() => navigate("/jobs")}
    />
  );
}

function ApplicationDetailWrapper() {
  const { applicationId = "" } = useParams();
  const token = useAuth().token ?? "";
  const navigate = useNavigate();
  return (
    <ApplicationDetailPage
      token={token}
      applicationId={applicationId}
      onBack={() => navigate(-1)}
    />
  );
}

function JobApplicationWrapper() {
  const { jobId = "" } = useParams();
  return <JobApplicationPage jobId={jobId} />;
}

function InterviewWrapper() {
  const { token = "" } = useParams();
  return <InterviewRoomPage token={token} />;
}

function UserManagementWrapper() {
  const token = useAuth().token ?? "";
  const navigate = useNavigate();
  return <UserManagementPage token={token} onBack={() => navigate("/jobs")} />;
}

function ShortlistWrapper() {
  const { jobId = "" } = useParams();
  const token = useAuth().token ?? "";
  const navigate = useNavigate();
  return (
    <ShortlistPage
      token={token}
      jobId={jobId}
      onSelectEvaluation={(id) => navigate(`/evaluations/${id}`)}
      onBack={() => navigate(`/jobs/${jobId}/applications`)}
    />
  );
}

function EvaluationDetailWrapper() {
  const { evaluationId = "" } = useParams();
  const token = useAuth().token ?? "";
  const navigate = useNavigate();
  return (
    <EvaluationDetailPage
      token={token}
      evaluationId={evaluationId}
      onBack={() => navigate(-1)}
    />
  );
}

function JobListWrapper() {
  const token = useAuth().token ?? "";
  const navigate = useNavigate();
  return (
    <JobListPage
      token={token}
      onSelectJob={(id) => navigate(`/jobs/${id}/applications`)}
      onSetupJob={(id) => navigate(`/jobs/${id}/setup`)}
    />
  );
}

function CompanyOverviewWrapper() {
  const token = useAuth().token ?? "";
  const navigate = useNavigate();
  return (
    <CompanyOverviewPage
      token={token}
      onSelectJob={(id) => navigate(`/jobs/${id}/applications`)}
      onViewJobAnalytics={(id) => navigate(`/jobs/${id}/analytics`)}
      onManageJobs={() => navigate("/jobs")}
    />
  );
}

function JobAnalyticsWrapper() {
  const { jobId = "" } = useParams();
  const token = useAuth().token ?? "";
  const navigate = useNavigate();
  return <JobAnalyticsPage token={token} jobId={jobId} onBack={() => navigate("/overview")} />;
}

// ── Auth pages that set token on success ─────────────────────────────────────

function LoginWrapper() {
  const { setToken } = useAuth();
  const navigate = useNavigate();
  return (
    <LoginPage
      onSuccess={(t) => { setToken(t); navigate("/overview"); }}
      onRegister={() => navigate("/register")}
    />
  );
}

function RegisterWrapper() {
  const { setToken } = useAuth();
  const navigate = useNavigate();
  return (
    <RegisterPage
      onSuccess={(t) => { setToken(t); navigate("/overview"); }}
      onLogin={() => navigate("/login")}
    />
  );
}

function SetPasswordWrapper() {
  const { setToken } = useAuth();
  const navigate = useNavigate();
  return (
    <SetPasswordPage
      onSuccess={(t) => { setToken(t); navigate("/overview"); }}
    />
  );
}

// ── Router ────────────────────────────────────────────────────────────────────

// Protected pages share the persistent app shell (sidebar + top bar + breadcrumbs).
function ProtectedLayout() {
  return (
    <PrivateRoute>
      <AppShell>
        <Outlet />
      </AppShell>
    </PrivateRoute>
  );
}

function AppRoutes() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginWrapper />} />
      <Route path="/register" element={<RegisterWrapper />} />
      <Route path="/set-password" element={<SetPasswordWrapper />} />
      <Route path="/apply/:jobId" element={<JobApplicationWrapper />} />
      <Route path="/interview/:token" element={<InterviewWrapper />} />
      <Route path="/feedback/:token" element={<FeedbackReportPage />} />

      {/* Protected — rendered inside the app shell */}
      <Route element={<ProtectedLayout />}>
        <Route path="/overview" element={<CompanyOverviewWrapper />} />
        <Route path="/jobs" element={<JobListWrapper />} />
        <Route path="/jobs/:jobId/analytics" element={<JobAnalyticsWrapper />} />
        <Route path="/jobs/:jobId/setup" element={<JobSetupWrapper />} />
        <Route path="/jobs/:jobId/applications" element={<ApplicationListWrapper />} />
        <Route path="/applications/:applicationId" element={<ApplicationDetailWrapper />} />
        <Route path="/jobs/:jobId/evaluations" element={<ShortlistWrapper />} />
        <Route path="/evaluations/:evaluationId" element={<EvaluationDetailWrapper />} />
        <Route path="/users" element={<UserManagementWrapper />} />
      </Route>

      {/* Default — post-login landing is the company overview (FR-005) */}
      <Route path="/" element={<Navigate to="/overview" replace />} />
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
