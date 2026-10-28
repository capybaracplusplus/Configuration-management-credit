import { afterEach, expect, test, vi } from 'vitest';
import {
  ApiError,
  SessionTransport,
} from '../../src/frontend/transport';
import { snapshot } from './fixtures';

/** A deterministic WebSocket stand-in for lifecycle and replay tests. */
class Socket {
  static readonly OPEN = 1;
  static latest: Socket;
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  close = vi.fn(() => this.end(1000));

  constructor(readonly url: string) {
    Socket.latest = this;
  }

  open(): void {
    this.readyState = Socket.OPEN;
    this.onopen?.();
  }

  end(code = 1006, reason = ''): void {
    this.readyState = 3;
    this.onclose?.(new CloseEvent('close', { code, reason }));
  }

  event(seq: number): void {
    const data = JSON.stringify({ seq, kind: 'output', text: 'hello' });
    this.onmessage?.(new MessageEvent('message', { data }));
  }
}

/** Provide a connected transport and captured HTTP requests. */
async function connect() {
  const fetcher = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => snapshot(),
  });
  vi.stubGlobal('fetch', fetcher);
  vi.stubGlobal('WebSocket', Socket);
  const listener = {
    snapshot: vi.fn(),
    event: vi.fn(),
    connection: vi.fn(),
    failure: vi.fn(),
  };
  const transport = new SessionTransport(listener);
  await transport.connect();
  return { transport, listener, fetcher };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test('snapshot starts a socket at the matching cursor', async () => {
  const { listener } = await connect();
  expect(listener.snapshot).toHaveBeenCalledWith(snapshot());
  expect(Socket.latest.url).toContain('/api/events/ws?');
  expect(Socket.latest.url).toContain('after=0');
  expect(Socket.latest.url).toContain('session_id=test-session');
  Socket.latest.open();
  await vi.waitFor(() => {
    expect(listener.connection).toHaveBeenCalledWith('connected');
  });
});

test('retry reuses the same command request ID', async () => {
  const { transport, fetcher } = await connect();
  const command = { requestId: 'stable-id', line: 'ls' };
  fetcher.mockRejectedValueOnce(new TypeError('Network failure'));
  await expect(transport.submit(command)).rejects.toThrow('Network');
  await transport.submit(command);
  const first = fetcher.mock.calls[1][1].body;
  const retry = fetcher.mock.calls[2][1].body;
  expect(first).toBe(retry);
  expect(JSON.parse(retry).request_id).toBe('stable-id');
});

test('HTTP errors preserve their status and diagnostic', async () => {
  const { transport, fetcher } = await connect();
  fetcher.mockResolvedValueOnce({
    ok: false,
    status: 409,
    json: async () => ({ detail: 'Сеанс изменился' }),
  });
  await expect(transport.submit({
    requestId: 'id', line: 'ls',
  })).rejects.toEqual(new ApiError('Сеанс изменился', 409));
});

test('oversized commands receive a clear untruncated validation error',
  async () => {
    const { transport, fetcher } = await connect();
    fetcher.mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({ detail: [{
        type: 'string_too_long', loc: ['body', 'line'],
        ctx: { max_length: 65_536 },
      }] }),
    });
    await expect(transport.submit({
      requestId: 'id', line: 'x'.repeat(65_537),
    })).rejects.toEqual(new ApiError(
      'Команда слишком длинная (максимум 65536 символов).', 422,
    ));
    const [, options] = fetcher.mock.calls.at(-1)!;
    expect(JSON.parse(options.body).line).toHaveLength(65_537);
  },
);

test('HTTP deadlines abort requests and clear their timer', async () => {
  vi.useFakeTimers();
  const { transport, fetcher } = await connect();
  Socket.latest.open();
  await vi.advanceTimersByTimeAsync(0);
  fetcher.mockImplementationOnce((_url, options) => new Promise((_, reject) => {
    options.signal.addEventListener('abort', () => {
      reject(new DOMException('Deadline exceeded', 'AbortError'));
    });
  }));
  const submitted = transport.submit({ requestId: 'timeout', line: 'ls' });
  const rejected = expect(submitted).rejects.toMatchObject({
    name: 'AbortError',
  });
  await vi.advanceTimersByTimeAsync(5_000);
  await rejected;
  expect(fetcher.mock.calls.at(-1)![1].signal.aborted).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
});

test('a stalled socket opening is closed and retried', async () => {
  vi.useFakeTimers();
  const { transport, listener } = await connect();
  const stalled = Socket.latest;
  await vi.advanceTimersByTimeAsync(5_000);
  expect(stalled.close).toHaveBeenCalledOnce();
  expect(listener.connection).toHaveBeenLastCalledWith('disconnected');
  await vi.advanceTimersByTimeAsync(500);
  expect(Socket.latest).not.toBe(stalled);
  transport.dispose();
  expect(vi.getTimerCount()).toBe(0);
});

test('snapshot deadlines provide a Russian recovery instruction', async () => {
  vi.useFakeTimers();
  const { transport, listener, fetcher } = await connect();
  transport.dispose();
  fetcher.mockImplementationOnce((_url, options) => new Promise((_, reject) => {
    options.signal.addEventListener('abort', () => {
      reject(new DOMException('Aborted', 'AbortError'));
    });
  }));
  const fresh = new SessionTransport(listener);
  const loading = fresh.connect();
  await vi.advanceTimersByTimeAsync(5_000);
  await loading;
  expect(listener.connection).toHaveBeenLastCalledWith('failed');
  expect(listener.failure).toHaveBeenLastCalledWith(
    'Не удалось подключиться к эмулятору. Обновите страницу.',
  );
});

