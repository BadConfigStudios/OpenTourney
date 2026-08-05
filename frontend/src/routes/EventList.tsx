import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { listEvents } from "../api/events";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

export function EventList() {
  const { apiFetch, currentPersona } = useAuth();
  const {
    data: events,
    error,
    isLoading,
  } = useQuery({ queryKey: ["events"], queryFn: () => listEvents(apiFetch) });

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Events</h2>
        {currentPersona.role === "organizer" && (
          <Link to="/events/new" className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white">
            New Event
          </Link>
        )}
      </div>
      <ErrorBanner error={error} />
      {isLoading && <p>Loading…</p>}
      {events && events.length === 0 && <p>No events yet.</p>}
      {events && events.length > 0 && (
        <ul className="divide-y divide-gray-200">
          {events.map((event) => (
            <li key={event.id} className="py-2">
              <Link to={`/events/${event.id}`} className="text-blue-700 hover:underline">
                {event.date}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
