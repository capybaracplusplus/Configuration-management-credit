import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import {
  command,
  launchBackend,
  startupCode,
  startupFixture,
  stopBackend,
} from './helpers';

const SCRIPT = [
  'cp /docs/repeated.txt /docs/copied.txt',
  'chmod 000 /docs/copied.txt',
  'uniq /docs/copied.txt',
  'chmod u=rw /docs/copied.txt',
  'uniq -d /docs/copied.txt',
  'cp -R /tree /copied-tree',
  'ls -l /docs/copied.txt',
].join('\n');

test('copy and chmod affect memory across refresh and preserve the ZIP',
  async ({ page }) => {
    const fixture = await startupFixture(SCRIPT);
    const archive = resolve('.generated/vfs/deep.zip');
    const before = await readFile(archive);
    const backend = await launchBackend(startupCode(fixture.script, archive));
    try {
      await page.goto(backend.url);
      const log = page.getByRole('log');
      await expect(log).toContainText(`${fixture.script}:3:`);
      await expect(log).toContainText('Доступ запрещён');
      await expect(log).toContainText('-rw-------');
      await expect(page.getByRole('textbox')).toBeEnabled();
      const transcript = await log.textContent();
      await page.reload();
      await expect(log).toHaveText(transcript ?? '');
      await command(page, 'uniq -c /docs/copied.txt');
      await expect(log).toContainText('2 alpha');
      await command(page, 'ls /copied-tree/level1/level2/level3');
      await expect(log).toContainText('note.txt');
      await page.screenshot({ path: 'test-results/stage-5.png' });
      expect(await readFile(archive)).toEqual(before);
    } finally {
      await stopBackend(backend.process);
      await fixture.cleanup();
    }
  });
