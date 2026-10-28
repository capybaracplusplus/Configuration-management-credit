import type { SessionSnapshot } from '../../src/frontend/types';

/** A complete snapshot fixture with deterministic identity and cursor. */
export function snapshot(): SessionSnapshot {
  return {
    session_id: 'test-session',
    username: 'student',
    hostname: 'localhost',
    title: 'Эмулятор - [student@localhost]',
    cwd: '/',
    state: 'ready',
    configuration: { vfs: null, startup_script: null },
    events: [],
    cursor: 0,
  };
}
