import { describe, expect, it, vi } from "vitest";
import { createEvent, getEvent, listEvents } from "./events";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("events api", () => {
  it("listEvents GETs /events", async () => {
    const apiFetch = fetchReturning([{ id: "1", date: "2026-08-01" }]);

    expect(await listEvents(apiFetch)).toEqual([{ id: "1", date: "2026-08-01" }]);
    expect(apiFetch).toHaveBeenCalledWith("/events", undefined);
  });

  it("getEvent GETs /events/:id", async () => {
    const apiFetch = fetchReturning({ id: "1", date: "2026-08-01" });

    expect(await getEvent(apiFetch, "1")).toEqual({ id: "1", date: "2026-08-01" });
    expect(apiFetch).toHaveBeenCalledWith("/events/1", undefined);
  });

  it("createEvent POSTs the date", async () => {
    const apiFetch = fetchReturning({ id: "1", date: "2026-08-01" }, 201);

    expect(await createEvent(apiFetch, "2026-08-01")).toEqual({ id: "1", date: "2026-08-01" });
    expect(apiFetch).toHaveBeenCalledWith("/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: "2026-08-01" }),
    });
  });
});
