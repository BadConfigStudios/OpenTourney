import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConfigProvider, useConfig } from "./ConfigProvider";

function Probe() {
  const config = useConfig();
  return <div>{config.oidcClientId}</div>;
}

describe("ConfigProvider", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({ oidcAuthority: "http://zitadel.test", oidcClientId: "test-client-id" }),
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

    await waitFor(() => expect(screen.getByText("test-client-id")).toBeInTheDocument());
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

  it("shows a fatal error if config.json has no oidcAuthority", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: true, json: () => Promise.resolve({ oidcClientId: "test-client-id" }) }),
      ) as unknown as typeof fetch,
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

  it("shows a fatal error if config.json has an empty oidcClientId (e.g. unset envsubst var)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ oidcAuthority: "http://zitadel.test", oidcClientId: "" }),
        }),
      ) as unknown as typeof fetch,
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
