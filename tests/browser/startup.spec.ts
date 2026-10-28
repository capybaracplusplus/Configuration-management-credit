import { expect, test } from '@playwright/test';
import { once } from 'node:events';
import {
  launchBackend,
  startupCode,
  startupFixture,
  stopBackend,
} from './helpers';

test('startup dialogue, source errors, spaced paths, and refresh',
  async ({ page }) => {
    const fixture = await startupFixture([
      '# Комментарий не выполняется',
      'ls "$HOME"',
      'unknown_startup',
      'ls after-error # Продолжить после ошибки',
    ].join('\n'));
    const backend = await launchBackend(
      startupCode(fixture.script, fixture.vfs),
    );
    try {
      await page.goto(backend.url);
      const log = page.getByRole('log');
      await expect(log).toContainText('ls "$HOME"');
      await expect(log).toContainText(`${fixture.script}:3`);
      await expect(log).toContainText('Неизвестная команда: unknown_startup');
      await expect(log).toContainText('ls after-error');
      await expect(page.getByText(fixture.script, { exact: true }))
        .toBeVisible();
      await expect(page.getByText(fixture.vfs, { exact: true })).toBeVisible();
      await expect(page.getByRole('textbox')).toBeEnabled();
      const transcript = await log.textContent();
      await page.reload();
      await expect(page.getByRole('textbox')).toBeEnabled();
      await expect(log).toHaveText(transcript ?? '');
      await page.screenshot({ path: 'test-results/stage-2.png' });
    } finally {
      await stopBackend(backend.process);
      await fixture.cleanup();
    }
  });

test('script exit renders its final state and terminates the process',
  async ({ page }) => {
    const fixture = await startupFixture('ls\nexit\nunknown_after_exit\n');
    const backend = await launchBackend(
      startupCode(fixture.script, fixture.vfs),
    );
    try {
      const stopped = once(backend.process, 'exit');
      await page.goto(backend.url);
      const log = page.getByRole('log');
      await expect(log).toContainText('exit');
      await expect(page.getByText('Сеанс завершён.', {
        exact: false,
      })).toBeVisible();
      await expect(log).not.toContainText('unknown_after_exit');
      await expect(page.getByRole('textbox')).toBeDisabled();
      expect((await stopped)[0]).toBe(0);
      await expect(log).toContainText('exit');
    } finally {
      await stopBackend(backend.process);
      await fixture.cleanup();
    }
  });
