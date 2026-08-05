import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import type { RoundRead } from "../api/rounds";
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

const ROUND_1: RoundRead = {
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

export const ROUND_2: RoundRead = {
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

const ROUND_3_UNREPORTED = {
  id: "r3",
  pod_id: "pod-1",
  number: 3,
  matches: [
    {
      id: "m3",
      round_id: "r3",
      entry1_id: "e1",
      entry2_id: "e2",
      result: "unreported",
      reported_by: null,
      witnessed_by: null,
      table_number: 1,
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
  // renderPairings() with no personaLabel relies on the AuthProvider's default
  // (persona[0], "Organizer") — but persona selection is persisted to
  // localStorage, so an earlier test's explicit renderPairings("Scorekeeper"/"Player")
  // would otherwise leak into later default-persona tests. Reset between tests.
  afterEach(() => {
    localStorage.clear();
  });

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

  it("lets the Organizer report a result via inline buttons", async () => {
    let matches = [{ ...ROUND_3_UNREPORTED.matches[0] }];
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([{ ...ROUND_3_UNREPORTED, matches }])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      http.post("/matches/m3/result", async ({ request }) => {
        const body = (await request.json()) as { result: string };
        matches = [{ ...matches[0], result: body.result }];
        return HttpResponse.json(matches[0]);
      }),
    );

    renderPairings();
    fireEvent.click(await screen.findByRole("button", { name: "Ash wins" }));

    expect(await screen.findByText(/entry1_win/)).toBeInTheDocument();
  });

  it("shows result buttons for the Scorekeeper persona too", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_3_UNREPORTED])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderPairings("Scorekeeper");

    expect(await screen.findByRole("button", { name: "Ash wins" })).toBeInTheDocument();
  });

  it("hides result buttons for the Player persona", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_3_UNREPORTED])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderPairings("Player");

    await screen.findByText(/Table 1: Ash vs Misty/);
    expect(screen.queryByRole("button", { name: "Ash wins" })).not.toBeInTheDocument();
  });

  it("shows an already-reported match's result as text instead of buttons", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderPairings();

    expect(await screen.findByText(/entry1_win/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ash wins" })).not.toBeInTheDocument();
  });

  it("hides result buttons on a past round even for the Organizer", async () => {
    const pastUnreported = { ...ROUND_3_UNREPORTED, number: 1 };
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([pastUnreported, ROUND_2])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderPairings();
    await screen.findByText(/Ash — \(bye\)/);

    fireEvent.click(screen.getByRole("button", { name: "Round 1" }));

    await screen.findByText(/Table 1: Ash vs Misty/);
    expect(screen.queryByRole("button", { name: "Ash wins" })).not.toBeInTheDocument();
  });

  it("lets the Organizer generate the next round and auto-selects it", async () => {
    let rounds: RoundRead[] = [ROUND_1];
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json(rounds)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      http.post("/pods/pod-1/rounds", () => {
        rounds = [...rounds, ROUND_2];
        return HttpResponse.json(ROUND_2, { status: 201 });
      }),
    );

    renderPairings();
    await screen.findByText(/Table 1: Ash vs Misty/);

    fireEvent.click(screen.getByRole("button", { name: "Generate Next Round" }));

    expect(await screen.findByText(/Ash — \(bye\)/)).toBeInTheDocument();
  });

  it("disables Generate Next Round while the latest round has an unreported match", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_3_UNREPORTED])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderPairings();

    expect(await screen.findByRole("button", { name: "Generate Next Round" })).toBeDisabled();
  });

  it("hides Generate Next Round for non-Organizer personas", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderPairings("Scorekeeper");

    await screen.findByText(/Table 1: Ash vs Misty/);
    expect(screen.queryByRole("button", { name: "Generate Next Round" })).not.toBeInTheDocument();
  });
});
