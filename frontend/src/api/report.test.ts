import { describe, expect, it, vi } from "vitest";
import { fetchPodReport } from "./report";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("report api", () => {
  it("fetchPodReport GETs /pods/:id/report", async () => {
    const apiFetch = fetchReturning({
      is_complete: false,
      rounds_played: 2,
      is_partial: true,
      standings: [{ entry_id: "e1", points: 6, rank: 1, tiebreakers: [0.75, 0.5] }],
    });

    const report = await fetchPodReport(apiFetch, "pod-1");

    expect(report).toEqual({
      is_complete: false,
      rounds_played: 2,
      is_partial: true,
      standings: [{ entry_id: "e1", points: 6, rank: 1, tiebreakers: [0.75, 0.5] }],
    });
    expect(apiFetch).toHaveBeenCalledWith("/pods/pod-1/report", undefined);
  });
});
