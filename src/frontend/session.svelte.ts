import { applyEvent, fromSnapshot } from './reducer';
import { ApiError, SessionTransport } from './transport';
import type {
  ConnectionState,
  PendingCommand,
  SessionSnapshot,
  SessionView,
  ShellEvent,
} from './types';

const SERVER_FAILURE_STATUS = 500;

/** Per-window projection of the server session and local editor state. */
export class SessionModel {
  view = $state.raw<SessionView | null>(null);
  connection = $state<ConnectionState>('connecting');
  draft = $state('');
  message = $state('');
  uncertain = $state(false);
  sending = $state(false);
  private pending: PendingCommand | null = null;
  private activeRequest: string | null = null;
  private acknowledgedClose = false;
  private readonly transport: SessionTransport;

  constructor() {
    this.transport = new SessionTransport({
      snapshot: (snapshot) => this.setSnapshot(snapshot),
      event: (event) => this.receive(event),
      connection: (state) => { this.connection = state; },
      failure: (message) => { this.message = message; },
    });
  }

  /** Connect when the owning component mounts. */
  connect(): void {
    void this.transport.connect();
  }

  /** Clean up the owning component's stream. */
  dispose(): void {
    this.transport.dispose();
  }

  /** Submit a draft or retry the exact same uncertain command. */
  async submit(): Promise<void> {
    if (this.sending) return;
    if (!this.pending && !this.draft.trim()) return;
    this.pending ??= {
      requestId: crypto.randomUUID(),
      line: this.draft,
    };
    const submitted = this.pending;
    this.activeRequest = submitted.requestId;
    this.sending = true;
    this.message = '';
    try {
      await this.transport.submit(submitted);
      this.accept(submitted.requestId);
    } catch (error) {
      this.submissionFailed(error, submitted);
    } finally {
      if (this.activeRequest === submitted.requestId) {
        this.activeRequest = null;
        this.sending = false;
      }
    }
  }

  /** Let the backend shut down after the last event is visibly rendered. */
  acknowledgeClose(): void {
    if (this.acknowledgedClose || !this.view) return;
    this.acknowledgedClose = true;
    void this.transport.acknowledgeClose(this.view.cursor);
  }

  private setSnapshot(snapshot: SessionSnapshot): void {
    this.view = fromSnapshot(snapshot);
  }

  private receive(event: ShellEvent): void {
    if (!this.view) return;
    this.view = applyEvent(this.view, event);
    if (event.kind === 'input' && event.command_id) {
      this.accept(event.command_id);
    }
  }

  private accept(requestId: string): void {
    if (this.pending?.requestId !== requestId) return;
    this.pending = null;
    this.activeRequest = null;
    this.sending = false;
    this.draft = '';
    this.uncertain = false;
    this.message = '';
  }

  private submissionFailed(
    error: unknown,
    submitted: PendingCommand,
  ): void {
    if (this.pending?.requestId !== submitted.requestId) return;
    if (error instanceof ApiError && error.status < SERVER_FAILURE_STATUS) {
      this.pending = null;
      this.uncertain = false;
      this.message = error.message;
      return;
    }
    this.uncertain = true;
    this.message = 'Ответ не получен. Можно безопасно повторить отправку.';
  }
}
