// Pure Ace adapter for explicit, verified current-file navigation.
// Ace coordinates are zero-based; SAT findings use one-based inclusive lines.
export function revealAceSource(editor, ace, selection, previous = null) {
  const session = editor?.getSession?.() || editor?.session;
  const length = session?.getLength?.();
  const first = selection?.start_line, last = selection?.end_line;
  if (!session || !Number.isSafeInteger(length) || length < 1 ||
      !Number.isSafeInteger(first) || !Number.isSafeInteger(last) ||
      first < 1 || last < first || last > length || last - first > 79) {
    throw new Error('Finding line range is not present in the opened editor');
  }
  const Range = ace?.require?.('ace/range')?.Range;
  if (typeof Range !== 'function' || typeof session.addMarker !== 'function' ||
      typeof session.removeMarker !== 'function' || typeof editor.gotoLine !== 'function' ||
      typeof editor.scrollToLine !== 'function') {
    throw new Error('Ace range navigation is unavailable');
  }
  const startRow = first - 1, endRow = last - 1;
  const endColumn = session.getLine(endRow).length;
  const range = new Range(startRow, 0, endRow, endColumn);
  editor.resize?.(true);
  const id = session.addMarker(range, 'pah-uca-source-highlight', 'fullLine', false);
  try {
    editor.gotoLine(first, 0, true);
    editor.scrollToLine(startRow, true, true, () => {});
  } catch (error) {
    session.removeMarker(id);
    throw error;
  }
  // Keep the finding visible even when the user returns focus to the SAT pane.
  // Clear the prior marker only after the new target has been installed.
  if (previous?.session && Number.isSafeInteger(previous.id)) {
    try { previous.session.removeMarker(previous.id); } catch (_) { /* closed tab */ }
  }
  return {session, id};
}
