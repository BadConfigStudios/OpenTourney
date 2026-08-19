import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../test/renderWithProviders";
import type { MinimalUserManager } from "../auth/AuthContext";
import { Callback } from "./Callback";

describe("Callback", () => {
  it("completes sign-in and navigates to /", async () => {
    renderWithProviders(<Callback />, { path: "/callback", routePath: "/callback" });

    await waitFor(() => expect(screen.getByTestId("navigated-to")).toHaveTextContent("/"));
  });

  it("shows an error message if the code exchange fails", async () => {
    const manager: MinimalUserManager = {
      getUser: () => Promise.resolve(null),
      signinRedirect: () => Promise.resolve(),
      signinRedirectCallback: () => Promise.reject(new Error("invalid_grant")),
      removeUser: () => Promise.resolve(),
    };

    renderWithProviders(<Callback />, { path: "/callback", routePath: "/callback", userManagerOverride: manager });

    expect(await screen.findByText(/sign-in failed: invalid_grant/i)).toBeInTheDocument();
  });
});
