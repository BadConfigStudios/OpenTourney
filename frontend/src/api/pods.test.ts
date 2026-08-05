import { describe, expect, it, vi } from "vitest";
import { completePod, createPod, listPodsForEvent } from "./pods";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("pods api", () => {
  it("listPodsForEvent GETs /pods?event_id=", async () => {
    const apiFetch = fetchReturning([
      { id: "p1", event_id: "e1", format_slug: "swiss", game_slug: "generic", completed_at: null },
    ]);

    const pods = await listPodsForEvent(apiFetch, "e1");

    expect(pods).toEqual([
      { id: "p1", event_id: "e1", format_slug: "swiss", game_slug: "generic", completed_at: null },
    ]);
    expect(apiFetch).toHaveBeenCalledWith("/pods?event_id=e1", undefined);
  });

  it("createPod POSTs the fixed swiss/generic slugs", async () => {
    const apiFetch = fetchReturning(
      { id: "p1", event_id: "e1", format_slug: "swiss", game_slug: "generic", completed_at: null },
      201,
    );

    await createPod(apiFetch, "e1");

    expect(apiFetch).toHaveBeenCalledWith("/pods", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: "e1", format_slug: "swiss", game_slug: "generic" }),
    });
  });

  it("completePod POSTs /pods/:id/complete", async () => {
    const apiFetch = fetchReturning({
      id: "p1",
      event_id: "e1",
      format_slug: "swiss",
      game_slug: "generic",
      completed_at: "2026-08-05T12:00:00Z",
    });

    const pod = await completePod(apiFetch, "p1");

    expect(pod.completed_at).toBe("2026-08-05T12:00:00Z");
    expect(apiFetch).toHaveBeenCalledWith("/pods/p1/complete", { method: "POST" });
  });
});
