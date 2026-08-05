import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Proxy the backend's real path prefixes to the local dev backend
    // (see backend/Dockerfile.prod / uvicorn, which serves on :8000),
    // mirroring the prod nginx.conf proxy_pass blocks below.
    proxy: {
      "/events": "http://localhost:8000",
      // The SPA route /pods/:podId/pairings is not a backend endpoint (unlike
      // the sibling /pods/:podId/report route, which IS real — see PR4 and
      // the matching comment in nginx.conf). bypass() returning the request's
      // own url tells Vite's proxy middleware to skip proxying and fall
      // through to Vite's own dev server / SPA handling instead.
      "/pods": {
        target: "http://localhost:8000",
        bypass: (req) => {
          if (req.url && /\/pairings$/.test(req.url)) {
            return req.url;
          }
        },
      },
      "/entries": "http://localhost:8000",
      "/matches": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    unstubGlobals: true,
    restoreMocks: true,
  },
});
