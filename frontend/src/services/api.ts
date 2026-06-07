const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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
    create: (token: string, data: { title: string }) =>
      request<Job>("POST", "/jobs", data, token),
    get: (token: string, id: string) => request<Job>("GET", `/jobs/${id}`, undefined, token),
    setupTurn: (token: string, id: string, data: { user_message: string }) =>
      request<{ message: string; status: string; criteria_draft?: unknown }>(
        "POST",
        `/jobs/${id}/setup/turn`,
        data,
        token
      ),
    activate: (token: string, id: string) =>
      request<Job>("POST", `/jobs/${id}/activate`, undefined, token),
  },
  users: {
    list: (token: string) =>
      request<UserProfile[]>("GET", "/users", undefined, token),
    create: (token: string, data: { email: string; role: string }) =>
      request<UserProfile>("POST", "/users", data, token),
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
};

export interface Job {
  id: string;
  company_id: string;
  title: string;
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface UserProfile {
  id: string;
  company_id: string;
  email: string;
  role: string;
  is_active: boolean;
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
