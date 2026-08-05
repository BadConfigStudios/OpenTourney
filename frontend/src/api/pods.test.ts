import { describe, expect, it, vi } from "vitest";
import { createPod, listPodsForEvent } from "./pods";

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
});
