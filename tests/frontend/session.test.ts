import { beforeEach, expect, test, vi } from 'vitest';
import { SessionModel } from '../../src/frontend/session.svelte';
import { ApiError } from '../../src/frontend/transport';
import type { TransportListener } from '../../src/frontend/types';
import { snapshot } from './fixtures';

const network = vi.hoisted(() => ({
  submit: vi.fn(),
  listener: null as TransportListener | null,
}));

vi.mock('../../src/frontend/transport', async (importOriginal) => {
  const original = await importOriginal<object>();
  return {
    ...original,
    SessionTransport: class {
      submit = network.submit;
      constructor(listener: TransportListener) {
        network.listener = listener;
      }
    },
  };
});

beforeEach(() => network.submit.mockReset());

test('an uncertain request retains its ID and locks its draft', async () => {
  const model = new SessionModel();
  network.listener?.snapshot(snapshot());
  model.draft = 'ls';
  network.submit.mockRejectedValueOnce(new TypeError('Lost response'));
  await model.submit();
  expect(model.uncertain).toBe(true);
  expect(model.draft).toBe('ls');
  await model.submit();
  expect(network.submit.mock.calls[0][0]).toEqual(
    network.submit.mock.calls[1][0],
  );
  expect(model.uncertain).toBe(false);
  expect(model.draft).toBe('');
});

test('a replayed input confirms a command whose HTTP response was lost',
  async () => {
    const model = new SessionModel();
    network.listener?.snapshot(snapshot());
    model.draft = 'ls';
    network.submit.mockRejectedValueOnce(new TypeError('Lost response'));
    await model.submit();
    const command = network.submit.mock.calls[0][0];
    network.listener?.event({
      seq: 1,
      kind: 'input',
      command_id: command.requestId,
      line: command.line,
    });
    expect(model.uncertain).toBe(false);
    expect(model.draft).toBe('');
    expect(model.view?.history).toEqual(['ls']);
  },
);

test('server failures retain an uncertain request ID for safe retry',
  async () => {
    const model = new SessionModel();
    network.listener?.snapshot(snapshot());
    model.draft = 'cp source destination';
    network.submit.mockRejectedValueOnce(new ApiError('Недоступно', 503));
    await model.submit();
    expect(model.uncertain).toBe(true);
    await model.submit();
    expect(network.submit.mock.calls[0][0]).toEqual(
      network.submit.mock.calls[1][0],
    );
  },
);

test.each(['success', 'failure'])(
  'accepted input unlocks the editor before late HTTP %s', async (outcome) => {
    const model = new SessionModel();
    network.listener?.snapshot(snapshot());
    let settleFirst: (value?: void) => void = () => undefined;
    const firstResponse = new Promise<void>((resolve, reject) => {
      settleFirst = outcome === 'success' ? resolve : reject;
    });
    let settleSecond: () => void = () => undefined;
    const secondResponse = new Promise<void>((resolve) => {
      settleSecond = resolve;
    });
    network.submit.mockReturnValueOnce(firstResponse)
      .mockReturnValueOnce(secondResponse);
    model.draft = 'echo first';
    const first = model.submit();
    const request = network.submit.mock.calls[0][0];
    network.listener?.event({
      seq: 1, kind: 'input', command_id: request.requestId, line: request.line,
    });
    expect(model.sending).toBe(false);
    model.draft = 'echo second';
    const second = model.submit();
    settleFirst();
    await first;
    expect(model.sending).toBe(true);
    expect(model.draft).toBe('echo second');
    expect(model.uncertain).toBe(false);
    settleSecond();
    await second;
    expect(model.sending).toBe(false);
  },
);
