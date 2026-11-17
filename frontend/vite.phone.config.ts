import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/** The phone page: a separate small bundle the app publishes to GitHub Pages; relative paths so it works under any URL. */
export default defineConfig({
  plugins: [react()],
  base: "./",
  publicDir: false,
  server: { port: 5181, strictPort: true },
  build: {
    outDir: "dist/phone",
    emptyOutDir: true,
    rollupOptions: { input: "phone.html" },
  },
});
