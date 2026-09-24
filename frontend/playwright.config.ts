import { defineConfig } from "@playwright/test";
const port = process.env.LESS_E2E_PORT ?? "5173";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `npm run dev -- --port ${port}`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: true,
  },
});
