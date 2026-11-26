import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";

// Mopidy serves the build from /yap/, so asset URLs must be relative.
// `npm start` runs a dev server that proxies the Mopidy and Yap websockets to
// a Mopidy instance on localhost:6680 (e.g. `docker compose up`).
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "mopidy_yap/static",
    emptyOutDir: true,
  },
  server: {
    port: 3000,
    proxy: {
      "/mopidy": {target: "http://localhost:6680", ws: true},
      "/yap/ws": {target: "http://localhost:6680", ws: true},
    },
  },
});
