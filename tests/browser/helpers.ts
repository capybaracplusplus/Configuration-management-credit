import { spawn, type ChildProcess } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { Page } from '@playwright/test';

const WAIT_MS = 10_000;
const EMPTY_ZIP = Buffer.from('504b0506' + '00'.repeat(18), 'hex');

/** Start a real backend without opening a second, uncontrolled browser. */
export async function launchBackend(code?: string): Promise<{
  process: ChildProcess;
  url: string;
}> {
  const source = code ?? [
    'from shell_emulator.launcher import launch',
    'from shell_emulator.session import Session',
    'launch(Session(), open_browser=False)',
  ].join('\n');
  const process = spawn('.venv/bin/python', ['-u', '-c', source]);
  const url = await serverAddress(process);
  return { process, url };
}

/** Resolve readiness from the launcher's actual reserved port. */
function serverAddress(process: ChildProcess): Promise<string> {
  return new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => {
      process.kill('SIGTERM');
      reject(new Error(`Backend did not become ready: ${output}`));
    }, WAIT_MS);
    process.stderr?.on('data', (chunk) => { output += String(chunk); });
    process.stdout?.on('data', (chunk) => {
      output += String(chunk);
      const url = output.match(/http:\/\/127\.0\.0\.1:\d+/)?.[0];
      if (url) { clearTimeout(timer); resolve(url); }
    });
    process.once('exit', (status) => {
      clearTimeout(timer);
      reject(new Error(`Backend exited (${status}): ${output}`));
    });
  });
}

/** Submit through the same keyboard path used during the live defense. */
export async function command(page: Page, line: string): Promise<void> {
  const input = page.getByRole('textbox', { name: 'Команда' });
  await input.fill(line);
  await input.press('Enter');
}

/** Reap each process even when a browser assertion fails. */
export async function stopBackend(process: ChildProcess): Promise<void> {
  if (process.exitCode !== null || process.signalCode !== null) return;
  const stopped = once(process, 'exit');
  process.kill('SIGTERM');
  await stopped;
}

/** Create a real script with spaces in its path and a cleanup operation. */
export async function startupFixture(text: string): Promise<{
  directory: string;
  script: string;
  vfs: string;
  cleanup: () => Promise<void>;
}> {
  const directory = await mkdtemp(join(tmpdir(), 'shell startup '));
  const script = join(directory, 'commands with spaces.emu');
  const vfs = join(directory, 'virtual files.zip');
  await writeFile(script, text, 'utf8');
  await writeFile(vfs, EMPTY_ZIP);
  return {
    directory,
    script,
    vfs,
    cleanup: () => rm(directory, { recursive: true, force: true }),
  };
}

/** Load a configured script through the actual configuration adapter. */
export function startupCode(script: string, vfs: string): string {
  return [
    'from shell_emulator.configuration import (',
    '    parse_configuration, load_startup,',
    ')',
    'from shell_emulator.launcher import launch',
    'from shell_emulator.engine import Shell',
    'from shell_emulator.session import Session',
    'from shell_emulator.vfs_zip import load_zip',
    `script = ${JSON.stringify(script)}`,
    `vfs = ${JSON.stringify(vfs)}`,
    'config = parse_configuration([',
    '    "--vfs", vfs, "--startup-script", script,',
    '])',
    'session = Session(',
    '    shell=Shell(vfs=load_zip(config.vfs)),',
    '    configuration={"vfs": vfs, "startup_script": script},',
    '    startup=load_startup(config),',
    ')',
    'launch(session, open_browser=False)',
  ].join('\n');
}
