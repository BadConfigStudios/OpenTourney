import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { Report } from "./Report";

const ENTRIES = [
  { id: "e1", pod_id: "pod-1", player_uuid: "u1", source_system: "opentourney-ui", metadata: { display_name: "Ash" } },
  { id: "e2", pod_id: "pod-1", player_uuid: "u2", source_system: "opentourney-ui", metadata: { display_name: "Misty" } },
];

const COMPLETE_REPORT = {
  is_complete: true,
  rounds_played: 2,
  is_partial: false,
  standings: [
    { entry_id: "e1", points: 6, rank: 1 },
    { entry_id: "e2", points: 3, rank: 2 },
  ],
};

function renderReport(personaLabel?: string) {
  renderWithProviders(<Report />, {
    path: "/pods/pod-1/report",
    routePath: "/pods/:podId/report",
    personaLabel,
  });
}

describe("Report", () => {
  it("shows ranked standings with entry names and points", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json(COMPLETE_REPORT)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    const rows = await screen.findAllByRole("row");
    // rows[0] is the header row.
    expect(rows[1]).toHaveTextContent("1");
    expect(rows[1]).toHaveTextContent("Ash");
    expect(rows[1]).toHaveTextContent("6");
    expect(rows[2]).toHaveTextContent("2");
    expect(rows[2]).toHaveTextContent("Misty");
    expect(rows[2]).toHaveTextContent("3");
  });

  it("shows a partial-round banner when is_partial is true", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json({ ...COMPLETE_REPORT, is_partial: true })),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    expect(await screen.findByText(/standings reflect completed rounds only/)).toBeInTheDocument();
  });

  it("shows a not-yet-complete banner when is_complete is false", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json({ ...COMPLETE_REPORT, is_complete: false })),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    expect(await screen.findByText(/not yet completed/)).toBeInTheDocument();
  });

  it("shows neither banner once the pod is complete and not partial", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json(COMPLETE_REPORT)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();
    await screen.findByText("Ash");

    expect(screen.queryByText(/standings reflect completed rounds only/)).not.toBeInTheDocument();
    expect(screen.queryByText(/not yet completed/)).not.toBeInTheDocument();
  });

  it("lets the Organizer complete the pod when the report isn't partial", async () => {
    let completed = false;
    server.use(
      http.get("/pods/pod-1/report", () =>
        HttpResponse.json({ ...COMPLETE_REPORT, is_complete: completed }),
      ),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      http.post("/pods/pod-1/complete", () => {
        completed = true;
        return HttpResponse.json({ id: "pod-1", event_id: "event-1", format_slug: "swiss", game_slug: "generic", completed_at: "2026-08-05T12:00:00Z" });
      }),
    );

    renderReport();
    fireEvent.click(await screen.findByRole("button", { name: "Complete Pod" }));

    expect(await screen.findByRole("button", { name: "Complete Pod" })).toBeDisabled();
  });

  it("disables Complete Pod when the report is partial", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json({ ...COMPLETE_REPORT, is_complete: false, is_partial: true })),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    expect(await screen.findByRole("button", { name: "Complete Pod" })).toBeDisabled();
  });

  it("hides Complete Pod for non-Organizer personas", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json({ ...COMPLETE_REPORT, is_complete: false })),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport("Player");

    await screen.findByText("Ash");
    expect(screen.queryByRole("button", { name: "Complete Pod" })).not.toBeInTheDocument();
  });
});
