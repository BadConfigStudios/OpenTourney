import { useQuery } from "@tanstack/react-query";
import { Link, Navigate } from "react-router";
import { listOrganizations } from "../api/organizations";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

export function Organizations() {
  const { apiFetch } = useAuth();
  const organizationsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: () => listOrganizations(apiFetch),
  });

  const organizations = organizationsQuery.data ?? [];

  if (organizationsQuery.isSuccess && organizations.length === 1) {
    return <Navigate to={`/organizations/${organizations[0].id}`} replace />;
  }

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">Organizations</h2>
      <ErrorBanner error={organizationsQuery.error} />

      {organizationsQuery.isSuccess && organizations.length === 0 && (
        <p className="text-sm text-gray-600">You don't belong to any organizations yet.</p>
      )}

      {organizations.length > 1 && (
        <ul>
          {organizations.map((org) => (
            <li key={org.id} className="mb-1">
              <Link to={`/organizations/${org.id}`} className="text-blue-600 underline">
                {org.name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
