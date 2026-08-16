import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { AuthProvider } from "../auth/AuthContext";
import { ConfigProvider } from "../config/ConfigProvider";

function NavigatedTo() {
  const location = useLocation();
  return <div data-testid="navigated-to">{location.pathname}</div>;
}

export function renderWithProviders(
  element: ReactElement,
  options: { path?: string; routePath?: string; personaLabel?: string; queryClient?: QueryClient } = {},
) {
  if (options.personaLabel) {
    localStorage.setItem("opentourney.persona", options.personaLabel);
  }

  const queryClient =
    options.queryClient ??
    new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

  const path = options.path ?? "/";
  const routePath = options.routePath ?? path;
  const router = createMemoryRouter(
    [
      { path: routePath, element },
      { path: "*", element: <NavigatedTo /> },
    ],
    { initialEntries: [path] },
  );

  return render(
    <QueryClientProvider client={queryClient}>
      <ConfigProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </ConfigProvider>
    </QueryClientProvider>,
  );
}
