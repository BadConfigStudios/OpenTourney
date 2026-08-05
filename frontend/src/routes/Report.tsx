import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { displayNameFor, listEntries } from "../api/entries";
import { completePod } from "../api/pods";
import { fetchPodReport } from "../api/report";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

export function Report() {
  const { podId } = useParams<{ podId: string }>();
  if (!podId) throw new Error("Report rendered without a podId route param");

  const { apiFetch, currentPersona } = useAuth();
  const queryClient = useQueryClient();
  const isOrganizer = currentPersona.role === "organizer";

  const reportQuery = useQuery({
    queryKey: ["report", podId],
    queryFn: () => fetchPodReport(apiFetch, podId),
  });
  const entriesQuery = useQuery({
    queryKey: ["entries", podId],
    queryFn: () => listEntries(apiFetch, podId),
  });

  const completeMutation = useMutation({
    mutationFn: () => completePod(apiFetch, podId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["report", podId] });
      queryClient.invalidateQueries({ queryKey: ["rounds", podId] });
    },
  });

  const report = reportQuery.data;

  return (
    <div>
      <p className="mb-2">
        <Link to={`/pods/${podId}/pairings`} className="text-sm text-blue-600 underline">
          Back to Pairings
        </Link>
      </p>
      <h2 className="mb-4 text-lg font-semibold">Report</h2>
      <ErrorBanner error={reportQuery.error ?? entriesQuery.error ?? completeMutation.error} />

      {(reportQuery.isLoading || entriesQuery.isLoading) && <p>Loading…</p>}

      {report && (
        <>
          {report.is_partial && (
            <p className="mb-2 rounded border border-yellow-300 bg-yellow-50 px-3 py-2 text-sm text-yellow-800">
              Latest round not fully reported — standings reflect completed rounds only.
            </p>
          )}
          {!report.is_complete && (
            <p className="mb-4 rounded border border-yellow-300 bg-yellow-50 px-3 py-2 text-sm text-yellow-800">
              Pod not yet completed — this is a live view, not final results.
            </p>
          )}

          {isOrganizer && (
            <button
              onClick={() => completeMutation.mutate()}
              disabled={completeMutation.isPending || report.is_partial || report.is_complete}
              title={
                report.is_complete
                  ? "Pod is already complete"
                  : report.is_partial
                    ? "The latest round must be fully reported before completing the pod"
                    : undefined
              }
              className="mb-4 rounded bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              Complete Pod
            </button>
          )}

          {report.standings.length === 0 ? (
            <p>No standings yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left">
                  <th className="py-1 pr-4">Rank</th>
                  <th className="py-1 pr-4">Entry</th>
                  <th className="py-1">Points</th>
                </tr>
              </thead>
              <tbody>
                {report.standings.map((row) => (
                  <tr key={row.entry_id} className="border-b border-gray-100">
                    <td className="py-1 pr-4">{row.rank}</td>
                    <td className="py-1 pr-4">{displayNameFor(entriesQuery.data, row.entry_id)}</td>
                    <td className="py-1">{row.points}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
