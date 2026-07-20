/**
 * Typed fetch wrapper for the Yarnboard API.
 *
 * Every call sets credentials: 'include' so the Flask session cookie is
 * sent/received -- required locally, where the Vite dev server
 * (localhost:5173) and Flask (localhost:5001) are different origins.
 *
 * BASE_URL falls back to "" (a relative path) when VITE_API_BASE_URL
 * isn't set at build time, which is the production case: a single Flask
 * service serves both this built frontend and the /api/* routes from the
 * same origin, so `fetch("" + "/api/profile")` correctly resolves against
 * whatever domain is currently serving the page, with no hardcoded URL
 * needed. Locally, .env.local sets VITE_API_BASE_URL explicitly since the
 * two dev servers really are on different ports.
 */
import type {
  Pattern,
  PatternDraft,
  PreviewResponse,
  User,
} from "../types/models";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, body.error || response.statusText);
  }
  return body as T;
}

// --- Auth -------------------------------------------------------------

export function register(username: string, email: string, password: string) {
  return request<{ message: string }>("/api/register", {
    method: "POST",
    body: JSON.stringify({ username, email, password }),
  });
}

export function login(email: string, password: string) {
  return request<{ message: string; username: string }>("/api/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout() {
  return request<{ message: string }>("/api/logout", { method: "POST" });
}

export function fetchProfile() {
  return request<User>("/api/profile");
}

// --- Patterns -----------------------------------------------------------

export function previewPattern(url: string) {
  return request<PreviewResponse>("/api/patterns/preview", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export interface SubmitPayload extends PatternDraft {
  original_url: string;
}

export function submitPattern(payload: SubmitPayload) {
  return request<{ message: string; pattern: Pattern }>("/api/patterns/submit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchMyUploads() {
  return request<Pattern[]>("/api/patterns/mine");
}

export function fetchMySaved() {
  return request<Pattern[]>("/api/patterns/saved");
}

export function savePattern(patternId: number) {
  return request<{ message: string }>("/api/patterns/saved", {
    method: "POST",
    body: JSON.stringify({ pattern_id: patternId }),
  });
}

export function unsavePattern(patternId: number) {
  return request<{ message: string }>(`/api/patterns/saved/${patternId}`, {
    method: "DELETE",
  });
}

export function fetchCommunityPatterns() {
  return request<Pattern[]>("/api/patterns/community");
}

export function fetchPattern(patternId: number) {
  return request<Pattern>(`/api/patterns/${patternId}`);
}

export function toggleProgress(
  patternId: number,
  part: string,
  index: number,
  completed: boolean,
) {
  return request<{ completed_steps: Record<string, boolean[]> }>(
    `/api/patterns/${patternId}/progress`,
    {
      method: "PATCH",
      body: JSON.stringify({ part, index, completed }),
    },
  );
}
