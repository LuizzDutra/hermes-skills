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
| inspector | `showBehaviour` / `showState` / `showTransition` / `showStep` | rebuilt on each selection |

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
- **Long node titles wrap, they do not vanish.** Four lines with an ellipsis
  plus a `<title>` tooltip for plan steps; three lines for states. Truncating
  silently loses the thing the reviewer needs.
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

Open it at ~760px and ~1100px: the inspector is an overlay below 880px and a
docked panel above it. Check one selection, one tab switch, and one resize —
that is where the fit/observer bugs surface.
