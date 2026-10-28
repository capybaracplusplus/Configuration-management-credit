<script lang="ts">
  import { onMount, tick } from 'svelte';
  import CommandEditor from './CommandEditor.svelte';
  import Transcript from './Transcript.svelte';
  import { SessionModel } from './session.svelte';
  import { statusLabel } from './status';

  const session = new SessionModel();
  const view = $derived(session.view);
  const closed = $derived(view?.state === 'closed');
  const ready = $derived(
    view?.state === 'ready' && session.connection === 'connected'
      && !session.sending && !session.uncertain,
  );
  const status = $derived(statusLabel(session.connection, view?.state));
  const identity = $derived(view
    ? `${view.username}@${view.hostname}`
    : 'локальный сеанс');

  onMount(() => {
    session.connect();
    return () => session.dispose();
  });

  $effect(() => {
    if (closed) void tick().then(() => session.acknowledgeClose());
  });
</script>

<svelte:head>
  <title>{view?.title ?? 'Эмулятор оболочки'}</title>
</svelte:head>

<main>
  <header class="page-header">
    <h1>Эмулятор оболочки</h1>
    <span class="project-label">Вариант 12</span>
  </header>

  <section class="session-summary" aria-label="Состояние сеанса">
    <p class="command-help">Введите команду и нажмите Enter.</p>
    <div class="session-badge">
      <span class="status-light" class:active={ready}></span>
      <span>{status}</span>
    </div>
  </section>

  <section id="terminal" class="terminal" aria-label="Терминал">
    <div class="terminal-header">
      <div class="terminal-tab">
        <span class="tab-icon" aria-hidden="true">›_</span>
        <span>{identity}</span>
      </div>
    </div>

    <Transcript events={view?.events ?? []} />

    {#if session.message}
      <div class="notice" role="alert">
        <span>{session.message}</span>
        {#if session.uncertain}
          <button
            disabled={session.sending || closed}
            onclick={() => void session.submit()}
          >Повторить отправку</button>
        {/if}
      </div>
    {/if}

    {#if closed}
      <div class="closed-notice" role="status">
        Сеанс завершён. История команд сохранена на этой странице.
      </div>
    {/if}

    <CommandEditor
      bind:draft={session.draft}
      disabled={!ready}
      history={view?.history ?? []}
      cwd={view?.cwd ?? '/'}
      onsubmit={() => void session.submit()}
    />

    <div class="terminal-footer">
      <span class="footer-status" aria-live="polite">{status}</span>
      <span id="editor-help">
        <kbd>↑</kbd><kbd>↓</kbd> история
        <span class="hint-divider">·</span>
        <kbd>↵</kbd> выполнить
      </span>
    </div>
  </section>

  {#if view}
    <section class="configuration" aria-label="Параметры сеанса">
      <div>
        <span class="config-label">Файловая система</span>
        <span class="config-value" title={view.configuration.vfs ?? ''}>
          {view.configuration.vfs ?? 'Пустая'}
        </span>
      </div>
      <div>
        <span class="config-label">Стартовый скрипт</span>
        <span
          class="config-value"
          title={view.configuration.startup_script ?? ''}
        >{view.configuration.startup_script ?? 'Не задан'}</span>
      </div>
    </section>
  {/if}

  <footer class="page-footer">
    Изменения файлов хранятся в памяти до завершения сеанса.
  </footer>
</main>
