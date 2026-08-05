import { describe, expect, it, vi } from "vitest";
import { fetchRounds, generateRound } from "./rounds";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("rounds api", () => {
  it("fetchRounds GETs /pods/:id/rounds", async () => {
    const apiFetch = fetchReturning([]);

    await fetchRounds(apiFetch, "pod-1");

    expect(apiFetch).toHaveBeenCalledWith("/pods/pod-1/rounds", undefined);
  });

  it("generateRound POSTs /pods/:id/rounds with no body", async () => {
    const apiFetch = fetchReturning({ id: "r1" }, 201);

    await generateRound(apiFetch, "pod-1");

    expect(apiFetch).toHaveBeenCalledWith("/pods/pod-1/rounds", { method: "POST" });
  });
});
