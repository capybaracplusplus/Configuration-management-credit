import type {
  PendingCommand,
  SessionSnapshot,
  ShellEvent,
  TransportListener,
} from './types';

const INITIAL_RETRY_MS = 500;
const MAX_RETRY_MS = 5_000;
const REQUEST_TIMEOUT_MS = 5_000;
const SOCKET_OPEN_TIMEOUT_MS = 5_000;
const RETRY_FACTOR = 2;
const SERVER_FAILURE_STATUS = 500;
const POLICY_VIOLATION = 1008;

/** An HTTP response can reject a command or leave its outcome uncertain. */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Convert structured HTTP validation errors into readable diagnostics. */
function errorMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const oversized = detail.find((issue) => (
      issue?.type === 'string_too_long' && Array.isArray(issue.loc)
        && issue.loc.at(-1) === 'line'
    ));
    const limit = oversized?.ctx?.max_length;
    if (typeof limit === 'number') {
      return `Команда слишком длинная (максимум ${limit} символов).`;
    }
    return 'Неверные параметры запроса. Проверьте введённую команду.';
  }
  return 'Ошибка сервера. Повторите запрос.';
}

/** Bound HTTP requests, including response bodies, to a fixed deadline. */
async function request<T>(path: string, body?: object): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`/api/${path}`, {
      method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
      cache: 'no-store',
      signal: controller.signal,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new ApiError(errorMessage(error?.detail), response.status);
    }
    return await response.json() as T;
  } finally {
    clearTimeout(timer);
  }
}

/** Own a resumable event socket without occupying an HTTP request slot. */
export class SessionTransport {
  private socket: WebSocket | null = null;
  private sessionId = '';
  private cursor = 0;
  private disposed = false;
  private handshakeActive = false;
  private handshakeDelay = INITIAL_RETRY_MS;
  private reconnectDelay = INITIAL_RETRY_MS;
  private handshakeTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private openingTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private readonly listener: TransportListener) {}

  /** Load a snapshot, then replay anything emitted after its cursor. */
  async connect(): Promise<void> {
    try {
      const snapshot = await request<SessionSnapshot>('session');
      if (this.disposed) return;
      this.sessionId = snapshot.session_id;
      this.cursor = snapshot.cursor;
      this.listener.snapshot(snapshot);
      this.openSocket();
    } catch (error) {
      if (!this.disposed) this.fail(error);
    }
  }

  /** Submit a stable request ID so an uncertain request can be retried. */
  async submit(command: PendingCommand): Promise<void> {
    await request('commands', {
      session_id: this.sessionId,
      request_id: command.requestId,
      line: command.line,
    });
  }

  /** Acknowledge only after the final output has reached the DOM. */
  async acknowledgeClose(cursor: number): Promise<void> {
    this.dispose();
    this.listener.connection('closed');
    await request('session/ack-close', {
      session_id: this.sessionId,
      cursor,
    }).catch(() => undefined);
  }

  /** Release sockets and retry timers when the owning component exits. */
  dispose(): void {
    this.disposed = true;
    this.clearHandshakeRetry();
    this.clearOpeningTimeout();
    if (this.reconnectTimer !== null) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.socket?.close();
    this.socket = null;
  }

  private openSocket(): void {
    if (this.disposed) return;
    const url = new URL('/api/events/ws', window.location.href);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.search = new URLSearchParams({
      session_id: this.sessionId,
      after: String(this.cursor),
    }).toString();
    const socket = new WebSocket(url.href);
    this.socket = socket;
    socket.onopen = () => {
      if (!this.isCurrent(socket)) return;
      this.clearOpeningTimeout();
      void this.start();
    };
    socket.onmessage = (message) => this.receive(socket, message);
    socket.onclose = (event) => this.closed(socket, event);
    socket.onerror = () => {
      if (this.isCurrent(socket)) socket.close();
    };
    this.openingTimer = setTimeout(() => {
      this.openingTimer = null;
      if (this.isCurrent(socket)) socket.close();
    }, SOCKET_OPEN_TIMEOUT_MS);
  }

  private clearOpeningTimeout(): void {
    if (this.openingTimer !== null) clearTimeout(this.openingTimer);
    this.openingTimer = null;
  }

  private isCurrent(socket: WebSocket): boolean {
    return !this.disposed && this.socket === socket;
  }

  private socketReady(socket: WebSocket | null): socket is WebSocket {
    return socket !== null && this.isCurrent(socket)
      && socket.readyState === WebSocket.OPEN;
  }

  private async start(): Promise<void> {
    const socket = this.socket;
    if (!this.socketReady(socket) || this.handshakeActive) return;
    this.handshakeActive = true;
    this.clearHandshakeRetry();
    try {
      await request('session/start', { session_id: this.sessionId });
      if (!this.isCurrent(socket)) return;
      this.handshakeDelay = INITIAL_RETRY_MS;
      this.reconnectDelay = INITIAL_RETRY_MS;
      this.listener.connection('connected');
    } catch (error) {
      if (!this.isCurrent(socket)) return;
      if (error instanceof ApiError && error.status < SERVER_FAILURE_STATUS) {
        this.fail(error);
      } else this.retryHandshake();
    } finally {
      this.handshakeActive = false;
      this.resumeHandshake(socket);
    }
  }

  private resumeHandshake(previous: WebSocket): void {
    if (this.socketReady(this.socket) && this.socket !== previous) {
      void this.start();
    }
  }

  /** Retry an uncertain start response without rerunning the script. */
  private retryHandshake(): void {
    this.listener.connection('disconnected');
    this.clearHandshakeRetry();
    this.handshakeTimer = setTimeout(() => {
      this.handshakeTimer = null;
      if (this.socketReady(this.socket)) void this.start();
    }, this.handshakeDelay);
    this.handshakeDelay = Math.min(
      this.handshakeDelay * RETRY_FACTOR, MAX_RETRY_MS,
    );
  }

  private clearHandshakeRetry(): void {
    if (this.handshakeTimer !== null) clearTimeout(this.handshakeTimer);
    this.handshakeTimer = null;
  }

  private receive(socket: WebSocket, message: MessageEvent<string>): void {
    if (!this.isCurrent(socket)) return;
    try {
      const event = JSON.parse(message.data) as ShellEvent;
      this.listener.event(event);
      this.cursor = Math.max(this.cursor, event.seq);
    } catch (error) {
      this.fail(error);
    }
  }

  private closed(socket: WebSocket, event: CloseEvent): void {
    if (!this.isCurrent(socket)) return;
    this.socket = null;
    this.clearOpeningTimeout();
    this.clearHandshakeRetry();
    if (event.code === POLICY_VIOLATION) {
      const reason = event.reason || 'Сеанс недоступен.';
      this.fail(new Error(`${reason} Обновите страницу.`));
      return;
    }
    this.listener.connection('disconnected');
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket();
    }, this.reconnectDelay);
    this.reconnectDelay = Math.min(
      this.reconnectDelay * RETRY_FACTOR, MAX_RETRY_MS,
    );
  }

  private fail(error: unknown): void {
    this.dispose();
    this.listener.connection('failed');
    const knownError = error instanceof Error && !(error instanceof TypeError)
      && error.name !== 'AbortError';
    this.listener.failure(knownError ? error.message
      : 'Не удалось подключиться к эмулятору. Обновите страницу.');
  }
}
