import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  envDir: "..",
  server: {
    host: "localhost",
    port: 5173,
  },
  test: {
    environment: "jsdom",
  },
});
