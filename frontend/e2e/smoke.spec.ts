import { expect, test } from "@playwright/test";

test.describe("Smoke Tests", () => {
  test("Templates page loads", async ({ page }) => {
    await page.goto("/templates");
    await expect(page.locator("text=Device Templates")).toBeVisible();
  });

  test("Devices page loads", async ({ page }) => {
    await page.goto("/devices");
    await expect(page.locator("text=Device")).toBeVisible();
  });

  test("Simulation page loads", async ({ page }) => {
    await page.goto("/simulation");
    await expect(page.locator("text=Simulation")).toBeVisible();
  });

  test("Monitor page loads", async ({ page }) => {
    await page.goto("/monitor");
    await expect(page.locator("text=Monitor")).toBeVisible();
  });

  test("Settings page loads with export/import buttons", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("text=Settings")).toBeVisible();
    await expect(page.locator("text=Export Config")).toBeVisible();
    await expect(page.locator("text=Import Config")).toBeVisible();
  });
});
