import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { NewEvent } from "./NewEvent";

describe("NewEvent", () => {
  beforeEach(() => localStorage.clear());

  it("creates an event and navigates to its detail page", async () => {
    server.use(
      http.post("/events", async ({ request }) => {
        const body = (await request.json()) as { date: string };
        return HttpResponse.json({ id: "new-1", date: body.date }, { status: 201 });
      }),
    );

    renderWithProviders(<NewEvent />, { path: "/events/new" });

    fireEvent.change(await screen.findByLabelText("Date"), { target: { value: "2026-08-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Event" }));

    expect(await screen.findByTestId("navigated-to")).toHaveTextContent("/events/new-1");
  });

  it("surfaces a validation error from the backend", async () => {
    server.use(
      http.post("/events", () => HttpResponse.json({ detail: "date is required" }, { status: 422 })),
    );

    renderWithProviders(<NewEvent />, { path: "/events/new" });

    fireEvent.change(await screen.findByLabelText("Date"), { target: { value: "2026-08-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Event" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("date is required");
  });

  it("redirects a non-Organizer persona away from the form", async () => {
    renderWithProviders(<NewEvent />, { path: "/events/new", personaLabel: "Player" });

    expect(await screen.findByTestId("navigated-to")).toHaveTextContent("/");
  });
});
