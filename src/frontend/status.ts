import type { ConnectionState, SessionState } from './types';

const SESSION_LABELS: Record<SessionState, string> = {
  waiting: 'Подготовка сеанса',
  starting: 'Стартовый скрипт',
  ready: 'Готов к работе',
  running: 'Выполнение',
  closing: 'Завершение сеанса',
  closed: 'Сеанс завершён',
};

const CONNECTION_LABELS: Record<ConnectionState, string> = {
  connecting: 'Подключение',
  connected: '',
  disconnected: 'Восстановление соединения',
  closed: 'Сеанс завершён',
  failed: 'Нет соединения',
};

/** Prefer explicit session completion over a subsequent socket closure. */
export function statusLabel(
  connection: ConnectionState,
  session?: SessionState,
): string {
  if (session === 'closed') return SESSION_LABELS.closed;
  if (connection !== 'connected') return CONNECTION_LABELS[connection];
  return SESSION_LABELS[session ?? 'waiting'];
}
