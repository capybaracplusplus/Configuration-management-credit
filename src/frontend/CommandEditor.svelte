<script lang="ts">
  import { tick } from 'svelte';
  import { HistoryCursor } from './history';

  interface Props {
    draft: string;
    disabled: boolean;
    history: string[];
    cwd: string;
    onsubmit: () => void;
  }

  let {
    draft = $bindable(''),
    disabled,
    history,
    cwd,
    onsubmit,
  }: Props = $props();

  let input: HTMLInputElement;
  const cursor = new HistoryCursor();

  $effect(() => {
    if (!disabled) void tick().then(() => input?.focus());
  });

  /** Navigate prior commands without submitting IME composition input. */
  function keydown(event: KeyboardEvent): void {
    if (event.isComposing) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      cursor.reset();
      onsubmit();
    }
    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      event.preventDefault();
      const direction = event.key === 'ArrowUp' ? -1 : 1;
      draft = cursor.move(direction, draft, history);
      void tick().then(() => input.setSelectionRange(
        draft.length, draft.length,
      ));
    }
  }
</script>

<div class="command-editor" class:disabled>
  <span class="editor-directory" title={cwd}>{cwd}</span>
  <span class="prompt-sign" aria-hidden="true">❯</span>
  <label class="visually-hidden" for="command">Команда</label>
  <input
    bind:this={input}
    bind:value={draft}
    id="command"
    name="command"
    type="text"
    autocomplete="off"
    autocapitalize="off"
    spellcheck="false"
    placeholder={disabled ? 'Ожидание…' : 'Введите команду'}
    aria-describedby="editor-help"
    {disabled}
    onkeydown={keydown}
    oninput={() => cursor.reset()}
  />
  <button
    class="enter-button"
    aria-label="Выполнить команду"
    disabled={disabled || !draft.trim()}
    onclick={() => { cursor.reset(); onsubmit(); }}
  >↵</button>
</div>
