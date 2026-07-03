import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend runs on :8000 (uvicorn) and serves the API under /api. In dev we
// proxy /api -> :8000 WITHOUT rewriting the prefix, so the exact same frontend
// code (which calls /api/...) works in dev and in the single-service prod build.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
