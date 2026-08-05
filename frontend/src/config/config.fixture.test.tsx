import { readFileSync } from "node:fs";
import { fileURLToPath, URL as NodeURL } from "node:url";
import { describe, expect, it } from "vitest";
import type { AppConfig, PersonaRole } from "./types";

const VALID_ROLES: PersonaRole[] = ["organizer", "scorekeeper", "player"];

// Use node's URL explicitly (not the jsdom-provided global URL, which rejects
// file: URLs) to resolve the fixture path relative to this test file.
const fixturePath = fileURLToPath(new NodeURL("../../public/config.json", import.meta.url));

describe("public/config.json fixture", () => {
  const config = JSON.parse(readFileSync(fixturePath, "utf-8")) as AppConfig;

  it("has a non-empty personas array", () => {
    expect(Array.isArray(config.personas)).toBe(true);
    expect(config.personas.length).toBeGreaterThan(0);
  });

  it("has a valid role and non-empty label/token for every persona", () => {
    for (const persona of config.personas) {
      expect(VALID_ROLES).toContain(persona.role);
      expect(typeof persona.label).toBe("string");
      expect(persona.label.length).toBeGreaterThan(0);
      expect(typeof persona.token).toBe("string");
      expect(persona.token.length).toBeGreaterThan(0);
    }
  });
});
