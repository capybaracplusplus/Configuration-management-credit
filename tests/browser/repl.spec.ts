import { expect, test } from '@playwright/test';
import { hostname, userInfo } from 'node:os';
import { once } from 'node:events';
import { command, launchBackend, stopBackend } from './helpers';

const COMMAND_LIMIT = 65_536;

test('interactive REPL, errors, refresh, history, and process exit',
  async ({ page }) => {
    const backend = await launchBackend();
    try {
      await page.goto(backend.url);
      const identity = `${userInfo().username}@${hostname()}`;
      await expect(page).toHaveTitle(`Эмулятор - [${identity}]`);
      const log = page.getByRole('log');
      await command(page, 'echo "$HOME"');
      await expect(log).toContainText(process.env.HOME ?? '');
      await command(page, 'unknown');
      await expect(log).toContainText('Неизвестная команда: unknown');
      await command(page, 'cd one two');
      await expect(log).toContainText('не более одного пути');
      const previous = await log.textContent();
      await page.reload();
      await expect(log).toHaveText(previous ?? '');
      const input = page.getByRole('textbox', { name: 'Команда' });
      await expect(input).toBeEnabled();
      await input.press('ArrowUp');
      await expect(input).toHaveValue('cd one two');
      await page.screenshot({ path: 'test-results/repl.png' });
      const stopped = once(backend.process, 'exit');
      await command(page, 'exit');
      await expect(page.getByText('Сеанс завершён.', {
        exact: false,
      })).toBeVisible();
      await expect(input).toBeDisabled();
      expect((await stopped)[0]).toBe(0);
    } finally {
      await stopBackend(backend.process);
    }
  });

test('oversized input has a useful error and does not block later commands',
  async ({ page }) => {
    const backend = await launchBackend();
    try {
      await page.goto(backend.url);
      await command(page, 'echo ' + 'x'.repeat(COMMAND_LIMIT));
      await expect(page.getByRole('alert')).toContainText('65536');
      await expect(page.getByRole('alert')).not.toContainText('[object');
      await expect(page.getByRole('textbox')).toBeEnabled();
      await command(page, 'echo recovered');
      await expect(page.getByRole('log')).toContainText('recovered');
    } finally {
      await stopBackend(backend.process);
    }
  });
