import { apiRequest, jsonInit, type ApiFetch } from "./request";

export interface EntryRead {
  id: string;
  pod_id: string;
  player_uuid: string;
  source_system: string;
  metadata: { display_name?: string; [key: string]: unknown };
  dropped_at_round: number | null;
}

const WALK_IN_SOURCE_SYSTEM = "opentourney-ui";

export function listEntries(apiFetch: ApiFetch, podId: string): Promise<EntryRead[]> {
  return apiRequest(apiFetch, `/entries?pod_id=${podId}`);
}

export function createEntry(apiFetch: ApiFetch, podId: string, displayName: string): Promise<EntryRead> {
  return apiRequest(
    apiFetch,
    "/entries",
    jsonInit("POST", {
      pod_id: podId,
      player_uuid: crypto.randomUUID(),
      source_system: WALK_IN_SOURCE_SYSTEM,
      metadata: { display_name: displayName },
    }),
  );
}

export function updateEntryDisplayName(
  apiFetch: ApiFetch,
  entryId: string,
  displayName: string,
): Promise<EntryRead> {
  return apiRequest(
    apiFetch,
    `/entries/${entryId}`,
    jsonInit("PATCH", { metadata: { display_name: displayName } }),
  );
}

export function deleteEntry(apiFetch: ApiFetch, entryId: string): Promise<void> {
  return apiRequest(apiFetch, `/entries/${entryId}`, { method: "DELETE" });
}

export function dropEntry(apiFetch: ApiFetch, entryId: string): Promise<EntryRead> {
  return apiRequest(apiFetch, `/entries/${entryId}/drop`, { method: "POST" });
}

export function undropEntry(apiFetch: ApiFetch, entryId: string): Promise<EntryRead> {
  return apiRequest(apiFetch, `/entries/${entryId}/undrop`, { method: "POST" });
}

export function displayNameFor(entries: EntryRead[] | undefined, entryId: string): string {
  const entry = entries?.find((candidate) => candidate.id === entryId);
  return entry?.metadata.display_name ?? entryId;
}
