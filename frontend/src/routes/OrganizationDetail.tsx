import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import {
  addOrganizationMember,
  getOrganization,
  listOrganizationMembers,
  removeOrganizationMember,
  updateOrganization,
  updateOrganizationMember,
  type OrganizationDetailRead,
  type OrganizationMemberRead,
  type OrgRoleName,
} from "../api/organizations";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

const ROLE_OPTIONS: OrgRoleName[] = ["owner", "organizer", "scorekeeper", "judge"];

export function OrganizationDetail() {
  const { organizationId } = useParams<{ organizationId: string }>();
  if (!organizationId) throw new Error("OrganizationDetail rendered without an organizationId route param");

  const { apiFetch } = useAuth();
  const queryClient = useQueryClient();
  const [nameDraft, setNameDraft] = useState("");
  const [newPlayerUuid, setNewPlayerUuid] = useState("");
  const [newSourceSystem, setNewSourceSystem] = useState("");
  const [newRole, setNewRole] = useState<OrgRoleName>("scorekeeper");

  const orgQuery = useQuery({
    queryKey: ["organizations", organizationId],
    queryFn: () => getOrganization(apiFetch, organizationId),
  });
  const membersQuery = useQuery({
    queryKey: ["organizations", organizationId, "members"],
    queryFn: () => listOrganizationMembers(apiFetch, organizationId),
  });

  const renameMutation = useMutation({
    mutationFn: () => updateOrganization(apiFetch, organizationId, nameDraft),
    onSuccess: (data) =>
      queryClient.setQueryData(
        ["organizations", organizationId],
        (old: OrganizationDetailRead | undefined) => (old ? { ...old, name: data.name } : old),
      ),
  });

  const addMemberMutation = useMutation({
    mutationFn: () => addOrganizationMember(apiFetch, organizationId, newPlayerUuid, newSourceSystem, newRole),
    onSuccess: (data) => {
      queryClient.setQueryData(
        ["organizations", organizationId, "members"],
        (old: OrganizationMemberRead[] | undefined) => (old ? [...old, data] : [data]),
      );
      setNewPlayerUuid("");
      setNewSourceSystem("");
      setNewRole("scorekeeper");
    },
  });

  const updateRoleMutation = useMutation({
    mutationFn: ({ memberId, role }: { memberId: string; role: OrgRoleName }) =>
      updateOrganizationMember(apiFetch, organizationId, memberId, role),
    onSuccess: (data) =>
      queryClient.setQueryData(
        ["organizations", organizationId, "members"],
        (old: OrganizationMemberRead[] | undefined) =>
          old?.map((member) => (member.id === data.id ? data : member)),
      ),
  });

  const removeMemberMutation = useMutation({
    mutationFn: (memberId: string) => removeOrganizationMember(apiFetch, organizationId, memberId),
    onSuccess: (_data, memberId) =>
      queryClient.setQueryData(
        ["organizations", organizationId, "members"],
        (old: OrganizationMemberRead[] | undefined) => old?.filter((member) => member.id !== memberId),
      ),
  });

  const org = orgQuery.data;
  const members = membersQuery.data ?? [];
  const isOwner = org?.viewer_role === "owner";

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">{org ? org.name : "…"}</h2>
      <ErrorBanner
        error={
          orgQuery.error ??
          membersQuery.error ??
          renameMutation.error ??
          addMemberMutation.error ??
          updateRoleMutation.error ??
          removeMemberMutation.error
        }
      />

      {isOwner && (
        <div className="mb-6">
          <label className="block text-sm">
            Organization name
            <input
              type="text"
              value={nameDraft || org.name}
              onChange={(event) => setNameDraft(event.target.value)}
              className="mt-1 block rounded border border-gray-300 px-2 py-1"
            />
          </label>
          <button
            type="button"
            disabled={renameMutation.isPending}
            onClick={() => renameMutation.mutate()}
            className="mt-2 rounded border border-gray-300 px-3 py-1.5 text-sm"
          >
            Save name
          </button>
        </div>
      )}

      <table className="mb-6 w-full text-left text-sm">
        <thead>
          <tr>
            <th className="border-b border-gray-200 pb-1">Identity</th>
            <th className="border-b border-gray-200 pb-1">Role</th>
            {isOwner && <th className="border-b border-gray-200 pb-1" />}
          </tr>
        </thead>
        <tbody>
          {members.map((member) => (
            <tr key={member.id}>
              <td className="py-1">{member.player_uuid}</td>
              <td className="py-1">
                {isOwner ? (
                  <select
                    value={member.role}
                    onChange={(event) =>
                      updateRoleMutation.mutate({ memberId: member.id, role: event.target.value as OrgRoleName })
                    }
                    className="rounded border border-gray-300 px-2 py-1"
                  >
                    {ROLE_OPTIONS.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </select>
                ) : (
                  member.role
                )}
              </td>
              {isOwner && (
                <td className="py-1">
                  <button
                    type="button"
                    onClick={() => removeMemberMutation.mutate(member.id)}
                    disabled={removeMemberMutation.isPending}
                    className="rounded border border-gray-300 px-2 py-1 text-xs"
                  >
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {isOwner && (
        <div>
          <h3 className="mb-2 text-sm font-semibold">Add member</h3>
          <label className="block text-sm">
            New member player UUID
            <input
              type="text"
              value={newPlayerUuid}
              onChange={(event) => setNewPlayerUuid(event.target.value)}
              className="mt-1 block rounded border border-gray-300 px-2 py-1"
            />
          </label>
          <label className="mt-2 block text-sm">
            New member source system
            <input
              type="text"
              value={newSourceSystem}
              onChange={(event) => setNewSourceSystem(event.target.value)}
              className="mt-1 block rounded border border-gray-300 px-2 py-1"
            />
          </label>
          <label className="mt-2 block text-sm">
            New member role
            <select
              value={newRole}
              onChange={(event) => setNewRole(event.target.value as OrgRoleName)}
              className="mt-1 block rounded border border-gray-300 px-2 py-1"
            >
              {ROLE_OPTIONS.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={addMemberMutation.isPending || newPlayerUuid.trim() === "" || newSourceSystem.trim() === ""}
            onClick={() => addMemberMutation.mutate()}
            className="mt-2 rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
          >
            Add member
          </button>
        </div>
      )}
    </div>
  );
}
