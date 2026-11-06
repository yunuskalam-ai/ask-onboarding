import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // In development, send API calls to the backend on port 8000.
    proxy: { "/api": "http://localhost:8000" },
  },
  test: {
    include: ["src/**/*.test.ts"],
  },
});
