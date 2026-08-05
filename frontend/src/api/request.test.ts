import { describe, expect, it, vi } from "vitest";
import { apiRequest, ApiError, jsonInit } from "./request";

function fetchReturning(response: { ok: boolean; status: number; statusText?: string; json?: () => Promise<unknown> }) {
  return vi.fn().mockResolvedValue(response);
}

describe("apiRequest", () => {
  it("parses a successful JSON response", async () => {
    const apiFetch = fetchReturning({ ok: true, status: 200, json: () => Promise.resolve({ id: "1" }) });

    const result = await apiRequest(apiFetch, "/events");

    expect(result).toEqual({ id: "1" });
    expect(apiFetch).toHaveBeenCalledWith("/events", undefined);
  });

  it("returns undefined for a 204 No Content response", async () => {
    const apiFetch = fetchReturning({ ok: true, status: 204 });

    const result = await apiRequest(apiFetch, "/entries/1", { method: "DELETE" });

    expect(result).toBeUndefined();
  });

  it("throws ApiError with the backend detail on a non-2xx response", async () => {
    const apiFetch = fetchReturning({
      ok: false,
      status: 422,
      statusText: "Unprocessable Entity",
      json: () => Promise.resolve({ detail: "date is required" }),
    });

    await expect(apiRequest(apiFetch, "/events", jsonInit("POST", {}))).rejects.toMatchObject({
      status: 422,
      message: "date is required",
    });
  });

  it("builds a readable message from FastAPI's array-shaped validation detail", async () => {
    const apiFetch = fetchReturning({
      ok: false,
      status: 422,
      statusText: "Unprocessable Content",
      json: () =>
        Promise.resolve({
          detail: [{ loc: ["body", "date"], msg: "field required", type: "missing" }],
        }),
    });

    const error = await apiRequest(apiFetch, "/events", jsonInit("POST", {})).catch((error: unknown) => error);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(422);
    expect((error as ApiError).message).not.toBe("Unprocessable Content");
    expect((error as ApiError).message).toContain("field required");
  });

  it("falls back to statusText when the error body isn't JSON", async () => {
    const apiFetch = fetchReturning({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("not json")),
    });

    await expect(apiRequest(apiFetch, "/events")).rejects.toMatchObject({
      status: 500,
      message: "Internal Server Error",
    });
  });

  it("ApiError instances are real Errors", async () => {
    const apiFetch = fetchReturning({ ok: false, status: 404, statusText: "Not Found" });

    await expect(apiRequest(apiFetch, "/events/1")).rejects.toBeInstanceOf(ApiError);
    await expect(apiRequest(apiFetch, "/events/1")).rejects.toBeInstanceOf(Error);
  });
});

describe("jsonInit", () => {
  it("builds a JSON request init", () => {
    expect(jsonInit("POST", { date: "2026-08-01" })).toEqual({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: "2026-08-01" }),
    });
  });
});