test('close acknowledgment includes the final rendered cursor', async () => {
  const { transport, listener, fetcher } = await connect();
  const socket = Socket.latest;
  await transport.acknowledgeClose(12);
  socket.end();
  expect(socket.close).toHaveBeenCalledOnce();
  expect(listener.connection).toHaveBeenLastCalledWith('closed');
  const [path, options] = fetcher.mock.calls.at(-1)!;
  expect(path).toBe('/api/session/ack-close');
  expect(JSON.parse(options.body)).toEqual({
    session_id: 'test-session', cursor: 12,
  });
});

test('policy rejection refuses the session with a refresh instruction',
  async () => {
    const { listener } = await connect();
    Socket.latest.end(1008, 'Сеанс изменился.');
    expect(listener.connection).toHaveBeenLastCalledWith('failed');
    expect(listener.failure).toHaveBeenCalledWith(
      'Сеанс изменился. Обновите страницу.',
    );
  },
);

test('socket reconnection resumes from the last applied event', async () => {
  vi.useFakeTimers();
  const { transport, listener } = await connect();
  const oldSocket = Socket.latest;
  oldSocket.event(1);
  oldSocket.event(2);
  oldSocket.event(1);
  oldSocket.end();
  await vi.advanceTimersByTimeAsync(500);
  expect(Socket.latest).not.toBe(oldSocket);
  expect(Socket.latest.url).toContain('after=2');
  oldSocket.event(3);
  oldSocket.end(1008, 'stale close');
  expect(listener.event).toHaveBeenCalledTimes(3);
  expect(listener.failure).not.toHaveBeenCalled();
  Socket.latest.event(3);
  expect(listener.event).toHaveBeenCalledTimes(4);
  transport.dispose();
});

test('rejected events stop the socket instead of losing output', async () => {
  const { listener } = await connect();
  listener.event.mockImplementationOnce(() => {
    throw new Error('Нарушен порядок событий.');
  });
  Socket.latest.event(3);
  expect(listener.connection).toHaveBeenLastCalledWith('failed');
  expect(Socket.latest.close).toHaveBeenCalledOnce();
});

test('a transient handshake failure retries the same session', async () => {
  vi.useFakeTimers();
  const { transport, listener, fetcher } = await connect();
  fetcher.mockRejectedValueOnce(new TypeError('Lost handshake response'));
  Socket.latest.open();
  await vi.advanceTimersByTimeAsync(0);
  expect(listener.connection).toHaveBeenLastCalledWith('disconnected');
  await vi.advanceTimersByTimeAsync(499);
  expect(fetcher).toHaveBeenCalledTimes(2);
  await vi.advanceTimersByTimeAsync(1);
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(fetcher.mock.calls[1][1].body).toBe(fetcher.mock.calls[2][1].body);
  expect(listener.connection).toHaveBeenLastCalledWith('connected');
  transport.dispose();
});

test('handshake retries back off and stop when disposed', async () => {
  vi.useFakeTimers();
  const { transport, fetcher } = await connect();
  fetcher.mockRejectedValue(new TypeError('Offline'));
  Socket.latest.open();
  await vi.advanceTimersByTimeAsync(0);
  await vi.advanceTimersByTimeAsync(500);
  expect(fetcher).toHaveBeenCalledTimes(3);
  await vi.advanceTimersByTimeAsync(999);
  expect(fetcher).toHaveBeenCalledTimes(3);
  await vi.advanceTimersByTimeAsync(1);
  expect(fetcher).toHaveBeenCalledTimes(4);
  transport.dispose();
  await vi.advanceTimersByTimeAsync(10_000);
  expect(fetcher).toHaveBeenCalledTimes(4);
});

test('in-flight handshakes cannot reactivate disposed transports', async () => {
  const { transport, listener, fetcher } = await connect();
  let finishStart: (value: unknown) => void = () => undefined;
  fetcher.mockReturnValueOnce(new Promise((resolve) => {
    finishStart = resolve;
  }));
  Socket.latest.open();
  Socket.latest.open();
  expect(fetcher).toHaveBeenCalledTimes(2);
  transport.dispose();
  finishStart({ ok: true, json: async () => ({ state: 'ready' }) });
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(listener.connection).not.toHaveBeenCalledWith('connected');
});

test('a new socket starts after an older handshake settles', async () => {
  vi.useFakeTimers();
  const { transport, listener, fetcher } = await connect();
  let finishStart: (value: unknown) => void = () => undefined;
  fetcher.mockReturnValueOnce(new Promise((resolve) => {
    finishStart = resolve;
  }));
  Socket.latest.open();
  Socket.latest.end();
  await vi.advanceTimersByTimeAsync(500);
  Socket.latest.open();
  expect(fetcher).toHaveBeenCalledTimes(2);
  finishStart({ ok: true, json: async () => ({ state: 'ready' }) });
  await vi.advanceTimersByTimeAsync(0);
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(listener.connection).toHaveBeenLastCalledWith('connected');
  transport.dispose();
});
