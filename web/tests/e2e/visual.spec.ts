// F4.6 visual snapshots: 7 pages at phone and desktop width, on the fixture.
// A layout or color change fails with a diff image in test-results/.
//   npx playwright test visual --update-snapshots   # accept a deliberate change
import { test, expect } from '@playwright/test';
import { PLENO, url } from './routes';

const PAGES: [string, string][] = [
  ['home-val', url('val', '')],
  ['plens-val', url('val', 'plens/')],
  ['intervencions-cas', url('cas', 'intervencions/')],
  ['mapa-val', url('val', 'mapa/')],
  ['pleno-cas', url('cas', `plens/${PLENO.id}/`)],
  ['pleno-split-val', url('val', 'plens/2022-03-31/')],
  ['metodologia-val', url('val', 'metodologia/')],
];
const WIDTHS = [375, 1280];

test.beforeEach(async ({ page }) => {
  // Same quote order and finished counters on every run: seeded Math.random, a fixed clock
  await page.addInitScript(() => {
    let seed = 42;
    Math.random = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  });
  await page.clock.install({ time: new Date('2026-10-18T10:00:00Z') });
});

for (const [name, path] of PAGES) {
  for (const width of WIDTHS) {
    test(`${name} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      // Sections that reveal on scroll: bring each into view once, then back to the top
      const height = await page.evaluate(() => document.body.scrollHeight);
      for (let y = 0; y < height; y += 600) {
        await page.evaluate((top) => window.scrollTo(0, top), y);
        await page.clock.runFor(500);
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      // The home's .reveal sections fade in when an IntersectionObserver fires, which does not
      // always happen on a fast scroll: show them all, in their final state
      await page.evaluate(() => document.querySelectorAll<HTMLElement>('.reveal').forEach((el) => {
        el.style.transition = 'none';
        el.classList.add('visible');
      }));
      await page.clock.runFor(10_000);     // counters and fades reach their final state
      // Leaflet maps draw after fetching their GeoJSON: wait for the 19 districts
      if (await page.locator('.leaflet-container').count()) {
        await expect.poll(() => page.locator('.leaflet-overlay-pane path').count()).toBeGreaterThanOrEqual(19);
        await page.clock.runFor(2_000);
      }
      await page.evaluate(() => document.fonts.ready);
      // CSS transitions (the mandate bars grow when they come into view) run on real time, not
      // on the fake clock: wait until every finite one has finished (the ticker loops forever)
      await page.waitForFunction(() => document.getAnimations().every(
        (a) => a.playState !== 'running' || a.effect?.getTiming().iterations === Infinity));
      // The home's district map (hydrated when visible) and its rotating quote change between
      // runs: they are masked there. The map has its own snapshot on the map page.
      const mask = name.startsWith('home')
        // islands are display: contents (no box of their own): mask what they render
        ? [page.locator('astro-island[component-export="DistrictMap"] > *'),
           page.locator('astro-island[component-export="HomeQuoteRotator"] > *')]
        : [];
      await expect(page).toHaveScreenshot(`${name}-${width}.png`, { fullPage: true, mask });
    });
  }
}
