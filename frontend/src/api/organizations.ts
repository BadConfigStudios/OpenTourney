import { apiRequest, jsonInit, type ApiFetch } from "./request";

export interface OrganizationRead {
  id: string;
  name: string;
}

export function listOrganizations(apiFetch: ApiFetch): Promise<OrganizationRead[]> {
  return apiRequest(apiFetch, "/organizations");
}

export function createOrganization(apiFetch: ApiFetch, name: string): Promise<OrganizationRead> {
  return apiRequest(apiFetch, "/organizations", jsonInit("POST", { name }));
}
