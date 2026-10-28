<script lang="ts">
  import { tick } from 'svelte';
  import { eventText } from './reducer';
  import type { ShellEvent } from './types';

  let { events }: { events: ShellEvent[] } = $props();
  let viewport: HTMLDivElement;
  let following = true;
  const BOTTOM_TOLERANCE = 32;

  $effect(() => {
    void events.length;
    if (following) void tick().then(scrollToBottom);
  });

  /** Preserve the viewport while the user reads an earlier command. */
  function trackScroll(): void {
    const remaining = viewport.scrollHeight - viewport.scrollTop;
    following = remaining - viewport.clientHeight < BOTTOM_TOLERANCE;
  }

  /** Follow arriving output only when the user has stayed at the bottom. */
  function scrollToBottom(): void {
    if (viewport) viewport.scrollTop = viewport.scrollHeight;
  }
</script>

<!-- Keep the scroll region keyboard-accessible. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
  class="transcript-scroll"
  bind:this={viewport}
  onscroll={trackScroll}
  tabindex="0"
  role="region"
  aria-label="История команд"
>
  <pre
    class="transcript"
    role="log"
    aria-live="polite"
  >{#each events as event (event.seq)}<span
    class:command-line={event.kind === 'input'}
    class:error-line={event.stream === 'stderr'}
  >{eventText(event)}</span>{/each}</pre>
</div>
