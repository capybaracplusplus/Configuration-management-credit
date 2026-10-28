/** Public transport records shared by the browser application. */
export type SessionState =
  | 'waiting'
  | 'starting'
  | 'ready'
  | 'running'
  | 'closing'
  | 'closed';

export type ConnectionState =
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'closed'
  | 'failed';

export interface ShellEvent {
  seq: number;
  kind: 'input' | 'output' | 'complete' | 'state';
  command_id?: string;
  line?: string;
  prompt?: string;
  text?: string;
  stream?: 'stdout' | 'stderr';
  status?: number;
  cwd?: string;
  state?: SessionState;
}

export interface SessionSnapshot {
  session_id: string;
  username: string;
  hostname: string;
  title: string;
  cwd: string;
  state: SessionState;
  configuration: {
    vfs: string | null;
    startup_script: string | null;
  };
  events: ShellEvent[];
  cursor: number;
}

export interface SessionView extends SessionSnapshot {
  history: string[];
}

export interface PendingCommand {
  requestId: string;
  line: string;
}

export interface TransportListener {
  snapshot: (snapshot: SessionSnapshot) => void;
  event: (event: ShellEvent) => void;
  connection: (state: ConnectionState) => void;
  failure: (message: string) => void;
}
