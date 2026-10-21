/**
 * The one place the build reads the project's data from (arquitectura-agentes.md F4.1).
 *
 * Pages and utils read JSON through readData() instead of building paths to ../data themselves,
 * so a build can run on another data directory: LCP_DATA_DIR=tests/fixtures/data npm run build
 * builds the site on the small test fixture. Without it, the repo's data/ is used.
 *
 * Each call returns a fresh parse: some pages sort or annotate what they read, and sharing one
 * object between pages would change what others see. Only the file text is cached.
 */
import { readFileSync, readdirSync } from 'fs';
import { resolve } from 'path';

export const DATA_DIR = process.env.LCP_DATA_DIR
  ? resolve(process.env.LCP_DATA_DIR)
  : resolve(process.cwd(), '..', 'data');

const texts = new Map<string, string>();

/** Parse a JSON file under the data directory, e.g. readData('plenos/2026-03-31.json'). */
export function readData<T = any>(name: string): T {
  let text = texts.get(name);
  if (text === undefined) {
    text = readFileSync(resolve(DATA_DIR, name), 'utf-8');
    texts.set(name, text);
  }
  return JSON.parse(text) as T;
}

/** File names in a folder of the data directory, e.g. listData('plenos'). */
export function listData(dir: string): string[] {
  return readdirSync(resolve(DATA_DIR, dir));
}
