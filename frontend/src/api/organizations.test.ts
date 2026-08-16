import { describe, expect, it, vi } from "vitest";
import {
  addOrganizationMember,
  createOrganization,
  getOrganization,
  listOrganizations,
  listOrganizationMembers,
  removeOrganizationMember,
  updateOrganization,
  updateOrganizationMember,
} from "./organizations";

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

  it("getOrganization GETs /organizations/:id", async () => {
    const apiFetch = fetchReturning({ id: "org-1", name: "Dragon's Den", viewer_role: "owner" });

    const org = await getOrganization(apiFetch, "org-1");

    expect(org).toEqual({ id: "org-1", name: "Dragon's Den", viewer_role: "owner" });
    expect(apiFetch).toHaveBeenCalledWith("/organizations/org-1", undefined);
  });

  it("updateOrganization PATCHes the new name", async () => {
    const apiFetch = fetchReturning({ id: "org-1", name: "New Name" });

    await updateOrganization(apiFetch, "org-1", "New Name");

    expect(apiFetch).toHaveBeenCalledWith("/organizations/org-1", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New Name" }),
    });
  });

  it("listOrganizationMembers GETs /organizations/:id/members", async () => {
    const members = [
      { id: "m1", organization_id: "org-1", player_uuid: "p1", source_system: "club-checkin", role: "owner" },
    ];
    const apiFetch = fetchReturning(members);

    const result = await listOrganizationMembers(apiFetch, "org-1");

    expect(result).toEqual(members);
    expect(apiFetch).toHaveBeenCalledWith("/organizations/org-1/members", undefined);
  });

  it("addOrganizationMember POSTs the new member", async () => {
    const member = { id: "m2", organization_id: "org-1", player_uuid: "p2", source_system: "club-checkin", role: "scorekeeper" };
    const apiFetch = fetchReturning(member, 201);

    await addOrganizationMember(apiFetch, "org-1", "p2", "club-checkin", "scorekeeper");

    expect(apiFetch).toHaveBeenCalledWith("/organizations/org-1/members", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_uuid: "p2", source_system: "club-checkin", role: "scorekeeper" }),
    });
  });

  it("updateOrganizationMember PATCHes the member's role", async () => {
    const member = { id: "m2", organization_id: "org-1", player_uuid: "p2", source_system: "club-checkin", role: "organizer" };
    const apiFetch = fetchReturning(member);

    await updateOrganizationMember(apiFetch, "org-1", "m2", "organizer");

    expect(apiFetch).toHaveBeenCalledWith("/organizations/org-1/members/m2", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "organizer" }),
    });
  });

  it("removeOrganizationMember DELETEs the member", async () => {
    const apiFetch = fetchReturning(undefined, 204);

    await removeOrganizationMember(apiFetch, "org-1", "m2");

    expect(apiFetch).toHaveBeenCalledWith("/organizations/org-1/members/m2", { method: "DELETE" });
  });
});
