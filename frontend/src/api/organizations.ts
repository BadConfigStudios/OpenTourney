import { apiRequest, jsonInit, type ApiFetch } from "./request";

export interface OrganizationRead {
  id: string;
  name: string;
}

export type OrgRoleName = "owner" | "organizer" | "scorekeeper" | "judge";

export interface OrganizationDetailRead extends OrganizationRead {
  viewer_role: OrgRoleName;
}

export interface OrganizationMemberRead {
  id: string;
  organization_id: string;
  player_uuid: string;
  source_system: string;
  role: OrgRoleName;
}

export function listOrganizations(apiFetch: ApiFetch): Promise<OrganizationRead[]> {
  return apiRequest(apiFetch, "/organizations");
}

export function createOrganization(apiFetch: ApiFetch, name: string): Promise<OrganizationRead> {
  return apiRequest(apiFetch, "/organizations", jsonInit("POST", { name }));
}

export function getOrganization(apiFetch: ApiFetch, organizationId: string): Promise<OrganizationDetailRead> {
  return apiRequest(apiFetch, `/organizations/${organizationId}`);
}

export function updateOrganization(
  apiFetch: ApiFetch,
  organizationId: string,
  name: string,
): Promise<OrganizationRead> {
  return apiRequest(apiFetch, `/organizations/${organizationId}`, jsonInit("PATCH", { name }));
}

export function listOrganizationMembers(
  apiFetch: ApiFetch,
  organizationId: string,
): Promise<OrganizationMemberRead[]> {
  return apiRequest(apiFetch, `/organizations/${organizationId}/members`);
}

export function addOrganizationMember(
  apiFetch: ApiFetch,
  organizationId: string,
  playerUuid: string,
  sourceSystem: string,
  role: OrgRoleName,
): Promise<OrganizationMemberRead> {
  return apiRequest(
    apiFetch,
    `/organizations/${organizationId}/members`,
    jsonInit("POST", { player_uuid: playerUuid, source_system: sourceSystem, role }),
  );
}

export function updateOrganizationMember(
  apiFetch: ApiFetch,
  organizationId: string,
  memberId: string,
  role: OrgRoleName,
): Promise<OrganizationMemberRead> {
  return apiRequest(
    apiFetch,
    `/organizations/${organizationId}/members/${memberId}`,
    jsonInit("PATCH", { role }),
  );
}

export function removeOrganizationMember(
  apiFetch: ApiFetch,
  organizationId: string,
  memberId: string,
): Promise<void> {
  return apiRequest(apiFetch, `/organizations/${organizationId}/members/${memberId}`, { method: "DELETE" });
}
