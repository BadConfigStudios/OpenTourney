import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

const DEFAULT_CONFIG = {
  oidcAuthority: "http://zitadel.test",
  oidcClientId: "test-client-id",
  oidcProjectId: "test-project-id",
};

export const server = setupServer(http.get("/config.json", () => HttpResponse.json(DEFAULT_CONFIG)));
