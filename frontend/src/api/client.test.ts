import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchProfile, login, previewPatternFromUpload } from "./client";

function stubFetchResolvingTo(response: Partial<Response> & { json: () => Promise<unknown> }) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client request wrapper", () => {
  it("stringifies JSON bodies and sets a JSON Content-Type header", async () => {
    const fetchMock = stubFetchResolvingTo({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ message: "Login successful", username: "jane" }),
    });

    await login("jane@example.com", "hunter2222");

    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(JSON.parse(options.body)).toEqual({ email: "jane@example.com", password: "hunter2222" });
  });

  it("leaves FormData bodies (file uploads) without a manual Content-Type header", async () => {
    stubFetchResolvingTo({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ duplicate: false, existing_pattern_id: null, draft: null }),
    });
    const fetchMock = vi.mocked(fetch);
    const file = new File(["<html></html>"], "pattern.html", { type: "text/html" });

    await previewPatternFromUpload("https://example.com/pattern", file);

    const [, options] = fetchMock.mock.calls[0];
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.headers).toBeUndefined();
  });

  it("throws an ApiError carrying the response status and the backend's error message", async () => {
    stubFetchResolvingTo({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      json: () => Promise.resolve({ error: "You don't have permission to edit this pattern." }),
    });

    await expect(fetchProfile()).rejects.toBeInstanceOf(ApiError);
    await expect(fetchProfile()).rejects.toMatchObject({
      status: 403,
      message: "You don't have permission to edit this pattern.",
    });
  });

  it("falls back to the response's statusText when the error body isn't valid JSON", async () => {
    stubFetchResolvingTo({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("not json")),
    });

    await expect(fetchProfile()).rejects.toMatchObject({
      status: 500,
      message: "Internal Server Error",
    });
  });
});
