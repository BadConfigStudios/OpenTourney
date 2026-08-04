import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConfigProvider, useConfig } from "./ConfigProvider";

function Probe() {
  const config = useConfig();
  return <div>{config.personas.map((p) => p.label).join(",")}</div>;
}

describe("ConfigProvider", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              personas: [{ label: "Organizer", role: "organizer", token: "t" }],
            }),
        }),
      ) as unknown as typeof fetch,
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads config.json and provides it via useConfig", async () => {
    render(
      <ConfigProvider>
        <Probe />
      </ConfigProvider>,
    );

    await waitFor(() => expect(screen.getByText("Organizer")).toBeInTheDocument());
  });

  it("shows a fatal error if config.json fails to load", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) })) as unknown as typeof fetch,
    );

    render(
      <ConfigProvider>
        <Probe />
      </ConfigProvider>,
    );

    await waitFor(() =>
      expect(screen.getByText(/failed to load app configuration/i)).toBeInTheDocument(),
    );
  });

  it("shows a fatal error if config.json has no personas", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })) as unknown as typeof fetch,
    );

    render(
      <ConfigProvider>
        <Probe />
      </ConfigProvider>,
    );

    await waitFor(() =>
      expect(screen.getByText(/failed to load app configuration/i)).toBeInTheDocument(),
    );
  });
});
