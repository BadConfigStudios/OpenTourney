import { apiRequest, jsonInit, type ApiFetch } from "./request";

export interface EventRead {
  id: string;
  date: string;
}

export function listEvents(apiFetch: ApiFetch): Promise<EventRead[]> {
  return apiRequest(apiFetch, "/events");
}

export function getEvent(apiFetch: ApiFetch, eventId: string): Promise<EventRead> {
  return apiRequest(apiFetch, `/events/${eventId}`);
}

export function createEvent(apiFetch: ApiFetch, date: string): Promise<EventRead> {
  return apiRequest(apiFetch, "/events", jsonInit("POST", { date }));
}
