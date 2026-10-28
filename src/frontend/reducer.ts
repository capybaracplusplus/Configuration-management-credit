import type {
  SessionSnapshot,
  SessionView,
  ShellEvent,
} from './types';

const EVENT_STEP = 1;

/** Build a browser projection from an authoritative server snapshot. */
export function fromSnapshot(snapshot: SessionSnapshot): SessionView {
  return {
    ...snapshot,
    events: [...snapshot.events],
    history: snapshot.events
      .filter((event) => event.kind === 'input')
      .map((event) => event.line ?? ''),
  };
}

/** Apply ordered events, discarding replay duplicates without side effects. */
export function applyEvent(
  view: SessionView,
  event: ShellEvent,
): SessionView {
  if (event.seq <= view.cursor) return view;
  if (event.seq !== view.cursor + EVENT_STEP) {
    throw new Error('Нарушен порядок событий. Обновите страницу.');
  }
  return {
    ...view,
    cursor: event.seq,
    cwd: event.cwd ?? view.cwd,
    state: event.state ?? view.state,
    events: [...view.events, event],
    history: event.kind === 'input'
      ? [...view.history, event.line ?? '']
      : view.history,
  };
}

/** Keep terminal text faithful to command output, including missing LF. */
export function eventText(event: ShellEvent): string {
  if (event.kind === 'input') {
    return `${event.prompt ?? '$'} ${event.line ?? ''}\n`;
  }
  return event.kind === 'output' ? event.text ?? '' : '';
}
