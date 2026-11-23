# Pillow motion-graphics renderer

One Python process, one frame at a time, piped into ffmpeg. No GPU, no browser, no timeline software.

## Frame model

`templates/core.py` gives a `Frame` that holds a cached gradient background plus an RGBA overlay:

```python
f = Frame()
f.chrome()                     # brand line + green rule, top-left, never a scene number
f.text((120, 300), "62", 400, INK, a)
f.para((120, 700), long_copy, 48, SOFT, a, max_w=1500)
f.rect((120, 400, 1570, 470), GREEN, a)
f.source("FONTE  GLOBAL E-WASTE MONITOR 2024")
img = f.img()                  # RGB, ready for the pipe
```

Scene function signature is `draw(t, f)`; `render(dur, draw, out)` loops `int(dur*30)` frames.

## Typography

- Windows: `arial.ttf` / `arialbd.ttf` for display, `consola.ttf` / `consolab.ttf` for mono labels, sources and
  kickers. Accents are safe in all four.
- `tracked()` draws uppercase labels character by character with letterspacing — the single cheapest way to make
  text look designed rather than defaulted.
- `wrap()` + a `max_w` argument on every paragraph; `fit_size()` shrinks a display line until it fits instead of
  letting it run past the margin.
- Hierarchy that survives compression: display 300–400 px for a number, 44–56 px for a claim, 30–36 px for
  support copy, 19–22 px mono for source and kicker.

## Safe area and margins

1920×1080 with a 120 px margin: content lives in `(120, 84) – (1800, 996)`. Verify numerically, not by eye —
compute `x + font.getlength(s)` against 1800 for every long string, and remember that letterspacing adds
`sum(len)+1 * tracking`.

## Colour discipline

One accent for emphasis (green), one for alert/regression (amber), everything else ink/grey/soft. Reserve the
accent so a single green word still means something at frame 7000.

## The compositing trap

`ImageDraw` on an RGBA image **overwrites** alpha; it does not alpha-composite. Draw a 40%-alpha rectangle over
another shape and you get a hole showing the gradient behind, not a tinted shape. Two fixes:

1. Pre-mix against the known background: `mix(BG, colour, k)` and draw opaque.
2. Draw a group into its own `Image.new("RGBA", ...)` layer and `alpha_composite` that layer once.

Use (1) for flat shapes on the background, (2) whenever a group fades in or out as a unit.

## Performance

About 30–40 ms per 1080p frame on a modern laptop core: a 38 s clip renders in ~32 s wall, a 168 s clip in ~4 min.
Render at 30 fps, CRF 18, `yuv420p`, `+faststart`. Preview stills with `preview(dur, draw, [t1, t2, ...])` before
the full render — iterating on PNGs costs seconds instead of minutes.

## Structure per scene

```python
DUR = 139.9

def b1(t, f): ...        # one function per beat, windows in absolute scene seconds
def b2(t, f): ...

BEATS = ((0.0, 10.8, b1), (10.8, 22.8, b2), ...)

def draw(t, f):
    for i, (s, e, fn) in enumerate(BEATS):
        if s - .02 <= t < e + .32:
            sub = Frame(); fn(t, sub)
            ga = ease_io(seg(t, s, s + .3)) * (1 - ease_io(seg(t, e, e + .3)))
            compose(f, sub, ga)
    f.chrome()
```

A `BEATS` table makes re-timing a data edit instead of a hunt through the file.
