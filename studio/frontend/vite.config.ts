/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5710, proxy: { "/api": `http://127.0.0.1:${process.env.STUDIO_API_PORT ?? 8710}` } },
  test: { environment: "jsdom", globals: false },
});
