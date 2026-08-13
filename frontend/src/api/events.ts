import { apiRequest, jsonInit, type ApiFetch } from "./request";

export interface EventRead {
  id: string;
  date: string;
  name: string;
  description: string | null;
  organization_id: string;
}

export function listEvents(apiFetch: ApiFetch): Promise<EventRead[]> {
  return apiRequest(apiFetch, "/events");
}

export function getEvent(apiFetch: ApiFetch, eventId: string): Promise<EventRead> {
  return apiRequest(apiFetch, `/events/${eventId}`);
}

export function createEvent(
  apiFetch: ApiFetch,
  date: string,
  name: string,
  organizationId: string,
  description?: string,
): Promise<EventRead> {
  return apiRequest(
    apiFetch,
    "/events",
    jsonInit("POST", { date, name, description, organization_id: organizationId }),
  );
}
