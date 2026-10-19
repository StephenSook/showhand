import { existsSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// The phone clips stay out of git, so CI serves the page without them and the timer clock runs.
// A local build or the deployed site has them, and the video must then be the clock.
const clipsPresent =
  Boolean(process.env.BASE_URL) || existsSync(new URL("../../public/replay/take_0525/source.mp4", import.meta.url));

async function open(page: Page, path = "/"): Promise<string[]> {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.goto(path);
  await expect(page.locator("body")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
  return errors;
}

test("loads every take with its grades and a drawn robot", async ({ page }) => {
  const errors = await open(page);
  await expect(page.locator(".take")).toHaveCount(3);
  await expect(page.locator("body")).toHaveAttribute("data-clock", clipsPresent ? "video" : "timer");
  if (clipsPresent) await expect(page.locator("#missing-video")).toBeHidden();
  else await expect(page.locator("#missing-video")).toBeVisible();

  const timeline = page.locator("#timeline");
  await expect(timeline).toHaveAttribute("data-seconds", "7");
  await expect(timeline).toHaveAttribute("data-attempts", "2");
  // Three judged lanes, one cell per second.
  await expect(page.locator("#timeline .cell")).toHaveCount(21);
  await expect(page.locator("#verdict")).toContainText("failed on foot slip and out of balance");
  await expect(page.locator("#fusion")).toContainText("re-show window [2.0, 3.0] must exactly match cited negative evidence");
  await expect(page.locator("#fusion")).toContainText("Decision: re-show 1 to 2 s and 4 to 5 s");

  // The canvas has real pixels in it, not a blank clear colour.
  const distinct = await page.locator("#robot").evaluate((canvas: HTMLCanvasElement) => {
    const probe = document.createElement("canvas");
    probe.width = 64;
    probe.height = 64;
    const context = probe.getContext("2d")!;
    context.drawImage(canvas, 0, 0, 64, 64);
    const data = context.getImageData(0, 0, 64, 64).data;
    const colours = new Set<string>();
    for (let i = 0; i < data.length; i += 4) colours.add(`${data[i]},${data[i + 1]},${data[i + 2]}`);
    return colours.size;
  });
  expect(distinct).toBeGreaterThan(40);
  expect(errors).toEqual([]);
});

test("a cell click moves the clock and the detail card to that second", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: /Measured, 1 to 2 s: failed on worst joint error/ }).click();
  await expect(page.locator("#second-heading")).toHaveText("Second 1 to 2");
  await expect(page.locator("#second")).toContainText("Over the limit on worst joint error.");
  await expect(page.locator("#second")).toContainText("This second is in the re-show list.");
  await expect(page.locator("#second tr.over")).toHaveCount(1);
  await expect(page.locator("#second tr.over")).toContainText("at most 1 rad");
  await expect(page.locator("#clock")).toContainText("0:01.0");
  await expect(page.locator("#play")).toHaveText("Play");
});

test("switching takes swaps the record and keeps the choice in the address", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: /Take 0526/ }).click();
  await expect(page).toHaveURL(/\?take=take_0526$/);
  await expect(page.locator("body")).toHaveAttribute("data-take", "take_0526");
  await expect(page.locator("#fusion")).toContainText("accept contradicts mandatory negative evidence");
  await expect(page.locator("#fusion")).toContainText("Decision: re-show 0 to 1 s");
  await expect(page.locator("#timeline .cell")).toHaveCount(21);

  await page.goto("/?take=take_0527");
  await expect(page.locator("body")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
  await expect(page.locator("body")).toHaveAttribute("data-take", "take_0527");
  await expect(page.locator("#timeline")).toHaveAttribute("data-seconds", "6");
  await expect(page.getByRole("button", { name: /Take 0527/ })).toHaveAttribute("aria-pressed", "true");
});

test("play advances the clock and pause holds it", async ({ page }) => {
  await open(page);
  await page.locator("#scrub").fill("0");
  const play = page.locator("#play");
  if ((await play.textContent()) === "Play") await play.click();
  await expect(play).toHaveText("Pause");
  await page.waitForTimeout(1200);
  await play.click();
  await expect(play).toHaveText("Play");
  const held = await page.locator("#clock").textContent();
  await page.waitForTimeout(500);
  expect(await page.locator("#clock").textContent()).toBe(held);
  expect(held).not.toMatch(/^0:00\.0/);
});

for (const width of [390, 768, 1440]) {
  test(`no sideways scroll at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await open(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}

for (const scheme of ["light", "dark"] as const) {
  test(`no axe violations in ${scheme} mode`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
    await open(page);
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  });
}
