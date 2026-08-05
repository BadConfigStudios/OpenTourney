import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { listEntries, type EntryRead } from "../api/entries";
import { fetchRounds } from "../api/rounds";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

function displayNameFor(entries: EntryRead[] | undefined, entryId: string): string {
  const entry = entries?.find((candidate) => candidate.id === entryId);
  return entry?.metadata.display_name ?? entryId;
}

export function Pairings() {
  const { podId } = useParams<{ podId: string }>();
  if (!podId) throw new Error("Pairings rendered without a podId route param");

  const { apiFetch } = useAuth();

  const roundsQuery = useQuery({
    queryKey: ["rounds", podId],
    queryFn: () => fetchRounds(apiFetch, podId),
  });
  const entriesQuery = useQuery({
    queryKey: ["entries", podId],
    queryFn: () => listEntries(apiFetch, podId),
  });

  const rounds = roundsQuery.data ?? [];
  const latestRound = rounds[rounds.length - 1];

  const [selectedRoundNumber, setSelectedRoundNumber] = useState<number | null>(null);
  const effectiveRoundNumber = selectedRoundNumber ?? latestRound?.number ?? null;
  const selectedRound = rounds.find((round) => round.number === effectiveRoundNumber);

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">Pairings</h2>
      <ErrorBanner error={roundsQuery.error ?? entriesQuery.error} />

      {rounds.length === 0 && !roundsQuery.isLoading && <p>No rounds generated yet.</p>}

      {rounds.length > 0 && (
        <div className="mb-4 flex gap-2">
          {rounds.map((round) => (
            <button
              key={round.number}
              onClick={() => setSelectedRoundNumber(round.number)}
              className="rounded border border-gray-300 px-2 py-1 text-sm"
            >
              Round {round.number}
            </button>
          ))}
        </div>
      )}

      {selectedRound && (
        <ul className="divide-y divide-gray-200">
          {selectedRound.matches.map((match) => (
            <li key={match.id} className="py-2">
              {match.entry2_id === null ? (
                <span>{displayNameFor(entriesQuery.data, match.entry1_id)} — (bye)</span>
              ) : (
                <span>
                  Table {match.table_number}: {displayNameFor(entriesQuery.data, match.entry1_id)} vs{" "}
                  {displayNameFor(entriesQuery.data, match.entry2_id)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
