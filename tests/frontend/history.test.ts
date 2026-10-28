import { expect, test } from 'vitest';
import { HistoryCursor } from '../../src/frontend/history';

test('history navigation restores an unfinished command', () => {
  const cursor = new HistoryCursor();
  const history = ['ls', 'cd /docs'];
  expect(cursor.move(-1, 'echo draft', history)).toBe('cd /docs');
  expect(cursor.move(-1, 'cd /docs', history)).toBe('ls');
  expect(cursor.move(-1, 'ls', history)).toBe('ls');
  expect(cursor.move(1, 'ls', history)).toBe('cd /docs');
  expect(cursor.move(1, 'cd /docs', history)).toBe('echo draft');
});

test('empty history and down from a fresh draft leave text intact', () => {
  const cursor = new HistoryCursor();
  expect(cursor.move(-1, 'draft', [])).toBe('draft');
  expect(cursor.move(1, 'draft', ['ls'])).toBe('draft');
});

test('editing a historical command starts a new draft cycle', () => {
  const cursor = new HistoryCursor();
  cursor.move(-1, 'old draft', ['ls']);
  cursor.reset();
  expect(cursor.move(-1, 'ls -l', ['ls'])).toBe('ls');
  expect(cursor.move(1, 'ls', ['ls'])).toBe('ls -l');
});
