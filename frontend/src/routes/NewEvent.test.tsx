import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { NewEvent } from "./NewEvent";

describe("NewEvent", () => {
  beforeEach(() => localStorage.clear());

  it("creates an event under an existing organization and navigates to its detail page", async () => {
    server.use(
      http.get("/organizations", () =>
        HttpResponse.json([{ id: "org-1", name: "Dragon's Den" }]),
      ),
      http.post("/events", async ({ request }) => {
        const body = (await request.json()) as { date: string; name: string; organization_id: string };
        return HttpResponse.json(
          { id: "new-1", date: body.date, name: body.name, description: null, organization_id: body.organization_id },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<NewEvent />, { path: "/events/new" });

    await screen.findByText("Dragon's Den");
    fireEvent.change(screen.getByLabelText("Event name"), { target: { value: "Friday Standard" } });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-08-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Event" }));

    expect(await screen.findByTestId("navigated-to")).toHaveTextContent("/events/new-1");
  });

  it("offers inline organization creation when the caller belongs to no organizations", async () => {
    server.use(
      http.get("/organizations", () => HttpResponse.json([])),
      http.post("/organizations", async ({ request }) => {
        const body = (await request.json()) as { name: string };
        return HttpResponse.json({ id: "org-new", name: body.name }, { status: 201 });
      }),
      http.post("/events", async ({ request }) => {
        const body = (await request.json()) as { date: string; name: string; organization_id: string };
        return HttpResponse.json(
          { id: "new-2", date: body.date, name: body.name, description: null, organization_id: body.organization_id },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<NewEvent />, { path: "/events/new" });

    await screen.findByLabelText("New organization name");
    fireEvent.change(screen.getByLabelText("New organization name"), { target: { value: "New Store" } });
    fireEvent.click(screen.getByRole("button", { name: "Create organization" }));

    await screen.findByText("New Store");
    fireEvent.change(screen.getByLabelText("Event name"), { target: { value: "Friday Standard" } });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-08-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Event" }));

    expect(await screen.findByTestId("navigated-to")).toHaveTextContent("/events/new-2");
  });

  it("surfaces a validation error from the backend", async () => {
    server.use(
      http.get("/organizations", () =>
        HttpResponse.json([{ id: "org-1", name: "Dragon's Den" }]),
      ),
      http.post("/events", () => HttpResponse.json({ detail: "date is required" }, { status: 422 })),
    );

    renderWithProviders(<NewEvent />, { path: "/events/new" });

    await screen.findByText("Dragon's Den");
    fireEvent.change(screen.getByLabelText("Event name"), { target: { value: "Friday Standard" } });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-08-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Event" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("date is required");
  });

  it("redirects a non-Organizer persona away from the form", async () => {
    renderWithProviders(<NewEvent />, { path: "/events/new", role: "player" });

    expect(await screen.findByTestId("navigated-to")).toHaveTextContent("/");
  });
});
