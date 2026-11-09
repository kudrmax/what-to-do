import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const BACKEND = process.env.WHERE_TO_GO_BACKEND ?? "http://127.0.0.1:18765";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: { "/api": { target: BACKEND, rewrite: (path) => path.replace(/^\/api/, "") } },
  },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"] },
});
