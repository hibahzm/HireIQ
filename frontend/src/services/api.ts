// Default to the relative `/api` path so requests flow through the reverse proxy
// (nginx in the container, the Vite dev-server proxy locally) instead of being
// hardcoded to localhost:8000 — which only works on a dev laptop, never in prod.
// Override with VITE_API_URL when calling the API on a different origin.
const BASE_URL = import.meta.env.VITE_API_URL || "/api";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  token?: string
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, detail.detail ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  auth: {
    register: (data: { company_name: string; email: string; password: string }) =>
      request<{ access_token: string; token_type: string }>("POST", "/auth/register", data),
    login: (data: { email: string; password: string }) =>
      request<{ access_token: string; token_type: string }>("POST", "/auth/login", data),
    refresh: () =>
      request<{ access_token: string; token_type: string }>("POST", "/auth/refresh"),
    logout: (token: string) => request<void>("POST", "/auth/logout", undefined, token),
    setPassword: (data: { token: string; new_password: string }) =>
      request<{ access_token: string; token_type: string }>("POST", "/auth/set-password", data),
    me: (token: string) =>
      request<{ id: string; company_id: string; email: string; role: string; is_active: boolean }>(
        "GET",
        "/auth/me",
        undefined,
        token
      ),
  },
  jobs: {
    list: (token: string, status?: string) =>
      request<Job[]>("GET", `/jobs${status ? `?status=${status}` : ""}`, undefined, token),
    create: (token: string, data: { title: string; description?: string; streaming_interview?: boolean }) =>
      request<Job>("POST", "/jobs", data, token),
    get: (token: string, id: string) => request<Job>("GET", `/jobs/${id}`, undefined, token),
    setupConversation: (token: string, id: string) =>
      request<SetupConversation>("GET", `/jobs/${id}/setup/conversation`, undefined, token),
    setupTurn: (token: string, id: string, data: { user_message: string }) =>
      request<{ message: string; status: string; criteria_draft?: unknown; job_status?: string | null }>(
        "POST",
        `/jobs/${id}/setup/turn`,
        data,
        token
      ),
    saveCriteria: (token: string, id: string, data: JobCriteriaInput) =>
      request<Job>("PUT", `/jobs/${id}/criteria`, data, token),
    activate: (token: string, id: string) =>
      request<Job>("POST", `/jobs/${id}/activate`, undefined, token),
    close: (token: string, id: string) =>
      request<Job>("POST", `/jobs/${id}/close`, undefined, token),
    reopen: (token: string, id: string) =>
      request<Job>("POST", `/jobs/${id}/reopen`, undefined, token),
    archive: (token: string, id: string) =>
      request<Job>("POST", `/jobs/${id}/archive`, undefined, token),
    delete: (token: string, id: string) =>
      request<void>("DELETE", `/jobs/${id}`, undefined, token),
  },
  applications: {
    listByJob: (token: string, jobId: string) =>
      request<Application[]>("GET", `/jobs/${jobId}/applications`, undefined, token),
    invite: (token: string, applicationId: string) =>
      request<InterviewInviteResponse>("POST", `/applications/${applicationId}/invite`, undefined, token),
    rescreen: (token: string, applicationId: string) =>
      request<{ status: string; application_id: string }>(
        "POST",
        `/applications/${applicationId}/rescreen`,
        undefined,
        token
      ),
  },
  company: {
    get: (token: string) =>
      request<CompanyProfile>("GET", "/company", undefined, token),
    updateOverview: (token: string, overview: string) =>
      request<CompanyProfile>("PUT", "/company/overview", { overview }, token),
  },
  users: {
    list: (token: string) =>
      request<UserProfile[]>("GET", "/users", undefined, token),
    create: (token: string, data: { email: string; role: string }) =>
      request<UserInviteResponse>("POST", "/users", data, token),
    setRole: (token: string, id: string, role: string) =>
      request<UserProfile>("PUT", `/users/${id}/role`, { role }, token),
    deactivate: (token: string, id: string) =>
      request<void>("DELETE", `/users/${id}`, undefined, token),
  },
  evaluations: {
    listByJob: (token: string, jobId: string) =>
      request<ShortlistItem[]>("GET", `/jobs/${jobId}/evaluations`, undefined, token),
    get: (token: string, evaluationId: string) =>
      request<EvaluationDetail>("GET", `/evaluations/${evaluationId}`, undefined, token),
  },
  feedback: {
    get: (token: string) =>
      request<FeedbackReport>("GET", `/feedback/${token}`),
  },
  analytics: {
    job: (token: string, jobId: string) =>
      request<JobAnalytics>("GET", `/jobs/${jobId}/analytics`, undefined, token),
    overview: (token: string) =>
      request<CompanyOverview>("GET", "/analytics/overview", undefined, token),
  },
  platform: {
    overview: (token: string) =>
      request<PlatformOverview>("GET", "/platform/overview", undefined, token),
    deleteCompany: (token: string, companyId: string) =>
      request<void>("DELETE", `/platform/companies/${companyId}`, undefined, token),
  },
};

