import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import type { PersonaRole } from "../config/types";
import { Report } from "./Report";

const ENTRIES = [
  { id: "e1", pod_id: "pod-1", player_uuid: "u1", source_system: "opentourney-ui", metadata: { display_name: "Ash" } },
  { id: "e2", pod_id: "pod-1", player_uuid: "u2", source_system: "opentourney-ui", metadata: { display_name: "Misty" } },
];

const COMPLETE_REPORT = {
  is_complete: true,
  rounds_played: 2,
  is_partial: false,
  active_entry_count: 2,
  recommended_rounds: 3,
  standings: [
    { entry_id: "e1", points: 6, rank: 1, tiebreakers: [0.75, 0.5] },
    { entry_id: "e2", points: 3, rank: 2, tiebreakers: [0.415, 0.4] },
  ],
};

function renderReport(role?: PersonaRole) {
  renderWithProviders(<Report />, {
    path: "/pods/pod-1/report",
    routePath: "/pods/:podId/report",
    role,
  });
}

describe("Report", () => {
  beforeEach(() => {
    server.use(
      http.get("/pods/pod-1", () =>
        HttpResponse.json({
          id: "pod-1",
          event_id: "event-1",
          format_slug: "swiss",
          game_slug: "generic",
          completed_at: null,
        }),
      ),
    );
  });

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

  it("shows OMW%/OOMW% columns", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json(COMPLETE_REPORT)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    const rows = await screen.findAllByRole("row");
    expect(rows[0]).toHaveTextContent("OMW%");
    expect(rows[0]).toHaveTextContent("OOMW%");
    expect(rows[1]).toHaveTextContent("75.0%");
    expect(rows[1]).toHaveTextContent("50.0%");
    expect(rows[2]).toHaveTextContent("41.5%");
    expect(rows[2]).toHaveTextContent("40.0%");
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

    renderReport("player");

    await screen.findByText("Ash");
    expect(screen.queryByRole("button", { name: "Complete Pod" })).not.toBeInTheDocument();
  });

  it("hides Complete Pod for the Scorekeeper persona", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json({ ...COMPLETE_REPORT, is_complete: false })),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport("scorekeeper");

    await screen.findByText("Ash");
    expect(screen.queryByRole("button", { name: "Complete Pod" })).not.toBeInTheDocument();
  });

  it("shows a message instead of a table when there are no standings yet", async () => {
    server.use(
      http.get("/pods/pod-1/report", () =>
        HttpResponse.json({ is_complete: false, rounds_played: 0, is_partial: false, active_entry_count: 0, recommended_rounds: 3, standings: [] }),
      ),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    expect(await screen.findByText("No standings yet.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("row")).toHaveLength(0);
  });

  it("surfaces an error banner when the report request fails", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json({ detail: "pod not found" }, { status: 404 })),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    expect(await screen.findByRole("alert")).toHaveTextContent("pod not found");
  });

  it("surfaces an error banner when Complete Pod fails with a 409", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json({ ...COMPLETE_REPORT, is_complete: false })),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      http.post("/pods/pod-1/complete", () =>
        HttpResponse.json(
          { detail: "round 2 has an unreported match; cannot complete pod" },
          { status: 409 },
        ),
      ),
    );

    renderReport();
    fireEvent.click(await screen.findByRole("button", { name: "Complete Pod" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "round 2 has an unreported match; cannot complete pod",
    );
  });

  it("shows a Bo1-by-default note for a Pokemon pod", async () => {
    server.use(
      http.get("/pods/pod-1", () =>
        HttpResponse.json({
          id: "pod-1",
          event_id: "event-1",
          format_slug: "swiss",
          game_slug: "pokemon-tcg",
          completed_at: null,
        }),
      ),
      http.get("/pods/pod-1/report", () => HttpResponse.json(COMPLETE_REPORT)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    expect(await screen.findByText(/best-of-1 by default/)).toBeInTheDocument();
  });

  it("hides the Bo1-by-default note for a non-Pokemon pod", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json(COMPLETE_REPORT)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();
    await screen.findByText("Ash");

    expect(screen.queryByText(/best-of-1 by default/)).not.toBeInTheDocument();
  });
});
