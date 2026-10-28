import { fileURLToPath } from 'node:url';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

const frontend = fileURLToPath(
  new URL('./src/frontend', import.meta.url),
);

export default defineConfig({
  root: frontend,
  plugins: [svelte({
    configFile: fileURLToPath(new URL('./svelte.config.js', import.meta.url)),
  })],
  resolve: { conditions: ['browser'] },
  build: { outDir: '../../dist', emptyOutDir: true },
  test: {
    root: fileURLToPath(new URL('.', import.meta.url)),
    include: ['tests/frontend/**/*.test.ts'],
    environment: 'jsdom',
    setupFiles: ['tests/frontend/setup.ts'],
    clearMocks: true,
  },
});
