import { readFileSync } from "node:fs";
import { fileURLToPath, URL as NodeURL } from "node:url";
import { describe, expect, it } from "vitest";
import type { AppConfig } from "./types";

// Use node's URL explicitly (not the jsdom-provided global URL, which rejects
// file: URLs) to resolve the fixture path relative to this test file.
const fixturePath = fileURLToPath(new NodeURL("../../public/config.json", import.meta.url));

describe("public/config.json fixture", () => {
  const config = JSON.parse(readFileSync(fixturePath, "utf-8")) as AppConfig;

  it("has a non-empty oidcAuthority", () => {
    expect(typeof config.oidcAuthority).toBe("string");
    expect(config.oidcAuthority.length).toBeGreaterThan(0);
  });

  it("has a non-empty oidcClientId", () => {
    expect(typeof config.oidcClientId).toBe("string");
    expect(config.oidcClientId.length).toBeGreaterThan(0);
  });
});
