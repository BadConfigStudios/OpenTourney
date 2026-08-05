import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { Pairings } from "./Pairings";

const ENTRIES = [
  {
    id: "e1",
    pod_id: "pod-1",
    player_uuid: "u1",
    source_system: "opentourney-ui",
    metadata: { display_name: "Ash" },
  },
  {
    id: "e2",
    pod_id: "pod-1",
    player_uuid: "u2",
    source_system: "opentourney-ui",
    metadata: { display_name: "Misty" },
  },
];

const ROUND_1 = {
  id: "r1",
  pod_id: "pod-1",
  number: 1,
  matches: [
    {
      id: "m1",
      round_id: "r1",
      entry1_id: "e1",
      entry2_id: "e2",
      result: "entry1_win",
      reported_by: "opentourney-ui:organizer-uuid",
      witnessed_by: "opentourney-ui:organizer-uuid",
      table_number: 1,
      method: "manual_entry",
    },
  ],
};

export const ROUND_2 = {
  id: "r2",
  pod_id: "pod-1",
  number: 2,
  matches: [
    {
      id: "m2",
      round_id: "r2",
      entry1_id: "e1",
      entry2_id: null,
      result: "unreported",
      reported_by: null,
      witnessed_by: null,
      table_number: null,
      method: "manual_entry",
    },
  ],
};

function renderPairings(personaLabel?: string) {
  renderWithProviders(<Pairings />, {
    path: "/pods/pod-1/pairings",
    routePath: "/pods/:podId/pairings",
    personaLabel,
  });
}

describe("Pairings", () => {
  it("shows the latest round's pairings by default, with entry names and table numbers", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1, ROUND_2])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderPairings();

    expect(await screen.findByText(/Ash — \(bye\)/)).toBeInTheDocument();
  });

  it("shows a past round's matches, read-only, when selected from round history", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1, ROUND_2])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderPairings();
    await screen.findByText(/Ash — \(bye\)/);

    fireEvent.click(screen.getByRole("button", { name: "Round 1" }));

    expect(await screen.findByText(/Table 1: Ash vs Misty/)).toBeInTheDocument();
  });

  it("shows a message when no rounds have been generated yet", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderPairings();

    expect(await screen.findByText("No rounds generated yet.")).toBeInTheDocument();
  });
});
