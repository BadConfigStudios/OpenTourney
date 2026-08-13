import { describe, expect, it, vi } from "vitest";
import { createOrganization, listOrganizations } from "./organizations";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("organizations api", () => {
  it("listOrganizations GETs /organizations", async () => {
    const apiFetch = fetchReturning([{ id: "org-1", name: "Dragon's Den" }]);

    const orgs = await listOrganizations(apiFetch);

    expect(orgs).toEqual([{ id: "org-1", name: "Dragon's Den" }]);
    expect(apiFetch).toHaveBeenCalledWith("/organizations", undefined);
  });

  it("createOrganization POSTs the name", async () => {
    const apiFetch = fetchReturning({ id: "org-2", name: "New Org" }, 201);

    await createOrganization(apiFetch, "New Org");

    expect(apiFetch).toHaveBeenCalledWith("/organizations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New Org" }),
    });
  });
});
