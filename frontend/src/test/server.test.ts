import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "./server";

describe("msw test server", () => {
  it("intercepts fetch and returns the default config handler", async () => {
    const response = await fetch("/config.json");
    const body = await response.json();

    expect(body).toEqual({
      oidcAuthority: "http://zitadel.test",
      oidcClientId: "test-client-id",
      oidcProjectId: "test-project-id",
    });
  });

  it("lets a test override a handler for one request", async () => {
    server.use(http.get("/events", () => HttpResponse.json([{ id: "1", date: "2026-08-01" }])));

    const response = await fetch("/events");

    expect(await response.json()).toEqual([{ id: "1", date: "2026-08-01" }]);
  });
});
