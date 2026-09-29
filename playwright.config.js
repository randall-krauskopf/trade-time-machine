import {defineConfig, devices} from "@playwright/test";

const port = Number(process.env.SMOKE_PORT || 4173);

export default defineConfig({
  testDir: "tests/smoke",
  workers: 1, // python3 -m http.server stalls when several browsers load module graphs at once.
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    ...devices["Desktop Chrome"],
  },
  webServer: {
    command: `python3 -m http.server ${port} --bind 127.0.0.1 --directory docs`,
    url: `http://127.0.0.1:${port}/index.html`,
    reuseExistingServer: !process.env.CI,
  },
});
