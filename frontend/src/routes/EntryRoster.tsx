import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createEntry, deleteEntry, listEntries, updateEntryDisplayName, type EntryRead } from "../api/entries";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

export function EntryRoster({ podId }: { podId: string }) {
  const { apiFetch, currentPersona } = useAuth();
  const queryClient = useQueryClient();
  const isOrganizer = currentPersona.role === "organizer";

  const {
    data: entries,
    error,
    isLoading,
  } = useQuery({ queryKey: ["entries", podId], queryFn: () => listEntries(apiFetch, podId) });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["entries", podId] });

  const createMutation = useMutation({
    mutationFn: (displayName: string) => createEntry(apiFetch, podId, displayName),
    onSuccess: invalidate,
  });
  const updateMutation = useMutation({
    mutationFn: (args: { entryId: string; displayName: string }) =>
      updateEntryDisplayName(apiFetch, args.entryId, args.displayName),
    onSuccess: invalidate,
  });
  const deleteMutation = useMutation({
    mutationFn: (entryId: string) => deleteEntry(apiFetch, entryId),
    onSuccess: invalidate,
  });

  const [newName, setNewName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");

  return (
    <div>
      <h3 className="mb-2 font-semibold">Entries</h3>
      <ErrorBanner error={createMutation.error ?? updateMutation.error ?? deleteMutation.error ?? error} />
      {isLoading && <p>Loading…</p>}
      {entries && entries.length === 0 && <p>No entries yet.</p>}
      {entries && entries.length > 0 && (
        <ul className="mb-4 divide-y divide-gray-200">
          {entries.map((entry: EntryRead) =>
            editingId === entry.id && isOrganizer ? (
              <li key={entry.id} className="flex items-center gap-2 py-2">
                <input
                  aria-label={`Edit name for ${entry.metadata.display_name ?? entry.id}`}
                  value={editingName}
                  onChange={(event) => setEditingName(event.target.value)}
                  className="rounded border border-gray-300 px-2 py-1"
                />
                <button
                  onClick={() => {
                    createMutation.reset();
                    deleteMutation.reset();
                    updateMutation.mutate({ entryId: entry.id, displayName: editingName });
                    setEditingId(null);
                  }}
                >
                  Save
                </button>
                <button onClick={() => setEditingId(null)}>Cancel</button>
              </li>
            ) : (
              <li key={entry.id} className="flex items-center justify-between py-2">
                <span>{entry.metadata.display_name ?? "(unnamed)"}</span>
                {isOrganizer && (
                  <span className="flex gap-2">
                    <button
                      aria-label={`Edit ${entry.metadata.display_name ?? entry.id}`}
                      onClick={() => {
                        setEditingId(entry.id);
                        setEditingName(entry.metadata.display_name ?? "");
                      }}
                    >
                      Edit
                    </button>
                    <button
                      aria-label={`Delete ${entry.metadata.display_name ?? entry.id}`}
                      onClick={() => {
                        createMutation.reset();
                        updateMutation.reset();
                        deleteMutation.mutate(entry.id);
                      }}
                    >
                      Delete
                    </button>
                  </span>
                )}
              </li>
            ),
          )}
        </ul>
      )}
      {isOrganizer && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            updateMutation.reset();
            deleteMutation.reset();
            createMutation.mutate(newName);
            setNewName("");
          }}
          className="flex gap-2"
        >
          <label className="flex items-center gap-2 text-sm">
            Display name
            <input
              required
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              className="rounded border border-gray-300 px-2 py-1"
            />
          </label>
          <button type="submit" className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white">
            Add Entry
          </button>
        </form>
      )}
    </div>
  );
}
