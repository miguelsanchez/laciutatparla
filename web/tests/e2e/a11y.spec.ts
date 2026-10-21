// F4.5 accessibility: axe on 5 pages against a baseline that can only shrink (ratchet).
// A new rule violated, or more elements failing a known rule, fails the test.
//   A11Y_UPDATE=1 npx playwright test a11y   # rewrite the baseline (after fixing, to lock it in)
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { resolve } from 'path';
import { ENTITY, PLENO, url } from './routes';

const BASELINE = resolve(process.cwd(), 'tests/a11y-baseline.json');
const PAGES = [
  url('val', ''),
  url('val', 'plens/'),
  url('cas', 'intervencions/'),
  url('val', 'mapa/'),
  url('cas', `entitats/${ENTITY.id}/`),
  url('val', `plens/${PLENO.id}/`),
  url('val', 'plens/2022-03-31/'),   // split recording: the video block (plan 3.11)
  url('cas', 'plens/2023-10-24/'),   // shared recording: the amber note
];

type Counts = Record<string, number>;   // axe rule id → failing elements
const baseline: Record<string, Counts> = existsSync(BASELINE) ? JSON.parse(readFileSync(BASELINE, 'utf-8')) : {};
const updated: Record<string, Counts> = { ...baseline };

test.describe.configure({ mode: 'serial' });

for (const path of PAGES) {
  test(`axe: ${path}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    // Freeze animations: the home ticker scrolls items in and out of view, so axe counted 7 or 8.
    await page.addStyleTag({ content: '*, *::before, *::after { animation: none !important; transition: none !important; }' });
    const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
    const now: Counts = Object.fromEntries(violations.map((v) => [v.id, v.nodes.length]));
    if (process.env.A11Y_UPDATE) {
      updated[path] = now;
      return;
    }
    const known = baseline[path] ?? {};
    const worse = Object.entries(now)
      .filter(([id, n]) => n > (known[id] ?? 0))
      .map(([id, n]) => {
        const v = violations.find((x) => x.id === id);
        const where = v?.nodes.map((node) => node.target.join(' ')).join(' | ');
        return `${id}: ${known[id] ?? 0} → ${n} (${v?.help}) at ${where}`;
      });
    expect(worse, `new accessibility problems on ${path}`).toEqual([]);
  });
}

test.afterAll(() => {
  if (process.env.A11Y_UPDATE) writeFileSync(BASELINE, JSON.stringify(updated, null, 2) + '\n');
});
