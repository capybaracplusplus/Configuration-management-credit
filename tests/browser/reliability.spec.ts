import { expect, test } from '@playwright/test';
import { command, launchBackend, stopBackend } from './helpers';

const OPEN_TABS = 8;
const REQUEST_RECOVERY_MS = 8_000;

test('eight tabs remain interactive on the same local server',
  async ({ context }) => {
    const backend = await launchBackend();
    const pages = [];
    try {
      for (let index = 0; index < OPEN_TABS; index++) {
        const page = await context.newPage();
        pages.push(page);
        await page.goto(backend.url);
        await expect(page.getByRole('textbox')).toBeEnabled();
      }
      await command(pages[0], 'echo tabs-alive');
      for (const page of pages) {
        await expect(page.getByRole('log')).toContainText('tabs-alive');
        await expect(page.getByRole('textbox')).toBeEnabled();
      }
      await command(pages.at(-1)!, 'echo last-tab-alive');
      await expect(pages[0].getByRole('log'))
        .toContainText('last-tab-alive');
    } finally {
      await Promise.all(pages.map((page) => page.close()));
      await stopBackend(backend.process);
    }
  });

test('accepted commands unlock input before a delayed HTTP response',
  async ({ page }) => {
    const backend = await launchBackend();
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => { release = resolve; });
    let first = true;
    await page.route('**/api/commands', async (route) => {
      if (!first) return route.continue();
      first = false;
      const response = await route.fetch();
      await held;
      await route.fulfill({ response });
    });
    try {
      await page.goto(backend.url);
      await command(page, 'echo first-accepted');
      await expect(page.getByRole('log')).toContainText('first-accepted');
      await expect(page.getByRole('textbox')).toBeEnabled();
      await command(page, 'echo second-accepted');
      await expect(page.getByRole('log')).toContainText('second-accepted');
      release();
      await expect(page.getByRole('textbox')).toBeEnabled();
      await expect(page.getByRole('alert')).toHaveCount(0);
    } finally {
      release();
      await page.unrouteAll({ behavior: 'wait' });
      await stopBackend(backend.process);
    }
  });

test('a request deadline exposes a retry that executes only once',
  async ({ page }) => {
    const backend = await launchBackend();
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => { release = resolve; });
    let first = true;
    await page.route('**/api/commands', async (route) => {
      if (!first) return route.continue();
      first = false;
      await held;
      await route.abort();
    });
    try {
      await page.goto(backend.url);
      await command(page, 'echo retry-after-deadline');
      const retry = page.getByRole('button', { name: 'Повторить отправку' });
      await expect(retry).toBeEnabled({ timeout: REQUEST_RECOVERY_MS });
      release();
      await retry.click();
      await expect(page.getByRole('textbox')).toBeEnabled();
      const result = await page.request.get(`${backend.url}/api/session`);
      const snapshot = await result.json();
      const lines = snapshot.events.filter((event: { kind: string }) => (
        event.kind === 'input'
      ));
      expect(lines).toHaveLength(1);
      expect(lines[0].line).toBe('echo retry-after-deadline');
    } finally {
      release();
      await page.unrouteAll({ behavior: 'wait' });
      await stopBackend(backend.process);
    }
  });
