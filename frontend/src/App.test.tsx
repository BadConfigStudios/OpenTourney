import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("shows a login button when unauthenticated", async () => {
    // No AuthProvider override here, so App constructs a real oidc-client-ts
    // UserManager from config.json (served by the default msw handler in
    // ../test/server.ts) and, finding no stored user, renders the login gate.
    render(<App />);

    expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
  });
});
