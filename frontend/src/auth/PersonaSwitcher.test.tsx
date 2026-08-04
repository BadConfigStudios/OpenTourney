import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfigProvider } from "../config/ConfigProvider";
import { AuthProvider } from "./AuthContext";
import { PersonaSwitcher } from "./PersonaSwitcher";

const CONFIG = {
  personas: [
    { label: "Organizer", role: "organizer" as const, token: "org-token" },
    { label: "Player", role: "player" as const, token: "player-token" },
  ],
};

describe("PersonaSwitcher", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(CONFIG) }));
  });

  it("lists every persona and switches the selection", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ConfigProvider>
          <AuthProvider>
            <PersonaSwitcher />
          </AuthProvider>
        </ConfigProvider>
      </QueryClientProvider>,
    );

    const select = await screen.findByRole("combobox", { name: /persona/i });
    expect(select).toHaveValue("Organizer");

    await userEvent.selectOptions(select, "Player");

    expect(select).toHaveValue("Player");
  });
});
