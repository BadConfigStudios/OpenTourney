import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import type { User } from "oidc-client-ts";
import { AuthProvider, type MinimalUserManager } from "../auth/AuthContext";
import { ConfigProvider } from "../config/ConfigProvider";
import type { PersonaRole } from "../config/types";

function NavigatedTo() {
  const location = useLocation();
  return <div data-testid="navigated-to">{location.pathname}</div>;
}

function fakeUser(role: PersonaRole): User {
  return { access_token: "test-access-token", expired: false, profile: { roles: [role] } } as unknown as User;
}

function fakeUserManager(role: PersonaRole | null): MinimalUserManager {
  const user = role ? fakeUser(role) : null;
  return {
    getUser: () => Promise.resolve(user),
    signinRedirect: () => Promise.resolve(),
    signinRedirectCallback: () => Promise.resolve(user ?? fakeUser("organizer")),
    removeUser: () => Promise.resolve(),
  };
}

export function renderWithProviders(
  element: ReactElement,
  options: {
    path?: string;
    routePath?: string;
    // undefined = authenticated as "organizer" (the old default persona);
    // an explicit PersonaRole = authenticated as that role; null = unauthenticated.
    role?: PersonaRole | null;
    // Escape hatch for tests that need custom async behavior (e.g. a rejecting
    // signinRedirectCallback) beyond what the role-based fake above supports.
    userManagerOverride?: MinimalUserManager;
    queryClient?: QueryClient;
  } = {},
) {
  const role = options.role === undefined ? "organizer" : options.role;

  const queryClient =
    options.queryClient ??
    new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

  const path = options.path ?? "/";
  const routePath = options.routePath ?? path;

  // createMemoryRouter never touches window.location, but AuthContext's
  // /callback bypass (needed so Callback can mount and call completeSignIn
  // while unauthenticated) reads window.location.pathname directly, matching
  // how the real app's createBrowserRouter keeps it in sync. Push the routed
  // path onto real history so that check sees the path a test asked for;
  // src/test/setup.ts resets it to "/" after each test.
  window.history.pushState({}, "", path);

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
        <AuthProvider userManagerOverride={options.userManagerOverride ?? fakeUserManager(role)}>
          <RouterProvider router={router} />
        </AuthProvider>
      </ConfigProvider>
    </QueryClientProvider>,
  );
}
