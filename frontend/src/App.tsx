import { BrowserRouter, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import PrivateRoute from "./components/PrivateRoute";

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

// ── Page wrappers that pull route params and auth token ──────────────────────

function JobSetupWrapper() {
  const { jobId = "" } = useParams();
  const { token = "" } = useAuth();
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
  const { token = "" } = useAuth();
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
  const { token = "" } = useAuth();
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
  const { token = "" } = useAuth();
  const navigate = useNavigate();
  return <UserManagementPage token={token} onBack={() => navigate("/jobs")} />;
}

function ShortlistWrapper() {
  const { jobId = "" } = useParams();
  const { token = "" } = useAuth();
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
  const { token = "" } = useAuth();
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
  const { token = "" } = useAuth();
  const navigate = useNavigate();
  return (
    <JobListPage
      token={token}
      onSelectJob={(id) => navigate(`/jobs/${id}/applications`)}
      onSetupJob={(id) => navigate(`/jobs/${id}/setup`)}
    />
  );
}

// ── Auth pages that set token on success ─────────────────────────────────────

function LoginWrapper() {
  const { setToken } = useAuth();
  const navigate = useNavigate();
  return (
    <LoginPage
      onSuccess={(t) => { setToken(t); navigate("/jobs"); }}
      onRegister={() => navigate("/register")}
    />
  );
}

function RegisterWrapper() {
  const { setToken } = useAuth();
  const navigate = useNavigate();
  return (
    <RegisterPage
      onSuccess={(t) => { setToken(t); navigate("/jobs"); }}
      onLogin={() => navigate("/login")}
    />
  );
}

function SetPasswordWrapper() {
  const { setToken } = useAuth();
  const navigate = useNavigate();
  return (
    <SetPasswordPage
      onSuccess={(t) => { setToken(t); navigate("/jobs"); }}
    />
  );
}

// ── Router ────────────────────────────────────────────────────────────────────

function AppRoutes() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginWrapper />} />
      <Route path="/register" element={<RegisterWrapper />} />
      <Route path="/set-password" element={<SetPasswordWrapper />} />
      <Route path="/apply/:jobId" element={<JobApplicationWrapper />} />
      <Route path="/interview/:token" element={<InterviewWrapper />} />

      {/* Protected */}
      <Route path="/jobs" element={<PrivateRoute><JobListWrapper /></PrivateRoute>} />
      <Route path="/jobs/:jobId/setup" element={<PrivateRoute><JobSetupWrapper /></PrivateRoute>} />
      <Route path="/jobs/:jobId/applications" element={<PrivateRoute><ApplicationListWrapper /></PrivateRoute>} />
      <Route path="/applications/:applicationId" element={<PrivateRoute><ApplicationDetailWrapper /></PrivateRoute>} />
      <Route path="/jobs/:jobId/evaluations" element={<PrivateRoute><ShortlistWrapper /></PrivateRoute>} />
      <Route path="/evaluations/:evaluationId" element={<PrivateRoute><EvaluationDetailWrapper /></PrivateRoute>} />
      <Route path="/users" element={<PrivateRoute><UserManagementWrapper /></PrivateRoute>} />

      {/* Default */}
      <Route path="/" element={<Navigate to="/jobs" replace />} />
      <Route path="*" element={<Navigate to="/jobs" replace />} />
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
