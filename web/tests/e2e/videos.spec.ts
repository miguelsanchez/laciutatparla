// Plan 3.11: the video block of a pleno page in its four states, in both languages, on the fixture.
//   split (2022-03-31) · live player (2022-11-17) · shared recording (2023-10-24 + 2023-10-24-1)
//   · single recording (2022-10-21, unchanged)
import { test, expect } from '@playwright/test';
import { plenos, url } from './routes';

const T = {
  cas: { single: 'Ver vídeo', title: 'Vídeo de la sesión', n: '2 partes', unavailable: 'Vídeo no disponible en el archivo municipal',
         note: 'dividida en 2 vídeos', shared: 'El archivo municipal publica un solo vídeo para este día', part: (i: number) => `Parte ${i}`, de: 'de 2' },
  val: { single: 'Veure vídeo', title: 'Vídeo de la sessió', n: '2 parts', unavailable: "Vídeo no disponible a l'arxiu municipal",
         note: 'partida en 2 vídeos', shared: 'L\'arxiu municipal publica un sol vídeo per a este dia', part: (i: number) => `Part ${i}`, de: 'de 2' },
} as const;
const LANGS = ['cas', 'val'] as const;
const pleno = (id: string) => plenos.find((p) => p.id === id)!;

for (const lang of LANGS) {
  const t = T[lang];

  test(`[${lang}] split pleno: part links in data order, no single button`, async ({ page }) => {
    const p = pleno('2022-03-31');
    expect(p.url_videos.length).toBe(2);
    await page.goto(url(lang, 'plens/2022-03-31/'));
    const block = page.locator('section[aria-labelledby="video-parts-h"]');
    await expect(block.locator('h2')).toContainText(t.title);
    await expect(block.locator('h2')).toContainText(t.n);
    const links = block.locator('ol li a');
    await expect(links).toHaveCount(2);
    for (let i = 0; i < 2; i++) {
      await expect(links.nth(i)).toHaveAttribute('href', p.url_videos[i]);
      await expect(links.nth(i)).toContainText(`${t.part(i + 1)} ${t.de}`);
      await expect(links.nth(i)).toHaveAttribute('target', '_blank');
      await expect(links.nth(i)).toHaveAttribute('rel', /noopener/);
    }
    await expect(block).toContainText(t.note);
    await expect(page.getByRole('link', { name: t.single })).toHaveCount(0);
    await expect(page.getByText(t.unavailable)).toHaveCount(0);
    // the interventions below still render (4 in the fixture)
    expect(await page.locator('h3').count()).toBeGreaterThanOrEqual(4);
  });

  test(`[${lang}] live-player pleno: grey line instead of the button`, async ({ page }) => {
    expect(pleno('2022-11-17').url_video).toContain('/live/');
    await page.goto(url(lang, 'plens/2022-11-17/'));
    await expect(page.getByText(t.unavailable)).toBeVisible();
    await expect(page.getByRole('link', { name: t.single })).toHaveCount(0);
    await expect(page.locator('a[href*="/live/"]')).toHaveCount(0);
    await expect(page.locator('section[aria-labelledby="video-parts-h"]')).toHaveCount(0);
    await expect(page.getByText(t.shared)).toHaveCount(0);
  });

  test(`[${lang}] shared recording: button kept, note links the sibling`, async ({ page }) => {
    for (const [id, sibling] of [['2023-10-24', '2023-10-24-1'], ['2023-10-24-1', '2023-10-24']] as const) {
      await page.goto(url(lang, `plens/${id}/`));
      await expect(page.getByRole('link', { name: t.single })).toHaveAttribute('href', pleno(id).url_video);
      const note = page.getByText(t.shared);
      await expect(note).toBeVisible();
      const link = note.locator('a');
      await expect(link).toHaveCount(1);
      await expect(link).toHaveAttribute('href', url(lang, `plens/${sibling}/`));
      await expect(page.locator('section[aria-labelledby="video-parts-h"]')).toHaveCount(0);
      await link.click();
      await expect(page).toHaveURL(new RegExp(`/plens/${sibling}/$`));
    }
  });

  test(`[${lang}] single recording: button only, no note`, async ({ page }) => {
    const p = pleno('2022-10-21');
    expect(p.url_videos).toEqual([]);
    await page.goto(url(lang, 'plens/2022-10-21/'));
    await expect(page.getByRole('link', { name: t.single })).toHaveAttribute('href', p.url_video);
    await expect(page.locator('section[aria-labelledby="video-parts-h"]')).toHaveCount(0);
    await expect(page.getByText(t.unavailable)).toHaveCount(0);
    await expect(page.getByText(t.shared)).toHaveCount(0);
  });
}

test('375 px: split pleno has no horizontal scroll and part links are at least 32 px tall', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto(url('val', 'plens/2022-03-31/'));
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const links = page.locator('section[aria-labelledby="video-parts-h"] ol li a');
  for (let i = 0; i < (await links.count()); i++) {
    expect((await links.nth(i).boundingBox())!.height).toBeGreaterThanOrEqual(32);
  }
});
