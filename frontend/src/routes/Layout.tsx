import { Link, Outlet } from "react-router";
import { useAuth } from "../auth/AuthContext";

export function Layout() {
  const { currentUser } = useAuth();

  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
        <div className="flex items-center gap-4">
          <h1 className="font-semibold">OpenTourney</h1>
          {currentUser.role === "organizer" && (
            <Link to="/organizations" className="text-sm text-blue-600 underline">
              Organizations
            </Link>
          )}
        </div>
      </header>
      <main className="p-4">
        <Outlet />
      </main>
    </div>
  );
}
