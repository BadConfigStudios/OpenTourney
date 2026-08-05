import { describe, expect, it, vi } from "vitest";
import { reportMatchResult } from "./matches";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("matches api", () => {
  it("reportMatchResult POSTs the result with a fixed manual_entry method", async () => {
    const apiFetch = fetchReturning({ id: "m1" });

    await reportMatchResult(apiFetch, "m1", "entry1_win");

    expect(apiFetch).toHaveBeenCalledWith("/matches/m1/result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result: "entry1_win", method: "manual_entry" }),
    });
  });
});
