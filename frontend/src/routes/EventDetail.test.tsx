import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { EventDetail } from "./EventDetail";

const EVENT = { id: "event-1", date: "2026-08-01", name: "Friday Standard", description: null, organization_id: "org-1" };
const POD = { id: "pod-1", event_id: "event-1", format_slug: "swiss", game_slug: "generic", completed_at: null };

function renderDetail(personaLabel?: string) {
  renderWithProviders(<EventDetail />, {
    path: "/events/event-1",
    routePath: "/events/:eventId",
    personaLabel,
  });
}

describe("EventDetail", () => {
  beforeEach(() => localStorage.clear());

  it("shows a Create Pod action when the event has no pod", async () => {
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json([])),
    );

    renderDetail();

    expect(await screen.findByText("This event has no pod yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Pod" })).toBeInTheDocument();
  });

  it("creates a pod with the default format/game slugs and then shows the roster", async () => {
    // Stateful handler: the component invalidates and refetches GET /pods
    // after the mutation, so a static handler would mask a broken create by
    // just re-serving the original (empty) list.
    let pods: (typeof POD)[] = [];
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json(pods)),
      http.post("/pods", async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({ event_id: "event-1", format_slug: "swiss", game_slug: "generic" });
        pods = [POD];
        return HttpResponse.json(POD, { status: 201 });
      }),
      http.get("/entries", () => HttpResponse.json([])),
    );

    renderDetail();
    fireEvent.click(await screen.findByRole("button", { name: "Create Pod" }));

    expect(await screen.findByText("No entries yet.")).toBeInTheDocument();
  });

  it("renders the entry roster once a pod exists", async () => {
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json([POD])),
      http.get("/entries", () =>
        HttpResponse.json([
          { id: "e1", pod_id: "pod-1", player_uuid: "u1", source_system: "opentourney-ui", metadata: { display_name: "Ash" } },
        ]),
      ),
    );

    renderDetail();

    expect(await screen.findByText("Ash")).toBeInTheDocument();
  });

  it("hides Create Pod for a non-Organizer persona", async () => {
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json([])),
    );

    renderDetail("Player");

    await screen.findByText("This event has no pod yet.");
    expect(screen.queryByRole("button", { name: "Create Pod" })).not.toBeInTheDocument();
  });

  it("links to the pairings screen once a pod exists", async () => {
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json([POD])),
      http.get("/entries", () => HttpResponse.json([])),
    );

    renderDetail();

    expect(await screen.findByRole("link", { name: "View Pairings" })).toHaveAttribute(
      "href",
      "/pods/pod-1/pairings",
    );
  });

  it("links to the report screen once a pod exists", async () => {
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json([POD])),
      http.get("/entries", () => HttpResponse.json([])),
    );

    renderDetail();

    expect(await screen.findByRole("link", { name: "View Report" })).toHaveAttribute(
      "href",
      "/pods/pod-1/report",
    );
  });
});
