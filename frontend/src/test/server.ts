import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

const DEFAULT_CONFIG = {
  personas: [
    { label: "Organizer", role: "organizer", token: "org-token" },
    { label: "Scorekeeper", role: "scorekeeper", token: "sk-token" },
    { label: "Player", role: "player", token: "player-token" },
  ],
};

export const server = setupServer(http.get("/config.json", () => HttpResponse.json(DEFAULT_CONFIG)));
