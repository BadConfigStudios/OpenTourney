import { act, render, screen } from "@testing-library/react";
import type { User } from "oidc-client-ts";
import { describe, expect, it, vi } from "vitest";
import { ConfigProvider } from "../config/ConfigProvider";
import { AuthProvider, useAuth, type MinimalUserManager } from "./AuthContext";

function Probe() {
  const { currentUser, apiFetch } = useAuth();
  return (
    <div>
      <span>{currentUser.role}</span>
      <button onClick={() => apiFetch("/events")}>fetch</button>
    </div>
  );
}

function fakeConfigFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ oidcAuthority: "http://zitadel.test", oidcClientId: "test-client-id" }),
    }),
  );
}

function authenticatedManager(roles: string[]): MinimalUserManager {
  const user = { access_token: "test-access-token", expired: false, profile: { roles } } as unknown as User;
  return {
    getUser: () => Promise.resolve(user),
    signinRedirect: vi.fn().mockResolvedValue(undefined),
    signinRedirectCallback: () => Promise.resolve(user),
    removeUser: vi.fn().mockResolvedValue(undefined),
  };
}

describe("AuthProvider", () => {
  it("derives currentUser.role from the roles claim and apiFetch attaches the access token", async () => {
    fakeConfigFetch();
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    // Config-loading fetch is stubbed globally above; apiFetch uses the same
    // global fetch, so intercept calls to "/events" specifically after mount.
    vi.stubGlobal("fetch", (...args: Parameters<typeof fetch>) => {
      const [input] = args;
      if (typeof input === "string" && input === "/events") return fetchSpy(...args);
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ oidcAuthority: "http://zitadel.test", oidcClientId: "test-client-id" }),
      } as Response);
    });

    render(
      <ConfigProvider>
        <AuthProvider userManagerOverride={authenticatedManager(["scorekeeper"])}>
          <Probe />
        </AuthProvider>
      </ConfigProvider>,
    );

    expect(await screen.findByText("scorekeeper")).toBeInTheDocument();

    await act(async () => screen.getByText("fetch").click());

    expect(fetchSpy).toHaveBeenCalledWith(
      "/events",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-access-token",
          Accept: "application/json",
        }),
      }),
    );
  });

  it("defaults to the player role when the token has no recognized role", async () => {
    fakeConfigFetch();
    render(
      <ConfigProvider>
        <AuthProvider userManagerOverride={authenticatedManager([])}>
          <Probe />
        </AuthProvider>
      </ConfigProvider>,
    );

    expect(await screen.findByText("player")).toBeInTheDocument();
  });

  it("shows a Login button and triggers signinRedirect when no user session exists", async () => {
    fakeConfigFetch();
    const signinRedirect = vi.fn().mockResolvedValue(undefined);
    const manager: MinimalUserManager = {
      getUser: () => Promise.resolve(null),
      signinRedirect,
      signinRedirectCallback: () => Promise.reject(new Error("not used in this test")),
      removeUser: () => Promise.resolve(),
    };

    render(
      <ConfigProvider>
        <AuthProvider userManagerOverride={manager}>
          <Probe />
        </AuthProvider>
      </ConfigProvider>,
    );

    const button = await screen.findByRole("button", { name: /log in/i });
    await act(async () => button.click());

    expect(signinRedirect).toHaveBeenCalledTimes(1);
  });
});
