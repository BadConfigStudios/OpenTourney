import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { createEvent } from "../api/events";
import { createOrganization, listOrganizations } from "../api/organizations";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

export function NewEvent() {
  const { apiFetch, currentPersona } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [date, setDate] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [newOrgName, setNewOrgName] = useState("");

  const organizationsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: () => listOrganizations(apiFetch),
    enabled: currentPersona.role === "organizer",
  });

  const createOrgMutation = useMutation({
    mutationFn: () => createOrganization(apiFetch, newOrgName),
    onSuccess: (org) => {
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
      setOrganizationId(org.id);
      setNewOrgName("");
    },
  });

  const mutation = useMutation({
    mutationFn: () => createEvent(apiFetch, date, name, organizationId, description || undefined),
    onSuccess: (event) => {
      queryClient.invalidateQueries({ queryKey: ["events"] });
      navigate(`/events/${event.id}`);
    },
  });

  const organizations = organizationsQuery.data ?? [];

  // Pre-select an organization once the caller's list loads, so a caller
  // with a single organization doesn't have to make a redundant choice.
  useEffect(() => {
    if (organizationId === "" && organizationsQuery.data && organizationsQuery.data.length > 0) {
      setOrganizationId(organizationsQuery.data[0].id);
    }
    // Deliberately omitting `organizationId` from deps: the `organizationId === ""` guard
    // means this can only fire once (the first time the list loads), and the empty option
    // in the <select> below is disabled, so it's unreachable via user action anyway.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organizationsQuery.data]);

  if (currentPersona.role !== "organizer") {
    return <Navigate to="/" replace />;
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
    >
      <h2 className="mb-4 text-lg font-semibold">New Event</h2>
      <ErrorBanner error={mutation.error ?? organizationsQuery.error ?? createOrgMutation.error} />

      <label className="block text-sm">
        Event name
        <input
          type="text"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="mt-1 block rounded border border-gray-300 px-2 py-1"
        />
      </label>

      <label className="mt-2 block text-sm">
        Description
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="mt-1 block rounded border border-gray-300 px-2 py-1"
        />
      </label>

      <label className="mt-2 block text-sm">
        Date
        <input
          type="date"
          required
          value={date}
          onChange={(event) => setDate(event.target.value)}
          className="mt-1 block rounded border border-gray-300 px-2 py-1"
        />
      </label>

      {organizations.length > 0 ? (
        <label className="mt-2 block text-sm">
          Organization
          <select
            required
            value={organizationId}
            onChange={(event) => setOrganizationId(event.target.value)}
            className="mt-1 block rounded border border-gray-300 px-2 py-1"
          >
            <option value="" disabled>
              Select an organization
            </option>
            {organizations.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>
        </label>
      ) : (
        organizationsQuery.isSuccess && (
          <div className="mt-2">
            <label className="block text-sm">
              New organization name
              <input
                type="text"
                value={newOrgName}
                onChange={(event) => setNewOrgName(event.target.value)}
                className="mt-1 block rounded border border-gray-300 px-2 py-1"
              />
            </label>
            <button
              type="button"
              disabled={createOrgMutation.isPending || newOrgName.trim() === ""}
              onClick={() => createOrgMutation.mutate()}
              className="mt-2 rounded border border-gray-300 px-3 py-1.5 text-sm"
            >
              Create organization
            </button>
            {/* Needed because in tests the GET /organizations mock is static, so the
                newly-created org never appears in a refetched <select>; in production this
                flashes briefly before the invalidated query refetches and the <select>
                (with the new org selected) replaces this branch. */}
            {createOrgMutation.data && (
              <p className="mt-2 text-sm text-gray-700">{createOrgMutation.data.name}</p>
            )}
          </div>
        )
      )}

      <button
        type="submit"
        disabled={mutation.isPending || organizationId === ""}
        className="mt-4 rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
      >
        Create Event
      </button>
    </form>
  );
}
