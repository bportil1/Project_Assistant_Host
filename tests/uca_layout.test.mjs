import test from 'node:test';
import assert from 'node:assert/strict';
import {defaultLayout, normalizeLayout, withPane, withWidth, layoutKey} from '../pah/web/static/uca-layout-state.mjs';

test('one, two and three pane layouts retain stable ordering', () => {
  const all = defaultLayout();
  assert.deepEqual(all.visible, ['editor', 'pypique', 'analyzer']);
  const two = withPane(all, 'editor', false);
  assert.deepEqual(two.visible, ['pypique', 'analyzer']);
  const one = withPane(two, 'pypique', false);
  assert.deepEqual(one.visible, ['analyzer']);
  assert.deepEqual(withPane(one, 'analyzer', false), one);
  assert.deepEqual(withPane(one, 'editor', true).visible, ['editor', 'analyzer']);
});
test('invalid state sanitizes and widths clamp', () => {
  const value = normalizeLayout({visible: ['bad', 'pypique', 'pypique'], widths: {editor: -50, pypique: 1000, analyzer: NaN}});
  assert.deepEqual(value.visible, ['pypique']);
  assert.equal(value.widths.editor, 15);
  assert.equal(value.widths.pypique, 70);
  assert.equal(value.widths.analyzer, 33);
  assert.equal(withWidth(defaultLayout(), 'editor', 45).widths.editor, 45);
  assert.throws(() => withWidth(defaultLayout(), 'bad', 20));
});
test('workspace and repository identity segregate saved layouts', () => {
  assert.notEqual(layoutKey('a', '/one'), layoutKey('a', '/two'));
  assert.notEqual(layoutKey('a', '/one'), layoutKey('b', '/one'));
  assert.equal(layoutKey('', '/one'), null);
  assert.equal(layoutKey('a', ''), null);
});