export interface InterviewInviteResponse {
  interview_token: string;
  expires_at: string;
}

export interface Job {
  id: string;
  company_id: string;
  title: string;
  description?: string | null;
  streaming_interview: boolean;
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface Application {
  id: string;
  job_id: string;
  candidate_id: string;
  candidate_name?: string | null;
  candidate_email?: string | null;
  screening_score: number | null;
  screening_rationale?: string | null;
  screening_status: string;
  status: string;
  interview_token?: string | null;
  interview_token_expires_at?: string | null;
  evaluation_id?: string | null;
  created_at: string;
}

export interface SetupConversation {
  messages: Array<{ role: "user" | "assistant"; content: string }>;
  status: string; // conversation: in_progress | completed | failed
  job_status: string;
  criteria: Record<string, unknown> | null;
}

export interface JobCriteriaInput {
  required_skills: Array<Record<string, unknown>>;
  optional_skills?: Array<Record<string, unknown>>;
  experience_level?: string;
  min_years_experience?: number | null;
  evaluation_dimensions: Array<Record<string, unknown>>;
  dealbreakers?: Array<Record<string, unknown>>;
  min_screening_score?: number;
}

export interface CompanyProfile {
  id: string;
  name: string;
  overview: string | null;
}

export interface UserProfile {
  id: string;
  company_id: string;
  email: string;
  role: string;
  is_active: boolean;
}

export interface UserInviteResponse extends UserProfile {
  invite_link?: string | null;
}

export interface ShortlistItem {
  evaluation_id: string;
  application_id: string;
  candidate: { full_name: string };
  overall_score: number;
  recommendation: "hire" | "no_hire" | "uncertain";
  confidence_flag: boolean;
  created_at: string;
}

export interface DimensionScore {
  dimension: string;
  score: number;
  evidence_quotes: string[];
}

export interface ConsistencyFlag {
  claim: string;
  cv_statement: string;
  interview_statement: string;
  flag_type: "contradiction" | "unverified";
}

export interface CommunicationQuality {
  response_depth: number;
  filler_word_frequency: number;
  deflection_frequency: number;
}

export interface TranscriptTurn {
  turn_index: number;
  speaker: string;
  content_text: string;
  audio_url: string | null;
}

export interface EvaluationDetail {
  id: string;
  application_id: string;
  overall_score: number;
  recommendation: "hire" | "no_hire" | "uncertain";
  dimension_scores: DimensionScore[];
  consistency_flags: ConsistencyFlag[];
  communication_quality: CommunicationQuality;
  confidence_flag: boolean;
  confidence_reason: string | null;
  summary: string | null;
  transcript: TranscriptTurn[];
  created_at: string;
}

export interface FeedbackReport {
  job_title: string;
  overall_score: number;
  dimension_scores: Array<{ dimension: string; score: number }>;
  summary: { strengths: string; areas_for_improvement: string } | null;
}

export interface TimingPercentiles {
  p50: number;
  p95: number;
}

export interface ScoreBucket {
  band: string;
  count: number;
}

export interface JobAnalytics {
  job_id: string;
  funnel: { received: number; qualified: number; interviewed: number; evaluated: number };
  qualification_rate: number | null;
  interview_completion_rate: number | null;
  avg_evaluation_score: number | null;
  time_to_screen_seconds: TimingPercentiles | null;
  time_to_evaluate_seconds: TimingPercentiles | null;
  score_distribution: ScoreBucket[];
}

export interface CompanyOverview {
  period: string;
  total_applications: number;
  screening_pass_rate: number | null;
  avg_evaluation_score: number | null;
  jobs: Array<{ id: string; title: string; status: string }>;
}

export interface PlatformOverview {
  companies: Array<{
    id: string;
    name: string;
    activity_events: number;
    job_events: number;
    prompt_tokens: number;
    completion_tokens: number;
    estimated_cost_usd: number;
    last_activity_at: string | null;
  }>;
  usage: Array<{
    company_id: string | null;
    company_name: string | null;
    agent_type: string;
    prompt_tokens: number;
    completion_tokens: number;
    estimated_cost_usd: number;
  }>;
  audit_events: Array<{
    company_id: string | null;
    company_name: string | null;
    event_type: string;
    count: number;
  }>;
}
