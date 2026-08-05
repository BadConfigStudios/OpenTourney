import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router";
import { getEvent } from "../api/events";
import { createPod, listPodsForEvent, type PodRead } from "../api/pods";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";
import { EntryRoster } from "./EntryRoster";

export function EventDetail() {
  const { eventId } = useParams<{ eventId: string }>();
  if (!eventId) throw new Error("EventDetail rendered without an eventId route param");

  const { apiFetch, currentPersona } = useAuth();
  const queryClient = useQueryClient();
  const isOrganizer = currentPersona.role === "organizer";

  const eventQuery = useQuery({ queryKey: ["events", eventId], queryFn: () => getEvent(apiFetch, eventId) });
  const podsQuery = useQuery({
    queryKey: ["pods", eventId],
    queryFn: () => listPodsForEvent(apiFetch, eventId),
  });

  const createPodMutation = useMutation({
    mutationFn: () => createPod(apiFetch, eventId),
    onSuccess: (newPod) => {
      queryClient.setQueryData<PodRead[]>(["pods", eventId], (old) => [...(old ?? []), newPod]);
    },
  });

  const pod = podsQuery.data?.[0];

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">Event {eventQuery.data ? eventQuery.data.date : "…"}</h2>
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

      {pod && <EntryRoster podId={pod.id} />}
    </div>
  );
}
