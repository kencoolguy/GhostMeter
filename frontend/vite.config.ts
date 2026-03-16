import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";

const EXT_MODULES = "/home/ken/.ghostmeter-frontend-modules/node_modules";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      { find: /^react-router-dom$/, replacement: path.join(EXT_MODULES, "react-router-dom") },
      { find: /^react-router-dom\/(.*)$/, replacement: path.join(EXT_MODULES, "react-router-dom") + "/$1" },
      { find: /^react-router\/dom$/, replacement: path.join(EXT_MODULES, "react-router/dist/development/dom-export.mjs") },
      { find: /^react-router$/, replacement: path.join(EXT_MODULES, "react-router/dist/development/index.mjs") },
      { find: /^react\/(.*)$/, replacement: path.join(EXT_MODULES, "react") + "/$1" },
      { find: /^react$/, replacement: path.join(EXT_MODULES, "react") },
      { find: /^react-dom\/(.*)$/, replacement: path.join(EXT_MODULES, "react-dom") + "/$1" },
      { find: /^react-dom$/, replacement: path.join(EXT_MODULES, "react-dom") },
      { find: /^zustand\/(.*)$/, replacement: path.join(EXT_MODULES, "zustand") + "/$1" },
      { find: /^zustand$/, replacement: path.join(EXT_MODULES, "zustand") },
      { find: /^axios$/, replacement: path.join(EXT_MODULES, "axios") },
    ],
  },
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
