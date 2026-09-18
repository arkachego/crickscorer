import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import type { Plugin } from "vite";

function healthEndpoint(): Plugin {
  return {
    name: "crickscorer-viewer-health",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url?.split("?")[0]?.replace(/\/$/, "") ?? "";
        if (url === "/health") {
          const body = JSON.stringify({
            status: "ok",
            service: "viewer",
            phase: 20,
          });
          res.statusCode = 200;
          res.setHeader("Content-Type", "application/json");
          res.end(body);
          return;
        }
        next();
      });
    },
  };
}

const proxyTarget = process.env.API_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss(), healthEndpoint()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: process.env.HOST || "0.0.0.0",
    port: Number(process.env.PORT || "5174"),
    proxy: {
      "/api": {
        target: proxyTarget,
        changeOrigin: true,
      },
      "/socket.io": {
        target: proxyTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});
