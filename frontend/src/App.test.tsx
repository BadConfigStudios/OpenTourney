import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("renders the persona switcher and the default route", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({ personas: [{ label: "Organizer", role: "organizer", token: "t" }] }),
      }),
    );

    render(<App />);

    expect(await screen.findByRole("combobox", { name: /persona/i })).toBeInTheDocument();
    expect(screen.getByText("Events")).toBeInTheDocument();
  });
});
