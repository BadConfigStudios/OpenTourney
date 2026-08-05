import { Outlet } from "react-router";
import { PersonaSwitcher } from "../auth/PersonaSwitcher";

export function Layout() {
  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
        <h1 className="font-semibold">OpenTourney</h1>
        <PersonaSwitcher />
      </header>
      <main className="p-4">
        <Outlet />
      </main>
    </div>
  );
}
