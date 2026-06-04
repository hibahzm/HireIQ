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
      request<User[]>("GET", "/users", undefined, token),
    create: (token: string, data: { email: string; role: string }) =>
      request<User>("POST", "/users", data, token),
    setRole: (token: string, id: string, role: string) =>
      request<User>("PUT", `/users/${id}/role`, { role }, token),
    deactivate: (token: string, id: string) =>
      request<void>("DELETE", `/users/${id}`, undefined, token),
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
