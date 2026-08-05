import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { createEvent } from "../api/events";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

export function NewEvent() {
  const { apiFetch, currentPersona } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [date, setDate] = useState("");

  const mutation = useMutation({
    mutationFn: () => createEvent(apiFetch, date),
    onSuccess: (event) => {
      queryClient.invalidateQueries({ queryKey: ["events"] });
      navigate(`/events/${event.id}`);
    },
  });

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
      <ErrorBanner error={mutation.error} />
      <label className="block text-sm">
        Date
        <input
          type="date"
          required
          value={date}
          onChange={(event) => setDate(event.target.value)}
          className="mt-1 block rounded border border-gray-300 px-2 py-1"
        />
      </label>
      <button
        type="submit"
        disabled={mutation.isPending}
        className="mt-4 rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
      >
        Create Event
      </button>
    </form>
  );
}
