import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { displayNameFor, listEntries, type EntryRead } from "../api/entries";
import { reportMatchResult, type MatchRead } from "../api/matches";
import { fetchPodReport } from "../api/report";
import { fetchRounds, generateRound } from "../api/rounds";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

function resultLabelFor(match: MatchRead, entries: EntryRead[] | undefined): string {
  if (match.result === "tie") return "Tie";
  if (match.result === "entry1_win") return `${displayNameFor(entries, match.entry1_id)} won`;
  if (match.result === "entry2_win" && match.entry2_id) {
    return `${displayNameFor(entries, match.entry2_id)} won`;
  }
  return match.result;
}

export function Pairings() {
  const { podId } = useParams<{ podId: string }>();
  if (!podId) throw new Error("Pairings rendered without a podId route param");

  const { apiFetch, currentPersona } = useAuth();
  const queryClient = useQueryClient();
  const canReport = currentPersona.role === "organizer" || currentPersona.role === "scorekeeper";
  const [selectedRoundNumber, setSelectedRoundNumber] = useState<number | null>(null);

  const roundsQuery = useQuery({
    queryKey: ["rounds", podId],
    queryFn: () => fetchRounds(apiFetch, podId),
  });
  const entriesQuery = useQuery({
    queryKey: ["entries", podId],
    queryFn: () => listEntries(apiFetch, podId),
  });
  const reportQuery = useQuery({
    queryKey: ["report", podId],
    queryFn: () => fetchPodReport(apiFetch, podId),
  });

  const reportMutation = useMutation({
    mutationFn: (args: { matchId: string; result: "entry1_win" | "entry2_win" | "tie" }) =>
      reportMatchResult(apiFetch, args.matchId, args.result),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rounds", podId] }),
  });

  const rounds = roundsQuery.data ?? [];
  const latestRound = rounds[rounds.length - 1];

  const isOrganizer = currentPersona.role === "organizer";
  const latestRoundHasUnreportedMatch =
    latestRound?.matches.some((match) => match.entry2_id !== null && match.result === "unreported") ?? false;

  const generateMutation = useMutation({
    mutationFn: () => generateRound(apiFetch, podId),
    onSuccess: (newRound) => {
      queryClient.invalidateQueries({ queryKey: ["rounds", podId] });
      queryClient.invalidateQueries({ queryKey: ["report", podId] });
      setSelectedRoundNumber(newRound.number);
    },
  });

  const effectiveRoundNumber = selectedRoundNumber ?? latestRound?.number ?? null;
  const selectedRound = rounds.find((round) => round.number === effectiveRoundNumber);
  const isLatestRound = effectiveRoundNumber !== null && effectiveRoundNumber === latestRound?.number;

  const previousRecommendedRounds = useRef<number | null>(null);
  const recommendedRounds = reportQuery.data?.recommended_rounds ?? null;
  const [roundTargetChangedFrom, setRoundTargetChangedFrom] = useState<number | null>(null);

  useEffect(() => {
    // reportQuery.data being undefined means "haven't fetched yet" — distinct from
    // recommended_rounds legitimately being 0, which must not be treated as "no data".
    if (reportQuery.data === undefined) return;
    const next = reportQuery.data.recommended_rounds;
    const previous = previousRecommendedRounds.current;
    setRoundTargetChangedFrom(previous !== null && previous !== next ? previous : null);
    previousRecommendedRounds.current = next;
  }, [reportQuery.data?.recommended_rounds]);

  return (
    <div>
      <p className="mb-2">
        <Link to="/" className="text-sm text-blue-600 underline">
          Back to Events
        </Link>
      </p>
      <h2 className="mb-4 text-lg font-semibold">Pairings</h2>
      <ErrorBanner
        error={
          roundsQuery.error ?? entriesQuery.error ?? reportQuery.error ?? reportMutation.error ?? generateMutation.error
        }
      />

      {(roundsQuery.isLoading || entriesQuery.isLoading) && <p>Loading…</p>}

      {reportQuery.data && (
        <p className="mb-2 text-sm text-gray-600">
          Recommended rounds: {reportQuery.data.recommended_rounds} (active entries:{" "}
          {reportQuery.data.active_entry_count})
        </p>
      )}
      {roundTargetChangedFrom !== null && (
        <p className="mb-2 text-sm text-amber-600">
          Round target changed from {roundTargetChangedFrom} to {recommendedRounds}
        </p>
      )}

      {isOrganizer && (
        <button
          onClick={() => generateMutation.mutate()}
          disabled={generateMutation.isPending || roundsQuery.isFetching || latestRoundHasUnreportedMatch}
          title={
            latestRoundHasUnreportedMatch
              ? "All matches in the current round must be reported first"
              : undefined
          }
          className="mb-4 rounded bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Generate Next Round
        </button>
      )}

      {rounds.length === 0 && roundsQuery.isSuccess && <p>No rounds generated yet.</p>}

      {rounds.length > 0 && (
        <div className="mb-4 flex gap-2">
          {rounds.map((round) => (
            <button
              key={round.number}
              onClick={() => setSelectedRoundNumber(round.number)}
              aria-current={round.number === effectiveRoundNumber}
              className={
                round.number === effectiveRoundNumber
                  ? "rounded border border-blue-600 bg-blue-600 px-2 py-1 text-sm text-white"
                  : "rounded border border-gray-300 px-2 py-1 text-sm"
              }
            >
              Round {round.number}
            </button>
          ))}
        </div>
      )}

      {selectedRound && (
        <>
          <h3 className="mb-2 font-semibold">Round {selectedRound.number}</h3>
          <ul className="divide-y divide-gray-200">
            {selectedRound.matches.map((match) => (
              <li key={match.id} className="py-2">
                {match.entry2_id === null ? (
                  <span>{displayNameFor(entriesQuery.data, match.entry1_id)} — (bye)</span>
                ) : match.result !== "unreported" ? (
                  <span>
                    Table {match.table_number}: {displayNameFor(entriesQuery.data, match.entry1_id)} vs{" "}
                    {displayNameFor(entriesQuery.data, match.entry2_id)} —{" "}
                    {resultLabelFor(match, entriesQuery.data)}
                  </span>
                ) : (
                  <span>
                    Table {match.table_number}: {displayNameFor(entriesQuery.data, match.entry1_id)} vs{" "}
                    {displayNameFor(entriesQuery.data, match.entry2_id)}
                    {canReport && isLatestRound && (
                      <span className="ml-2 inline-flex gap-2">
                        <button
                          disabled={reportMutation.isPending}
                          onClick={() => reportMutation.mutate({ matchId: match.id, result: "entry1_win" })}
                        >
                          {displayNameFor(entriesQuery.data, match.entry1_id)} wins
                        </button>
                        <button
                          disabled={reportMutation.isPending}
                          onClick={() => reportMutation.mutate({ matchId: match.id, result: "tie" })}
                        >
                          Tie
                        </button>
                        <button
                          disabled={reportMutation.isPending}
                          onClick={() => reportMutation.mutate({ matchId: match.id, result: "entry2_win" })}
                        >
                          {displayNameFor(entriesQuery.data, match.entry2_id)} wins
                        </button>
                      </span>
                    )}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
