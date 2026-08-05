import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Real browser navigation (hard refresh, direct link) sends
// "Accept: text/html,..."; the frontend's own apiFetch sends
// "Accept: application/json" (see AuthContext.tsx). Some of these prefixes
// collide with SPA client-side routes at the exact same path
// (/events/:eventId, /pods/:podId/report) — checking Accept tells the two
// apart regardless of path, mirroring the nginx.conf dispatch used in prod.
function bypassOnHtmlAccept(req: { headers: { accept?: string }; url?: string }) {
  if (req.url && /text\/html/.test(req.headers.accept ?? "")) {
    return req.url;
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Proxy the backend's real path prefixes to the local dev backend
    // (see backend/Dockerfile.prod / uvicorn, which serves on :8000),
    // mirroring the prod nginx.conf proxy_pass blocks below.
    proxy: {
      "/events": { target: "http://localhost:8000", bypass: bypassOnHtmlAccept },
      "/pods": { target: "http://localhost:8000", bypass: bypassOnHtmlAccept },
      "/entries": { target: "http://localhost:8000", bypass: bypassOnHtmlAccept },
      "/matches": { target: "http://localhost:8000", bypass: bypassOnHtmlAccept },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    unstubGlobals: true,
    restoreMocks: true,
  },
});
