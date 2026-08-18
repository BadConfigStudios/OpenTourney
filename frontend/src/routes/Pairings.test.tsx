import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import type { RoundRead } from "../api/rounds";
import type { MatchResult } from "../api/matches";
import type { PersonaRole } from "../config/types";
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

const ROUND_2: RoundRead = {
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

const ROUND_3_UNREPORTED: RoundRead = {
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

function reportHandler() {
  return http.get("/pods/pod-1/report", () =>
    HttpResponse.json({
      is_complete: false,
      rounds_played: 0,
      is_partial: false,
      active_entry_count: 2,
      recommended_rounds: 1,
      standings: [],
    }),
  );
}

function renderPairings(role?: PersonaRole) {
  renderWithProviders(<Pairings />, {
    path: "/pods/pod-1/pairings",
    routePath: "/pods/:podId/pairings",
    role,
  });
}

describe("Pairings", () => {
  // renderPairings() with no role relies on renderWithProviders' default
  // ("organizer") — each call builds a fresh fake UserManager for the given
  // role, so an earlier test's explicit renderPairings("scorekeeper"/"player")
  // never leaks into later default-role tests.

  it("shows the latest round's pairings by default, with entry names and table numbers", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1, ROUND_2])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      reportHandler(),
    );

    renderPairings();

    expect(await screen.findByText(/Ash — \(bye\)/)).toBeInTheDocument();
  });

  it("shows a past round's matches, read-only, when selected from round history", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1, ROUND_2])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      reportHandler(),
    );

    renderPairings();
    await screen.findByText(/Ash — \(bye\)/);

    fireEvent.click(screen.getByRole("button", { name: "Round 1" }));

    expect(await screen.findByText(/Table 1: Ash vs Misty/)).toBeInTheDocument();
  });

  it("indicates which round is currently selected after clicking a round-history button", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1, ROUND_2])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      reportHandler(),
    );

    renderPairings();
    await screen.findByText(/Ash — \(bye\)/);
    expect(await screen.findByRole("heading", { name: "Round 2" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Round 2" })).toHaveAttribute("aria-current", "true");

    fireEvent.click(screen.getByRole("button", { name: "Round 1" }));

    expect(await screen.findByRole("heading", { name: "Round 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Round 1" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: "Round 2" })).toHaveAttribute("aria-current", "false");
  });

  it("shows a message when no rounds have been generated yet", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      reportHandler(),
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
        const body = (await request.json()) as { result: MatchResult };
        matches = [{ ...matches[0], result: body.result }];
        return HttpResponse.json(matches[0]);
      }),
      reportHandler(),
    );

    renderPairings();
    fireEvent.click(await screen.findByRole("button", { name: "Ash wins" }));

    expect(await screen.findByText(/Ash won/)).toBeInTheDocument();
  });

  it("shows result buttons for the Scorekeeper persona too", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_3_UNREPORTED])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      reportHandler(),
    );

    renderPairings("scorekeeper");

    expect(await screen.findByRole("button", { name: "Ash wins" })).toBeInTheDocument();
  });

  it("hides result buttons for the Player persona", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_3_UNREPORTED])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      reportHandler(),
    );

    renderPairings("player");

    await screen.findByText(/Table 1: Ash vs Misty/);
    expect(screen.queryByRole("button", { name: "Ash wins" })).not.toBeInTheDocument();
  });

  it("shows an already-reported match's result as text instead of buttons", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      reportHandler(),
    );

    renderPairings();

    expect(await screen.findByText(/Ash won/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ash wins" })).not.toBeInTheDocument();
  });

  it("hides result buttons on a past round even for the Organizer", async () => {
    const pastUnreported = { ...ROUND_3_UNREPORTED, number: 1 };
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([pastUnreported, ROUND_2])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      reportHandler(),
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
      reportHandler(),
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
      reportHandler(),
    );

    renderPairings();

    expect(await screen.findByRole("button", { name: "Generate Next Round" })).toBeDisabled();
  });

  it("hides Generate Next Round for non-Organizer personas", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      reportHandler(),
    );

    renderPairings("scorekeeper");

    await screen.findByText(/Table 1: Ash vs Misty/);
    expect(screen.queryByRole("button", { name: "Generate Next Round" })).not.toBeInTheDocument();
  });

  it("shows the recommended round count", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1, ROUND_2])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      http.get("/pods/pod-1/report", () =>
        HttpResponse.json({
          is_complete: false,
          rounds_played: 2,
          is_partial: false,
          active_entry_count: 2,
          recommended_rounds: 1,
          standings: [],
        }),
      ),
    );

    renderPairings();

    expect(await screen.findByText(/Recommended rounds: 1/)).toBeInTheDocument();
  });

  it("shows a banner when the recommended round count changes after generating a round", async () => {
    let rounds: RoundRead[] = [ROUND_1];
    let reportFetchCount = 0;
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json(rounds)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      http.post("/pods/pod-1/rounds", () => {
        rounds = [...rounds, ROUND_2];
        return HttpResponse.json(ROUND_2, { status: 201 });
      }),
      http.get("/pods/pod-1/report", () => {
        reportFetchCount += 1;
        const active = reportFetchCount === 1 ? 2 : 1;
        return HttpResponse.json({
          is_complete: false,
          rounds_played: rounds.length,
          is_partial: false,
          active_entry_count: active,
          recommended_rounds: active <= 1 ? 0 : 1,
          standings: [],
        });
      }),
    );

    renderPairings();
    await screen.findByText(/Recommended rounds: 1/);

    fireEvent.click(screen.getByRole("button", { name: "Generate Next Round" }));

    expect(await screen.findByText(/Round target changed from 1 to 0/)).toBeInTheDocument();
  });
});
