import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfigProvider } from "../config/ConfigProvider";
import { AuthProvider, useAuth } from "./AuthContext";

const CONFIG = {
  personas: [
    { label: "Organizer", role: "organizer" as const, token: "org-token" },
    { label: "Player", role: "player" as const, token: "player-token" },
  ],
};

function Probe() {
  const { currentPersona, setPersona, apiFetch } = useAuth();
  return (
    <div>
      <span>{currentPersona.label}</span>
      <button onClick={() => setPersona("Player")}>switch</button>
      <button onClick={() => apiFetch("/events")}>fetch</button>
    </div>
  );
}

function renderWithProviders() {
  const queryClient = new QueryClient();
  vi.spyOn(queryClient, "clear");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(CONFIG) }));

  render(
    <QueryClientProvider client={queryClient}>
      <ConfigProvider>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </ConfigProvider>
    </QueryClientProvider>,
  );

  return queryClient;
}

describe("AuthProvider", () => {
  beforeEach(() => localStorage.clear());

  it("defaults to the first persona and switches on demand, clearing the query cache", async () => {
    const queryClient = renderWithProviders();
    expect(await screen.findByText("Organizer")).toBeInTheDocument();

    await act(async () => screen.getByText("switch").click());

    expect(screen.getByText("Player")).toBeInTheDocument();
    expect(queryClient.clear).toHaveBeenCalledTimes(1);
  });

  it("apiFetch attaches the current persona's Bearer token", async () => {
    renderWithProviders();
    await screen.findByText("Organizer");
    const fetchSpy = vi.mocked(fetch);
    fetchSpy.mockClear();

    await act(async () => screen.getByText("fetch").click());

    expect(fetchSpy).toHaveBeenCalledWith(
      "/events",
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer org-token" }) }),
    );
  });
});
