import { expect, test } from 'vitest';
import {
  applyEvent,
  eventText,
  fromSnapshot,
} from '../../src/frontend/reducer';
import { snapshot } from './fixtures';

test('replayed input is not duplicated in output or history', () => {
  const event = { seq: 1, kind: 'input' as const, line: 'ls' };
  const first = applyEvent(fromSnapshot(snapshot()), event);
  expect(applyEvent(first, event)).toBe(first);
  expect(first.history).toEqual(['ls']);
  expect(first.events).toEqual([event]);
});

test('events update the projection without mutating a snapshot', () => {
  const original = fromSnapshot(snapshot());
  const changed = applyEvent(original, {
    seq: 1,
    kind: 'complete',
    cwd: '/home',
    state: 'ready',
  });
  expect(changed.cwd).toBe('/home');
  expect(original.cwd).toBe('/');
  expect(original.cursor).toBe(0);
});

test('missing events are rejected instead of silently losing output', () => {
  expect(() => applyEvent(fromSnapshot(snapshot()), {
    seq: 2,
    kind: 'output',
    text: 'missing first event',
  })).toThrow('Нарушен порядок');
});

test('snapshot restores history and cursor after refresh', () => {
  const data = snapshot();
  data.events = [{ seq: 1, kind: 'input', line: 'cd /docs' }];
  data.cursor = 1;
  const restored = fromSnapshot(data);
  expect(restored.history).toEqual(['cd /docs']);
  expect(applyEvent(restored, {
    seq: 2,
    kind: 'output',
    text: 'ok',
  }).cursor).toBe(2);
});

test('output formatting preserves echo -n, spaces, and literal HTML', () => {
  expect(eventText({
    seq: 1,
    kind: 'output',
    text: '  <script>literal</script>',
  })).toBe('  <script>literal</script>');
  expect(eventText({
    seq: 2,
    kind: 'input',
    prompt: '/ $',
    line: 'ls',
  })).toBe('/ $ ls\n');
});
