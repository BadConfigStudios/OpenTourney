import { describe, expect, it, vi } from "vitest";
import { createEvent, getEvent, listEvents } from "./events";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

const EVENT_FIXTURE = {
  id: "1",
  date: "2026-08-01",
  name: "Friday Standard",
  description: null,
  organization_id: "org-1",
};

describe("events api", () => {
  it("listEvents GETs /events", async () => {
    const apiFetch = fetchReturning([EVENT_FIXTURE]);

    expect(await listEvents(apiFetch)).toEqual([EVENT_FIXTURE]);
    expect(apiFetch).toHaveBeenCalledWith("/events", undefined);
  });

  it("getEvent GETs /events/:id", async () => {
    const apiFetch = fetchReturning(EVENT_FIXTURE);

    expect(await getEvent(apiFetch, "1")).toEqual(EVENT_FIXTURE);
    expect(apiFetch).toHaveBeenCalledWith("/events/1", undefined);
  });

  it("createEvent POSTs date, name, organization_id, and optional description", async () => {
    const apiFetch = fetchReturning(EVENT_FIXTURE, 201);

    await createEvent(apiFetch, "2026-08-01", "Friday Standard", "org-1");

    expect(apiFetch).toHaveBeenCalledWith("/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        date: "2026-08-01",
        name: "Friday Standard",
        description: undefined,
        organization_id: "org-1",
      }),
    });
  });

  it("createEvent includes description when provided", async () => {
    const apiFetch = fetchReturning(EVENT_FIXTURE, 201);

    await createEvent(apiFetch, "2026-08-01", "Friday Standard", "org-1", "Weekly league night");

    expect(apiFetch).toHaveBeenCalledWith(
      "/events",
      expect.objectContaining({
        body: JSON.stringify({
          date: "2026-08-01",
          name: "Friday Standard",
          description: "Weekly league night",
          organization_id: "org-1",
        }),
      }),
    );
  });
});
