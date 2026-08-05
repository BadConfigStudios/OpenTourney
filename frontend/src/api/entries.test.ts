import { describe, expect, it, vi } from "vitest";
import { createEntry, deleteEntry, listEntries, updateEntryDisplayName } from "./entries";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("entries api", () => {
  it("listEntries GETs /entries?pod_id=", async () => {
    const apiFetch = fetchReturning([]);

    await listEntries(apiFetch, "pod-1");

    expect(apiFetch).toHaveBeenCalledWith("/entries?pod_id=pod-1", undefined);
  });

  it("createEntry generates a UUID and a fixed walk-in source_system", async () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue("11111111-1111-4111-8111-111111111111");
    const apiFetch = fetchReturning({ id: "e1" }, 201);

    await createEntry(apiFetch, "pod-1", "Ash");

    expect(apiFetch).toHaveBeenCalledWith("/entries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pod_id: "pod-1",
        player_uuid: "11111111-1111-4111-8111-111111111111",
        source_system: "opentourney-ui",
        metadata: { display_name: "Ash" },
      }),
    });
  });

  it("updateEntryDisplayName PATCHes only metadata.display_name", async () => {
    const apiFetch = fetchReturning({ id: "e1" });

    await updateEntryDisplayName(apiFetch, "e1", "Misty");

    expect(apiFetch).toHaveBeenCalledWith("/entries/e1", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metadata: { display_name: "Misty" } }),
    });
  });

  it("deleteEntry DELETEs /entries/:id", async () => {
    const apiFetch = vi.fn().mockResolvedValue({ ok: true, status: 204 });

    await deleteEntry(apiFetch, "e1");

    expect(apiFetch).toHaveBeenCalledWith("/entries/e1", { method: "DELETE" });
  });
});
