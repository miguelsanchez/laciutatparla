// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import preact from '@astrojs/preact';
import sitemap from '@astrojs/sitemap';

// https://astro.build/config
export default defineConfig({
  site: 'https://laciutatparla.es',
  vite: {
    plugins: [tailwindcss()],
    server: {
      allowedHosts: ['laciutatparla.ngrok.app', 'logically-foresighted-kiera.ngrok-free.dev'],
    },
  },
  integrations: [preact(), sitemap()],
  redirects: {
    '/': '/val/',
  },
  i18n: {
    defaultLocale: "val",
    locales: ["cas", "val"],
    routing: {
      prefixDefaultLocale: true,
    },
  },
});
