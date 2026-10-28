import { fireEvent, render } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import CommandEditor from '../../src/frontend/CommandEditor.svelte';

test('arrow keys recover the draft and Enter submits once', async () => {
  const submit = vi.fn();
  const view = render(CommandEditor, {
    draft: 'unfinished',
    disabled: false,
    history: ['ls'],
    cwd: '/',
    onsubmit: submit,
  });
  const input = view.getByLabelText('Команда') as HTMLInputElement;
  await fireEvent.keyDown(input, { key: 'ArrowUp' });
  expect(input.value).toBe('ls');
  await fireEvent.keyDown(input, { key: 'ArrowDown' });
  expect(input.value).toBe('unfinished');
  await fireEvent.keyDown(input, { key: 'Enter' });
  expect(submit).toHaveBeenCalledOnce();
});

test('IME composition does not accidentally execute a command', async () => {
  const submit = vi.fn();
  const view = render(CommandEditor, {
    draft: 'текст',
    disabled: false,
    history: [],
    cwd: '/',
    onsubmit: submit,
  });
  await fireEvent.keyDown(view.getByLabelText('Команда'), {
    key: 'Enter',
    isComposing: true,
  });
  expect(submit).not.toHaveBeenCalled();
});

test('execution control is disabled while the session is unavailable', () => {
  const view = render(CommandEditor, {
    draft: 'ls',
    disabled: true,
    history: [],
    cwd: '/',
    onsubmit: vi.fn(),
  });
  const input = view.getByLabelText('Команда') as HTMLInputElement;
  const button = view.getByRole('button') as HTMLButtonElement;
  expect(input.disabled).toBe(true);
  expect(button.disabled).toBe(true);
});
