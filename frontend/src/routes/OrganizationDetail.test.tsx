import { QueryClient } from "@tanstack/react-query";
import { fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { OrganizationDetail } from "./OrganizationDetail";

const OWNER_ORG = { id: "org-1", name: "Dragon's Den", viewer_role: "owner" };
const ORGANIZER_ORG = { id: "org-1", name: "Dragon's Den", viewer_role: "organizer" };
const SCOREKEEPER_ORG = { id: "org-1", name: "Dragon's Den", viewer_role: "scorekeeper" };
const JUDGE_ORG = { id: "org-1", name: "Dragon's Den", viewer_role: "judge" };
const MEMBERS = [
  { id: "m1", organization_id: "org-1", player_uuid: "p1", source_system: "club-checkin", role: "owner" },
  { id: "m2", organization_id: "org-1", player_uuid: "p2", source_system: "club-checkin", role: "scorekeeper" },
];

function renderDetail() {
  renderWithProviders(<OrganizationDetail />, {
    path: "/organizations/org-1",
    routePath: "/organizations/:organizationId",
  });
}

describe("OrganizationDetail", () => {
  beforeEach(() => localStorage.clear());

  it("shows the roster with identity and role for any member", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(ORGANIZER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    expect(await screen.findByText("p1")).toBeInTheDocument();
    expect(screen.getByText("p2")).toBeInTheDocument();
    expect(screen.getAllByText("club-checkin")).toHaveLength(2);
  });

  it("hides owner-only controls for a non-owner member", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(ORGANIZER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    expect(screen.queryByLabelText("Organization name")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("New member player UUID")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
  });

  it("shows rename, add-member, per-row role select, and remove for an owner", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    expect(screen.getByLabelText("Organization name")).toBeInTheDocument();
    expect(screen.getByLabelText("New member player UUID")).toBeInTheDocument();
    expect(await screen.findAllByRole("button", { name: "Remove" })).toHaveLength(2);
  });

  it("renames the organization", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
      http.patch("/organizations/org-1", async ({ request }) => {
        const body = (await request.json()) as { name: string };
        return HttpResponse.json({ id: "org-1", name: body.name });
      }),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    fireEvent.change(screen.getByLabelText("Organization name"), { target: { value: "New Name" } });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));

    expect(await screen.findByText("New Name")).toBeInTheDocument();
  });

  it("tracks server renames after a successful save instead of pinning to the local draft", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
      http.patch("/organizations/org-1", async ({ request }) => {
        const body = (await request.json()) as { name: string };
        return HttpResponse.json({ id: "org-1", name: body.name });
      }),
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    renderWithProviders(<OrganizationDetail />, {
      path: "/organizations/org-1",
      routePath: "/organizations/:organizationId",
      queryClient,
    });

    await screen.findByText("Dragon's Den");
    fireEvent.change(screen.getByLabelText("Organization name"), { target: { value: "First Edit" } });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));
    await screen.findByText("First Edit");

    // Simulate an out-of-band cache update (another tab's rename, a background
    // refetch) landing after the local save. If the local draft were still
    // "First Edit", the input would keep showing it instead of this new name.
    queryClient.setQueryData(["organizations", "org-1"], {
      id: "org-1",
      name: "External Rename",
      viewer_role: "owner",
    });
    expect(await screen.findByText("External Rename")).toBeInTheDocument();
    expect(screen.getByLabelText("Organization name")).toHaveValue("External Rename");
  });

  it("disables Save name and does not fire the mutation when the field is cleared to empty", async () => {
    let patchCalled = false;
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
      http.patch("/organizations/org-1", async ({ request }) => {
        patchCalled = true;
        const body = (await request.json()) as { name: string };
        return HttpResponse.json({ id: "org-1", name: body.name });
      }),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    const input = screen.getByLabelText("Organization name");
    const saveButton = screen.getByRole("button", { name: "Save name" });

    // Unedited: displays org.name, but must not send an empty PATCH if clicked.
    expect(input).toHaveValue("Dragon's Den");

    fireEvent.change(input, { target: { value: "" } });
    expect(saveButton).toBeDisabled();

    fireEvent.click(saveButton);
    expect(patchCalled).toBe(false);
  });

  it("adds a new member", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
      http.post("/organizations/org-1/members", async ({ request }) => {
        const body = (await request.json()) as { player_uuid: string; source_system: string; role: string };
        return HttpResponse.json(
          { id: "m3", organization_id: "org-1", player_uuid: body.player_uuid, source_system: body.source_system, role: body.role },
          { status: 201 },
        );
      }),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    fireEvent.change(screen.getByLabelText("New member player UUID"), { target: { value: "p3" } });
    fireEvent.change(screen.getByLabelText("New member source system"), { target: { value: "club-checkin" } });
    fireEvent.change(screen.getByLabelText("New member role"), { target: { value: "judge" } });
    fireEvent.click(screen.getByRole("button", { name: "Add member" }));

    expect(await screen.findByText("p3")).toBeInTheDocument();
  });

  it("changes a member's role", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
      http.patch("/organizations/org-1/members/m2", async ({ request }) => {
        const body = (await request.json()) as { role: string };
        return HttpResponse.json({ id: "m2", organization_id: "org-1", player_uuid: "p2", source_system: "club-checkin", role: body.role });
      }),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    const row = (await screen.findByText("p2")).closest("tr");
    if (!row) throw new Error("expected a table row for p2");
    fireEvent.change(within(row).getByRole("combobox"), { target: { value: "organizer" } });

    expect(await within(row).findByText("organizer")).toBeInTheDocument();
  });

  it("removes a member", async () => {
    let members = MEMBERS;
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(members)),
      http.delete("/organizations/org-1/members/m2", () => {
        members = members.filter((member) => member.id !== "m2");
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderDetail();

    await screen.findByText("p2");
    const row = screen.getByText("p2").closest("tr");
    if (!row) throw new Error("expected a table row for p2");
    fireEvent.click(within(row).getByRole("button", { name: "Remove" }));

    await screen.findByText("Dragon's Den");
    expect(screen.queryByText("p2")).not.toBeInTheDocument();
  });

  it("surfaces the lockout-guard 409 inline", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
      http.delete("/organizations/org-1/members/m1", () =>
        HttpResponse.json({ detail: "cannot revoke the organization's only owner" }, { status: 409 }),
      ),
    );

    renderDetail();

    await screen.findByText("p1");
    const row = screen.getByText("p1").closest("tr");
    if (!row) throw new Error("expected a table row for p1");
    fireEvent.click(within(row).getByRole("button", { name: "Remove" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("cannot revoke the organization's only owner");
  });

  it("shows a permission message instead of the roster for a scorekeeper viewer, without fetching members", async () => {
    let membersFetched = false;
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(SCOREKEEPER_ORG)),
      http.get("/organizations/org-1/members", () => {
        membersFetched = true;
        return HttpResponse.json(
          { detail: "organizer role required for this organization" },
          { status: 403 },
        );
      }),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    expect(
      await screen.findByText("You don't have permission to view this organization's member roster."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(membersFetched).toBe(false);
  });

  it("shows the same permission message for a judge viewer", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(JUDGE_ORG)),
      http.get("/organizations/org-1/members", () =>
        HttpResponse.json({ detail: "organizer role required for this organization" }, { status: 403 }),
      ),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    expect(
      await screen.findByText("You don't have permission to view this organization's member roster."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
