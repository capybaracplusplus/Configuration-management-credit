import { expect, test } from '@playwright/test';
import { once } from 'node:events';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import {
  launchBackend,
  startupCode,
  startupFixture,
  stopBackend,
} from './helpers';

test('ZIP loads into the GUI and survives refresh without changing source',
  async ({ page }) => {
    const fixture = await startupFixture('# Loading only\n');
    const archive = resolve('.generated/vfs/deep.zip');
    const before = await readFile(archive);
    const backend = await launchBackend(startupCode(fixture.script, archive));
    try {
      await page.goto(backend.url);
      const log = page.getByRole('log');
      await expect(log).toContainText('VFS загружена в память:');
      await expect(log).toContainText('Корень VFS:');
      await expect(log).toContainText('assets');
      await expect(log).toContainText('tree');
      await expect(page.getByRole('textbox')).toBeEnabled();
      const transcript = await log.textContent();
      await page.reload();
      await expect(page.getByRole('textbox')).toBeEnabled();
      await expect(log).toHaveText(transcript ?? '');
      await page.screenshot({ path: 'test-results/stage-3.png' });
      expect(await readFile(archive)).toEqual(before);
    } finally {
      await stopBackend(backend.process);
      await fixture.cleanup();
    }
  });

for (const variant of ['minimal', 'multiple', 'deep']) {
  test(`VFS smoke script renders ${variant} and exits`, async ({ page }) => {
    const archive = resolve(`.generated/vfs/${variant}.zip`);
    const script = resolve('demos/vfs-smoke.emu');
    const backend = await launchBackend(startupCode(script, archive));
    try {
      const stopped = once(backend.process, 'exit');
      await page.goto(backend.url);
      const log = page.getByRole('log');
      await expect(log).toContainText('ls -al /');
      await expect(log).toContainText('Путь не существует: /missing');
      await expect(page.getByRole('textbox')).toBeDisabled();
      expect((await stopped)[0]).toBe(0);
      await expect(log).toContainText('exit');
      const root = variant === 'minimal' ? 'Корень VFS: пусто' : 'docs';
      await expect(log).toContainText(root);
    } finally {
      await stopBackend(backend.process);
    }
  });
}
