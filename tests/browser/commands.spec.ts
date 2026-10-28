import { expect, test } from '@playwright/test';
import { resolve } from 'node:path';
import {
  command,
  launchBackend,
  startupCode,
  startupFixture,
  stopBackend,
} from './helpers';

test('navigation uses virtual paths and keeps cwd after refresh',
  async ({ page }) => {
    const fixture = await startupFixture('cd /docs\nls -al\n');
    const archive = resolve('.generated/vfs/deep.zip');
    const backend = await launchBackend(startupCode(fixture.script, archive));
    try {
      await page.goto(backend.url);
      const log = page.getByRole('log');
      await expect(log).toContainText('repeated.txt');
      await expect(log).toContainText('-rw-r--r--');
      await expect(page.locator('.editor-directory')).toHaveText('/docs');
      await command(page, 'cd ../tree/level1/level2/level3');
      await expect(page.locator('.editor-directory'))
        .toHaveText('/tree/level1/level2/level3');
      await page.reload();
      await expect(page.getByRole('textbox')).toBeEnabled();
      await command(page, 'ls');
      await expect(log).toContainText('note.txt');
      await command(page, 'cd -');
      await expect(page.locator('.editor-directory')).toHaveText('/docs');
      await page.screenshot({ path: 'test-results/stage-4.png' });
    } finally {
      await stopBackend(backend.process);
      await fixture.cleanup();
    }
  });

test('text and calendar commands render output and recover from errors',
  async ({ page }) => {
    const fixture = await startupFixture([
      'uniq -c /docs/repeated.txt',
      'uniq /assets/payload.bin',
      'cal 2 2024',
      'cal 13 2024',
      'echo "<script>literal</script>"',
    ].join('\n'));
    const archive = resolve('.generated/vfs/deep.zip');
    const backend = await launchBackend(startupCode(fixture.script, archive));
    try {
      await page.goto(backend.url);
      const log = page.getByRole('log');
      await expect(log).toContainText('2 alpha');
      await expect(log).toContainText('February 2024');
      await expect(log).toContainText('29');
      await expect(log).toContainText(`${fixture.script}:2:`);
      await expect(log).toContainText(`${fixture.script}:4:`);
      await expect(log).toContainText('<script>literal</script>');
      await expect(log.locator('script')).toHaveCount(0);
      await expect(page.getByRole('textbox')).toBeEnabled();
    } finally {
      await stopBackend(backend.process);
      await fixture.cleanup();
    }
  });
