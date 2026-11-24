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
  7px labels. Do not remove the clamp to make a big machine "fit". The layout
  spends 190px per depth layer (215 for plans, node `r = 44`), so nothing past
  ~1260 user units can fit a 960px frame at that clamp: measure
  `view.getBBox().width * window.__vt.k` against `stage.clientWidth - 48` before
  saying a graph fits, and shorten the flow instead of shrinking the floor.
- **The selected node stays visible.** `openInspector()` re-fits and
  `focusNode()` centres the selection inside `usableW()` — the stage width minus
  an overlay inspector. Skip it and the panel covers the node you just clicked.
  Below 880px the inspector is a block after the stage instead of an overlay:
  when it is in flow (`position: static`), `openInspector()` scrolls it into
  view — a panel that opens below the fold reads as a click that did nothing.
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
  nothing. A `flow` edge has no transition at all: its click opens the
  destination step (`showStep(edge.to)`), never `showTransition(undefined)` —
  the throw leaves every flow edge dead.
- **Bind clicks by `data-*` attribute, not by matching row text.** A regex over
  the row's text also matches ids quoted inside another row's prose, and the
  click opens the wrong panel.
- **The click path owns the selection ring.** `draw()` paints the dashed ring
  from `state.sel`; a handler that opens the panel without assigning it leaves
  the graph without the highlight the status filter already gives. Set
  `state.sel` where the panel opens, clear it where the panel closes.
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

- **There is no synthetic-click shortcut.** `setPointerCapture` on the `<svg>`
  (which pan/zoom needs) retargets the trailing `click` at the `<svg>`, so an
  `dispatchEvent(new MouseEvent('click'))` probe passes while a real click on a
  node does nothing. Capture only when the gesture starts on empty canvas, mark
  every clickable group `data-hit` (`node` / `edge`), suppress the click a drag
  would deliver, and probe with `Input.dispatchMouseEvent`, never with a
  constructed event.
- **Hairline geometry needs a fat, invisible hit target.** A 1.8px edge stroke
  is effectively unclickable with a real pointer; overlay a 14px transparent
  stroke carrying the same `data-hit` and wire the edge label to the same
  handler — the label is the click the user tries first.
- **Focus outlines are keyboard-only.** Node groups with `tabindex` get a
  focus ring on click; a square outline on a circular node reads as a broken
  render where the panel should have opened. Scope the outline to
  `:focus-visible`.

- **A status missing from `ORDER` drops its cards.** Cards are grouped by
  `effective(b)` and only `ORDER` keys are rendered, so a status the YAML still
  allows must map to an `ORDER` key before it reaches the grid. `approved` maps
  to `missing` for that reason — reintroducing it as a bucket means adding it to
  `ORDER`, `RANK`, `RANK_LABEL` and `PAL` together, or behaviours vanish from the
  Behaviours tab while the header still counts them.
- **The legend is four buckets.** `implemented` (teal without a run, green with
  one), `untested`, `proposed`, `failing`. `draft` and `divergent` keep colours
  but stay out of the legend; adding a fifth row means the summary and the
  filters have to agree with it. The header counters come from the same
  `effective()` mapping the paint uses, one chip per bucket present — a count
  computed by a different rule puts a number in the header that the node
  colours contradict. Filters key off the painted bucket too: `implemented`
  includes the unverified, or the filter empties a graph the legend calls
  populated.

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

**Assert geometry numerically; a screenshot is not evidence.** Every layout fact
this file cares about has a number attached, so read the number:

| question | read |
|---|---|
| does the graph fit the frame? | `view.getBBox().width * __vt.k` vs `stage.clientWidth - 48` |
| is the inspector an overlay or in flow? | `getComputedStyle(inspector).position`, its `getBoundingClientRect()` |
| did the click open the panel? | `#inspector` has class `open`, N sections, rule text length > 0 |
| is the node on screen? | its `getBoundingClientRect()` inside the viewport |
| is the colour right? | `getComputedStyle(el).stroke` / `.fill` |

No screenshot, and no vision pass, on a render you just generated: it costs a
turn and an image read to learn what one `clientWidth` comparison settles, and
"looks fine" is not a claim a later run can re-check. Vision belongs to images
the repo produces as output (a chart, a frame of an explainer) — never to
`graph.html`, whose entire state is the payload plus the stylesheet you already
have in hand. Clamp, overlay and cue are the only judgement calls, and each one
reduces to a rect comparison: a clamp is `scrollHeight > clientHeight` on the
clamping element, an overlay is an `x`/`y` intersection of two rects.

For a click-path change, drive the real file — with **real pointer input**, not
`dispatchEvent(new MouseEvent('click'))`. A synthetic click skips pointer events
entirely, so it passes through a `setPointerCapture` that would retarget the real
click and leave the node dead: that is exactly how the "click does nothing" bug
survived a green synthetic probe. In the browser tool, send
`Input.dispatchMouseEvent` (`mousePressed` + `mouseReleased` at the element's
on-screen centre) and check `elementFromPoint` first — at 780×380 the node you
aimed at is often below the fold, and the probe then tests nothing.

Then assert the `#inspector` DOM (`open` class, section count, rule text
length) and the numbers above, not a picture of them. Force the width with a
device-metrics override (`Emulation.setDeviceMetricsOverride`, e.g. 1000×900
@2x) rather than resizing the window, and run the whole probe — navigate,
dispatch, assert — in one browser call: tab state is not guaranteed between
calls, and the next call finds `about:blank` where your page was.

Palette changes are verified in **both themes**. Outside the desktop frame the
injected vars do not exist, so simulate each: put a
`:root{--foreground:…;--muted-foreground:…;--accent:…;--border:…;--card:…}`
`<style>` before `</head>` — light values once, dark values once — and assert
the *computed* colour of chips, dots and node strokes, not the stylesheet
text. Build the fixture spec with one behaviour per status so every bucket is
on screen at once; a spec that exercises only two buckets ships a palette
half-tested.
