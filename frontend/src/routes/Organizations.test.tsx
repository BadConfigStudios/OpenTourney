import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { Organizations } from "./Organizations";

describe("Organizations", () => {
  beforeEach(() => localStorage.clear());

  it("redirects straight to the detail page when the caller belongs to exactly one organization", async () => {
    server.use(
      http.get("/organizations", () => HttpResponse.json([{ id: "org-1", name: "Dragon's Den" }])),
    );

    renderWithProviders(<Organizations />, { path: "/organizations" });

    expect(await screen.findByTestId("navigated-to")).toHaveTextContent("/organizations/org-1");
  });

  it("lists all organizations as links when the caller belongs to more than one", async () => {
    server.use(
      http.get("/organizations", () =>
        HttpResponse.json([
          { id: "org-1", name: "Dragon's Den" },
          { id: "org-2", name: "Second Store" },
        ]),
      ),
    );

    renderWithProviders(<Organizations />, { path: "/organizations" });

    expect(await screen.findByRole("link", { name: "Dragon's Den" })).toHaveAttribute(
      "href",
      "/organizations/org-1",
    );
    expect(screen.getByRole("link", { name: "Second Store" })).toHaveAttribute(
      "href",
      "/organizations/org-2",
    );
  });

  it("shows an empty state when the caller belongs to no organizations", async () => {
    server.use(http.get("/organizations", () => HttpResponse.json([])));

    renderWithProviders(<Organizations />, { path: "/organizations" });

    expect(await screen.findByText("You don't belong to any organizations yet.")).toBeInTheDocument();
  });
});
