import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendUrl = process.env.VITE_API_URL || "http://localhost:8099";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5214,
    host: true,
    allowedHosts: ["worldforge.ssantoro.fr", "172.16.16.99", "172.16.16.252"],
    proxy: {
      "/api": {
        target: backendUrl,
        changeOrigin: true,
        timeout: 300000, // 5 minutes for long LLM calls
      },
      "/ws": {
        target: backendUrl,
        ws: true,
      },
    },
  },
});
