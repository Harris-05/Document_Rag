/** The most documents that can be compared in one question. The server enforces its own limit too. */
export const MAX_COMPARE = 5;
export const MIN_COMPARE = 2;

/** Adds or removes a document from the selection, never going past `max`. Order is the order chosen. */
export function toggleSelection(selected: string[], id: string, max = MAX_COMPARE): string[] {
  if (selected.includes(id)) return selected.filter((existing) => existing !== id);
  if (selected.length >= max) return selected;
  return [...selected, id];
}

/** Drops documents that no longer exist (for example one that was just deleted). */
export function pruneSelection(selected: string[], available: string[]): string[] {
  const exists = new Set(available);
  const kept = selected.filter((id) => exists.has(id));
  return kept.length === selected.length ? selected : kept;
}
