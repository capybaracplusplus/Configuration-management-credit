import { render } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import Transcript from '../../src/frontend/Transcript.svelte';

test('terminal output escapes markup and preserves missing newlines', () => {
  const view = render(Transcript, {
    props: {
      events: [
        { seq: 1, kind: 'output', text: '<b>literal</b>' },
        { seq: 2, kind: 'output', text: ' continued\n' },
      ],
    },
  });
  const log = view.getByRole('log');
  expect(log.textContent).toBe('<b>literal</b> continued\n');
  expect(log.querySelector('b')).toBeNull();
});
