# Review surface — maintaining `graph.html`

`spec_render.py` writes one self-contained file: no CDN, no fonts, no build
step. The data is embedded as JSON in `<script id="payload">`; everything else
is rendering. Keep it that way — a preview that needs the network is a preview
that fails offline.

| part | lives in | note |
|---|---|---|
| payload | `build_payload()` in `spec_model.py` | the only data the page knows |
| layout | `layout()` | depth by BFS from `roots`, one barycenter pass |
| drawing | `draw()` | SVG only, no canvas, no library |
| tabs | `renderCards` / `renderScenarios` / `renderTrace` / `renderTable` | one function per tab, re-run on filter change |
| inspector | `showBehaviour` / `showScenario` / `showState` / `showTransition` / `showStep` / `showMeta` | rebuilt on each selection |

## Rules that are easy to break

- **Readable beats complete.** `fit()` clamps zoom to ≥0.72 and left-aligns
  when the graph is wider than the frame; the user pans instead of squinting at
  7px labels. Do not remove the clamp to make a big machine "fit".
- **The selected node stays visible.** `openInspector()` re-fits and
  `focusNode()` centres the selection inside `usableW()` — the stage width minus
  an overlay inspector. Skip it and the panel covers the node you just clicked.
- **Height follows content.** The stage is sized from the node bbox, clamped to
  340–700px; a fixed tall stage leaves the chat frame mostly empty.
- **React to width, not height.** The `ResizeObserver` ignores height-only
  changes; otherwise our own stage resize triggers a second fit and the view
  jumps right after the inspector opens.
- **`rendered` ≠ `generated`.** `rendered` is when the HTML was written;
  `generated` exists only after a test run. Collapsing them makes every
  `implemented` behaviour look verified — the "unverified" state keys off
  `DATA.generated` for exactly this reason.
- **Colour is status, never decoration.** Edge colour = worst attached
  behaviour; step colour = plan status; a `done` step with a failing check stays
  red. Never "fix" a red node by changing the palette.
- **Diff rings key off behaviours, not states.** The diff set holds `BEH-…` ids;
  a state is touched when one of the behaviours attached to its edges is in that
  set. Comparing the state id to the diff set never matches, and a delta renders
  as if nothing changed.
- **Stacked self-loops need an index.** Two transitions on one state draw the
  same arc; offset each loop by its position (`lift = 1 + k * 0.4`) or one edge
  hides the other and both labels collide.
- **Long node titles wrap, they do not vanish.** Four lines with an ellipsis
  plus a `<title>` tooltip for plan steps; three lines for states. Truncating
  silently loses the thing the reviewer needs.
- **The node panel leads with behaviours.** A node is clicked to answer "which
  rules live here", so `showState` renders `Behaviours (N)` first, each row a
  `data-beh` link into `showBehaviour`, and only then the transitions in/out —
  and those only when non-empty (a `flow` step has none; the old "none" rows
  just pushed the behaviours out of view). Machine edges carry the transition
  **object** in `edge.transition`; code that treats it as an id silently renders
  nothing.
- **Clamped card text needs a way out.** `.card p` clamps to three lines, so a
  card whose text is clamped must open the inspector — invariants and context
  cards included (`showMeta`, bound by `data-meta`), not only behaviours. A card
  that looks clickable and is not strands the half of the rule that got cut.
- **Multi-item values render one `<li>` per item.** Joining a list into one
  string with `; ` turns a three-item scenario into a paragraph no reviewer
  reads. `given`, `then`, refs and steps are separate items in the inspector,
  never a concatenated string.
- **A new inspector panel copies `showScenario` whole**: header `id · owner`,
  a link back to the owning entity, hidden for `kind: refactor`, closed by
  `setTab` and Escape. And wire the click in every surface that shows the
  entity — card, table row and graph node all reach the same panel; the
  surface without the click is the one the user reports as missing.
- **Measure the container after it is displayed.** `renderTrace()` sizes its
  columns from `box.clientWidth`; a flex child with auto width measures 0 before
  it has content, so the canvas silently falls back to a 700px viewBox and every
  label scales with it. Give the panels `flex:1;min-width:0` and read the width
  only after the tab's `display` is set.
- **Derive label budgets from the measured width, not a fixed character count.**
  Trace columns are percentage widths; a hard `slice(0, 34)` clips mid-word at
  narrow frames. Compute the budget from the column width and cut with `…`.
- **No hand edits.** If a label is wrong, the YAML or the payload is wrong.

## Theme

The frame injects `--foreground`, `--muted-foreground`, `--accent`, `--border`,
`--card`; the page must not set its own background, font, or margin. Palette hue
is picked from the luminance of `--foreground`, so light and dark both work — a
new colour needs both a light and a dark value in `PAL`.

## Testing a change

```
python spec_render.py <spec> --results results.json --out /tmp/g.html
```

Open it at ~760px and ~1100px: below 880px the panel sits in normal flow above
the cards (full width, page scrolls to it); above it, it is docked as a 320px
column. Check one selection, one tab switch, and one resize — that is where the
fit/observer bugs surface.

For a click-path change, drive the real file instead of eyeballing: open the
rendered HTML over `file://` in the browser and dispatch
`new MouseEvent('click', {bubbles: true})` on the card — the handlers are
plain click listeners, no navigation — then assert the `#inspector` DOM
(`open` class, section count, rule text length). Keep screenshots in the
loop: clamp, overlay and cue are layout facts a DOM read cannot confirm.
