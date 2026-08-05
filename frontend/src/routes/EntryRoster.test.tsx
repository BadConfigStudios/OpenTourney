import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { PersonaSwitcher } from "../auth/PersonaSwitcher";
import { EntryRoster } from "./EntryRoster";

const ASH = {
  id: "e1",
  pod_id: "pod-1",
  player_uuid: "u1",
  source_system: "opentourney-ui",
  metadata: { display_name: "Ash" },
};

const MISTY = {
  id: "e2",
  pod_id: "pod-1",
  player_uuid: "u2",
  source_system: "opentourney-ui",
  metadata: { display_name: "Misty" },
};

describe("EntryRoster", () => {
  beforeEach(() => localStorage.clear());

  it("lists entries by display name", async () => {
    server.use(http.get("/entries", () => HttpResponse.json([ASH])));

    renderWithProviders(<EntryRoster podId="pod-1" />);

    expect(await screen.findByText("Ash")).toBeInTheDocument();
  });

  it("adds an entry as Organizer", async () => {
    // Stateful handler: the component invalidates and refetches GET /entries
    // after the mutation, so a static handler would mask a broken add by
    // just re-serving the original (empty) list.
    let entries: (typeof ASH)[] = [];
    server.use(
      http.get("/entries", () => HttpResponse.json(entries)),
      http.post("/entries", async ({ request }) => {
        const body = (await request.json()) as { metadata: { display_name: string } };
        const created = { ...ASH, metadata: body.metadata };
        entries = [created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );

    renderWithProviders(<EntryRoster podId="pod-1" />);
    await screen.findByText("No entries yet.");

    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Ash" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Entry" }));

    expect(await screen.findByText("Ash")).toBeInTheDocument();
  });

  it("edits an entry's display name", async () => {
    // Stateful handler for the same reason as the add-entry test above.
    let current = ASH;
    server.use(
      http.get("/entries", () => HttpResponse.json([current])),
      http.patch("/entries/e1", async ({ request }) => {
        const body = (await request.json()) as { metadata: { display_name: string } };
        current = { ...current, metadata: body.metadata };
        return HttpResponse.json(current);
      }),
    );

    renderWithProviders(<EntryRoster podId="pod-1" />);
    await screen.findByText("Ash");

    fireEvent.click(screen.getByRole("button", { name: "Edit Ash" }));
    fireEvent.change(screen.getByLabelText("Edit name for Ash"), { target: { value: "Misty" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Misty")).toBeInTheDocument();
  });

  it("deletes an entry", async () => {
    let deleted = false;
    server.use(
      http.get("/entries", () => HttpResponse.json(deleted ? [] : [ASH])),
      http.delete("/entries/e1", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderWithProviders(<EntryRoster podId="pod-1" />);
    await screen.findByText("Ash");

    fireEvent.click(screen.getByRole("button", { name: "Delete Ash" }));

    await waitFor(() => expect(screen.queryByText("Ash")).not.toBeInTheDocument());
  });

  it("hides mutation controls for a non-Organizer persona", async () => {
    server.use(http.get("/entries", () => HttpResponse.json([ASH])));

    renderWithProviders(<EntryRoster podId="pod-1" />, { personaLabel: "Player" });

    await screen.findByText("Ash");
    expect(screen.queryByRole("button", { name: "Edit Ash" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete Ash" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Display name")).not.toBeInTheDocument();
  });

  it("disambiguates Edit/Delete buttons by entry name across multiple rows", async () => {
    server.use(http.get("/entries", () => HttpResponse.json([ASH, MISTY])));

    renderWithProviders(<EntryRoster podId="pod-1" />);
    await screen.findByText("Ash");
    await screen.findByText("Misty");

    const editAsh = screen.getByRole("button", { name: "Edit Ash" });
    const editMisty = screen.getByRole("button", { name: "Edit Misty" });
    const deleteAsh = screen.getByRole("button", { name: "Delete Ash" });
    const deleteMisty = screen.getByRole("button", { name: "Delete Misty" });
    expect(editAsh).toBeInTheDocument();
    expect(editMisty).toBeInTheDocument();
    expect(deleteAsh).toBeInTheDocument();
    expect(deleteMisty).toBeInTheDocument();

    fireEvent.click(editAsh);
    expect(screen.getByLabelText("Edit name for Ash")).toBeInTheDocument();
    expect(screen.queryByLabelText("Edit name for Misty")).not.toBeInTheDocument();
  });

  it("clears a stale mutation error once a different action is attempted", async () => {
    let entries = [ASH];
    server.use(
      http.get("/entries", () => HttpResponse.json(entries)),
      http.post("/entries", () => HttpResponse.json({ detail: "add failed" }, { status: 500 })),
      http.delete("/entries/e1", () => {
        entries = [];
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderWithProviders(<EntryRoster podId="pod-1" />);
    await screen.findByText("Ash");

    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Brock" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Entry" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("add failed");

    fireEvent.click(screen.getByRole("button", { name: "Delete Ash" }));

    await waitFor(() => expect(screen.queryByText("Ash")).not.toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("hides the edit row if the persona switches to non-Organizer mid-edit", async () => {
    // Regression test: EntryRoster keeps `editingId` as local component state,
    // which survives a persona switch (switching personas doesn't unmount the
    // component tree — it only clears the React Query cache). Render a real
    // PersonaSwitcher alongside EntryRoster, in the same AuthProvider, so we
    // exercise the actual live persona-change path rather than a fresh mount.
    server.use(http.get("/entries", () => HttpResponse.json([ASH])));

    renderWithProviders(
      <>
        <PersonaSwitcher />
        <EntryRoster podId="pod-1" />
      </>,
      { personaLabel: "Organizer" },
    );

    await screen.findByText("Ash");
    fireEvent.click(screen.getByRole("button", { name: "Edit Ash" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByLabelText("Edit name for Ash")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("persona"), { target: { value: "Player" } });

    await waitFor(() => expect(screen.getByLabelText("persona")).toHaveValue("Player"));
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Edit name for Ash")).not.toBeInTheDocument();
  });
});
