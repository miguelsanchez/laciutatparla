// F4.4 smoke: every route in both languages answers 200, renders its content without console
// errors, and links to its equivalent in the other language; the filters and the map work.
import { test, expect, type Page } from '@playwright/test';
import { PAIRS, PLENO, PLENO_SPEAKER, INTERVENTION, url } from './routes';

/** Console errors and uncaught exceptions, ignoring failed loads of third-party resources. */
function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const where = msg.location()?.url ?? '';
    if (where && !where.startsWith('http://localhost')) return;
    if (/Failed to load resource/.test(msg.text()) && !where.startsWith('http://localhost')) return;
    errors.push(msg.text());
  });
  return errors;
}

for (const [cas, val] of PAIRS) {
  for (const [lang, path, other, otherPath] of [
    ['cas', cas, 'val', val],
    ['val', val, 'cas', cas],
  ] as const) {
    test(`${url(lang, path)} loads and links to ${url(other, otherPath)}`, async ({ page }) => {
      const errors = trackErrors(page);
      const res = await page.goto(url(lang, path));
      expect(res?.status()).toBe(200);
      await expect(page.locator('h1').first()).not.toBeEmpty();
      await expect(page.locator('html')).toHaveAttribute('lang', /.+/);

      // The language switch keeps the equivalent route
      const alternate = page.locator(`link[rel="alternate"][hreflang="${other === 'val' ? 'ca' : 'es'}"]`);
      await expect(alternate).toHaveAttribute('href', new RegExp(`${url(other, otherPath)}$`));
      await expect(page.locator(`header a[href="${url(other, otherPath)}"]`).first()).toBeAttached();
      // valencià is the default language (decision §11.1)
      await expect(page.locator('link[rel="alternate"][hreflang="x-default"]'))
        .toHaveAttribute('href', new RegExp(`${url('val', lang === 'val' ? path : otherPath)}$`));

      await page.waitForLoadState('networkidle');
      expect(errors).toEqual([]);
    });
  }
}

test('the switch to the other language lands on the equivalent page', async ({ page }) => {
  await page.goto(url('cas', 'otras-voces/'));
  await page.locator(`header a[href="${url('val', 'altres-veus/')}"]`).filter({ visible: true }).first().click();
  // the page may add its open tab to the URL (?tab=…)
  await expect(page).toHaveURL(new RegExp(`${url('val', 'altres-veus/')}(\\?.*)?$`));
});

test('a pleno page lists its interventions', async ({ page }) => {
  // An empty pleno page still builds (its data load is wrapped in try/catch): check the content.
  await page.goto(url('cas', `plens/${PLENO.id}/`));
  await expect(page.getByText(PLENO_SPEAKER).first()).toBeVisible();
});

test('an intervention page shows its text in both languages', async ({ page }) => {
  for (const lang of ['cas', 'val'] as const) {
    await page.goto(url(lang, `intervencions/${INTERVENTION.id}/`));
    const first = (lang === 'cas' ? INTERVENTION.text_cas : INTERVENTION.text_val)
      .replace(/\*\*/g, '').split(/[.\n]/)[0].trim().slice(0, 40);
    await expect(page.getByText(first, { exact: false }).first()).toBeVisible();
  }
});

test('the filter bar narrows the interventions', async ({ page }) => {
  await page.goto(url('cas', 'intervencions/'));
  const live = page.locator('[aria-live="polite"]').filter({ hasText: 'intervenciones' });
  const total = Number((await live.textContent())!.trim().split(' ')[0]);
  expect(total).toBeGreaterThan(1);
  await page.getByPlaceholder('Buscar por entidad, persona o palabra clave...').fill(PLENO_SPEAKER);
  await expect.poll(async () => Number((await live.textContent())!.trim().split(' ')[0])).toBeLessThan(total);
  await expect(page.getByText(PLENO_SPEAKER).first()).toBeVisible();
});

test('the map draws its areas', async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto(url('val', 'mapa/'));
  await expect(page.locator('.leaflet-container')).toBeVisible();
  // 19 districts by default (88 barrios in barrio mode)
  await expect.poll(() => page.locator('.leaflet-overlay-pane path').count()).toBeGreaterThanOrEqual(19);
  expect(errors).toEqual([]);
});
