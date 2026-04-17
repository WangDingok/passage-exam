import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    allowedHosts: [
      "gerardo-nonliquefying-celine.ngrok-free.app",
      "vince-detectable-nonverminously.ngrok-free.dev"
    ],
    proxy: {
      "/drafts": "http://127.0.0.1:8001",
      "/health": "http://127.0.0.1:8001"
    }
  }
});
