import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { getEvent } from "../api/events";
import { createPod, listPodsForEvent } from "../api/pods";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";
import { EntryRoster } from "./EntryRoster";

export function EventDetail() {
  const { eventId } = useParams<{ eventId: string }>();
  if (!eventId) throw new Error("EventDetail rendered without an eventId route param");

  const { apiFetch, currentUser } = useAuth();
  const queryClient = useQueryClient();
  const isOrganizer = currentUser.role === "organizer";

  const eventQuery = useQuery({ queryKey: ["events", eventId], queryFn: () => getEvent(apiFetch, eventId) });
  const podsQuery = useQuery({
    queryKey: ["pods", eventId],
    queryFn: () => listPodsForEvent(apiFetch, eventId),
  });

  const createPodMutation = useMutation({
    mutationFn: () => createPod(apiFetch, eventId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pods", eventId] }),
  });

  const pod = podsQuery.data?.[0];

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">
        {eventQuery.data ? eventQuery.data.name : "…"}
      </h2>
      {eventQuery.data && <p className="mb-4 text-sm text-gray-600">{eventQuery.data.date}</p>}
      <ErrorBanner error={eventQuery.error ?? podsQuery.error ?? createPodMutation.error} />

      {podsQuery.data && !pod && (
        <div className="mb-6">
          <p className="mb-2 text-sm text-gray-600">This event has no pod yet.</p>
          {isOrganizer && (
            <button
              onClick={() => createPodMutation.mutate()}
              disabled={createPodMutation.isPending}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
            >
              Create Pod
            </button>
          )}
        </div>
      )}

      {pod && (
        <>
          <p className="mb-4">
            <Link to={`/pods/${pod.id}/pairings`} className="text-blue-600 underline">
              View Pairings
            </Link>
            {" · "}
            <Link to={`/pods/${pod.id}/report`} className="text-blue-600 underline">
              View Report
            </Link>
          </p>
          <EntryRoster podId={pod.id} podCompletedAt={pod.completed_at} />
        </>
      )}
    </div>
  );
}
