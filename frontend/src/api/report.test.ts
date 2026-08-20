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
      active_entry_count: 1,
      recommended_rounds: 3,
      standings: [
        {
          entry_id: "e1",
          points: 6,
          rank: 1,
          tiebreakers: [
            { label: "OMW%", value: 0.75, format: "percent" },
            { label: "OOMW%", value: 0.5, format: "percent" },
          ],
        },
      ],
    });

    const report = await fetchPodReport(apiFetch, "pod-1");

    expect(report.standings[0].tiebreakers).toEqual([
      { label: "OMW%", value: 0.75, format: "percent" },
      { label: "OOMW%", value: 0.5, format: "percent" },
    ]);
    expect(apiFetch).toHaveBeenCalledWith("/pods/pod-1/report", undefined);
  });
});
