const FORWARD = 1;

/** Preserve an unfinished line while navigating server-owned history. */
export class HistoryCursor {
  private index: number | null = null;
  private savedDraft = '';

  /** Return the next history item, or restore the user's original draft. */
  move(direction: -1 | 1, draft: string, history: string[]): string {
    if (!history.length) return draft;
    if (this.index === null) {
      if (direction === FORWARD) return draft;
      this.savedDraft = draft;
      this.index = history.length;
    }
    this.index = Math.max(0, this.index + direction);
    if (this.index >= history.length) {
      this.index = null;
      return this.savedDraft;
    }
    return history[this.index];
  }

  /** A submitted or edited line starts a new history navigation cycle. */
  reset(): void {
    this.index = null;
    this.savedDraft = '';
  }
}
