import { apiRequest, jsonInit, type ApiFetch } from "./request";

export interface PodRead {
  id: string;
  event_id: string;
  format_slug: string;
  game_slug: string;
  completed_at: string | null;
}

export function listPodsForEvent(apiFetch: ApiFetch, eventId: string): Promise<PodRead[]> {
  return apiRequest(apiFetch, `/pods?event_id=${eventId}`);
}

export function getPod(apiFetch: ApiFetch, podId: string): Promise<PodRead> {
  return apiRequest(apiFetch, `/pods/${podId}`);
}

export function createPod(apiFetch: ApiFetch, eventId: string, gameSlug: string): Promise<PodRead> {
  return apiRequest(
    apiFetch,
    "/pods",
    jsonInit("POST", { event_id: eventId, format_slug: "swiss", game_slug: gameSlug }),
  );
}

export function completePod(apiFetch: ApiFetch, podId: string): Promise<PodRead> {
  return apiRequest(apiFetch, `/pods/${podId}/complete`, { method: "POST" });
}
