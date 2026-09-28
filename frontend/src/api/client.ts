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
  PatternEditPayload,
  PatternNotification,
  PreviewResponse,
  StitchFiddleLink,
  User,
} from "../types/models";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

/**
 * Resolve a pattern's `photo_url` for use in an <img src>. Unlike every
 * other API call, an <img> tag's src is resolved by the *browser* against
 * the current page's origin, not run through this file's `request()` --
 * so a same-origin-relative photo_url (an uploaded photo, served from our
 * own GET /api/patterns/<id>/photo) would silently resolve against the
 * frontend's own origin instead of the API's. That's harmless in
 * production (one combined Flask-served origin), but breaks locally,
 * where the Vite dev server (5173) and Flask (5001) are different
 * origins -- exactly the scenario BASE_URL exists to handle everywhere
 * else. A scraped photo_url is already an absolute external URL and must
 * be left untouched (prepending BASE_URL to an absolute URL would mangle
 * it), so only same-origin-relative paths get the prefix.
 */
export function resolvePhotoUrl(photoUrl: string | null): string | undefined {
  if (!photoUrl) return undefined;
  return photoUrl.startsWith("/") ? `${BASE_URL}${photoUrl}` : photoUrl;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  // FormData bodies (file uploads) must NOT get a manual Content-Type --
  // the browser sets one itself with the correct multipart boundary. JSON
  // bodies (everything else) do need it set explicitly.
  const isFormData = options.body instanceof FormData;

  const response = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    ...options,
    headers: isFormData ? options.headers : { "Content-Type": "application/json", ...options.headers },
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

/**
 * Fallback for sites that block Yarnboard's automatic fetch (e.g.
 * Cloudflare's bot-detection challenge): the user saves the page's HTML
 * themselves and uploads it here instead. `url` is still required -- it's
 * what dedup and attribution are based on -- only the page content itself
 * comes from the upload rather than a server-side fetch.
 */
export function previewPatternFromUpload(url: string, htmlFile: File) {
  const formData = new FormData();
  formData.append("url", url);
  formData.append("html_file", htmlFile);
  return request<PreviewResponse>("/api/patterns/preview-upload", {
    method: "POST",
    body: formData,
  });
}

/**
 * Upload (or replace) the photo on an already-published pattern -- works
 * for a pattern that already had a scraped or previously-uploaded photo,
 * or one that never had any. Always replaces whatever was there before
 * (see Pattern.to_dict's priority rule in models.py).
 */
export function uploadPatternPhoto(patternId: number, photo: File) {
  const formData = new FormData();
  formData.append("photo", photo);
  return request<{ message: string; pattern: Pattern }>(`/api/patterns/${patternId}/photo`, {
    method: "POST",
    body: formData,
  });
}

/** Removes this pattern's photo entirely, regardless of whether it was
 * scraped or manually uploaded. */
export function deletePatternPhoto(patternId: number) {
  return request<{ message: string; pattern: Pattern }>(`/api/patterns/${patternId}/photo`, {
    method: "DELETE",
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

/** Edit an already-published pattern. 403s if the current user is neither
 * an admin nor the original uploader (backend-enforced; see _can_edit in
 * patterns/routes.py). */
export function updatePattern(patternId: number, payload: PatternEditPayload) {
  return request<{ message: string; pattern: Pattern }>(`/api/patterns/${patternId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/** Patterns the current user has stale (now-outdated) checklist progress
 * on -- drives the in-app "this pattern changed" banner. */
export function fetchNotifications() {
  return request<PatternNotification[]>("/api/patterns/notifications");
}

/** Dismisses the banner for one pattern, clearing this user's stale
 * progress on it immediately. Safe to call even if it's no longer stale
 * (e.g. already cleared by toggling a checkbox) -- the backend no-ops. */
export function acknowledgePatternUpdate(patternId: number) {
  return request<{ message: string }>(`/api/patterns/${patternId}/acknowledge-update`, {
    method: "POST",
  });
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

// --- Stitch Fiddle chart import -----------------------------------------

export function fetchStitchFiddleLinks() {
  return request<StitchFiddleLink[]>("/api/stitch-fiddle/links");
}

export function saveStitchFiddleLink(shareUrl: string) {
  return request<StitchFiddleLink>("/api/stitch-fiddle/links", {
    method: "POST",
    body: JSON.stringify({ share_url: shareUrl }),
  });
}

export function deleteStitchFiddleLink(linkId: number) {
  return request<{ message: string }>(`/api/stitch-fiddle/links/${linkId}`, {
    method: "DELETE",
  });
}

/** Fetches the chart from Stitch Fiddle (slow -- launches a real headless
 * browser server-side) and turns it into a Pattern, or returns the
 * existing one if this link was already imported. */
export function importStitchFiddleLink(linkId: number) {
  return request<{ message: string; pattern: Pattern }>(
    `/api/stitch-fiddle/links/${linkId}/import`,
    { method: "POST" },
  );
}
