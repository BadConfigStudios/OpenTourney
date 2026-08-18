import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { renderWithProviders } from "../test/renderWithProviders";
import { Layout } from "./Layout";

describe("Layout", () => {
  beforeEach(() => localStorage.clear());

  it("shows an Organizations nav link for an Organizer persona", async () => {
    renderWithProviders(<Layout />, { path: "/" });

    expect(await screen.findByRole("link", { name: "Organizations" })).toHaveAttribute(
      "href",
      "/organizations",
    );
  });

  it("hides the Organizations nav link for a non-Organizer persona", async () => {
    renderWithProviders(<Layout />, { path: "/", role: "player" });

    await screen.findByText("OpenTourney");
    expect(screen.queryByRole("link", { name: "Organizations" })).not.toBeInTheDocument();
  });
});
