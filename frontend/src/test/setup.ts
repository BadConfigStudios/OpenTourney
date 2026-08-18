import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
  server.resetHandlers();
  cleanup();
  localStorage.clear();
  // renderWithProviders syncs window.history to the routed test path (see
  // src/test/renderWithProviders.tsx); reset it so one test's path can't leak
  // into the next.
  window.history.pushState({}, "", "/");
});

afterAll(() => server.close());
