import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Standard Vite config used by Docker builds (npm ci installs packages normally).
// For local development on VirtualBox shared folder, use:
//   npm run build:local  (invokes external vite config with custom module resolver)
//   npm run dev          (same)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  },
});
