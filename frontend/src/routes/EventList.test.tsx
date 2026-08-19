import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { EventList } from "./EventList";

describe("EventList", () => {
  beforeEach(() => localStorage.clear());

  it("renders events as links to their detail page", async () => {
    server.use(
      http.get("/events", () =>
        HttpResponse.json([
          { id: "1", date: "2026-08-01", name: "Friday Standard", description: null, organization_id: "org-1" },
          { id: "2", date: "2026-09-01", name: "Regional Qualifier", description: null, organization_id: "org-1" },
        ]),
      ),
    );

    renderWithProviders(<EventList />);

    expect(await screen.findByRole("link", { name: "Friday Standard" })).toHaveAttribute("href", "/events/1");
    expect(screen.getByRole("link", { name: "Regional Qualifier" })).toHaveAttribute("href", "/events/2");
    // renderWithProviders defaults role to "organizer" when unspecified.
    expect(screen.getByRole("link", { name: "New Event" })).toHaveAttribute("href", "/events/new");
  });

  it("shows New Event only for the Organizer persona", async () => {
    server.use(http.get("/events", () => HttpResponse.json([])));

    renderWithProviders(<EventList />, { role: "scorekeeper" });

    await screen.findByText("No events yet.");
    expect(screen.queryByRole("link", { name: "New Event" })).not.toBeInTheDocument();
  });

  it("surfaces a fetch error via ErrorBanner", async () => {
    server.use(http.get("/events", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));

    renderWithProviders(<EventList />);

    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});
