# -*- coding: utf-8 -*-
"""sync_check.py — one-glance sync audit for a narrated cut.

For every sentence of a scene, grab the frame that is on screen 0.6 s after that
sentence starts, and print the sentence under it. If the frame does not show what
the sentence is talking about, the beat is misplaced.

    python sync_check.py <master.mp4> <timeline.json> <frases.json> <scene_n> [offset]

frases.json shape:  {"4": {"marcas": [{"t": 0.05, "dur": 3.36, "txt": "..."}, ...]}}
timeline.json shape: {"cenas": {"4": {"inicio": 248.98, "fim": 388.9, "dur": 139.92}}}

Writes qa/sync_scNN.png next to the master. Pillow + ffmpeg only; paths may be Windows.
"""
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

MAX_CUES = 12          # even-sample when a scene has more sentences than this
COLS = 2
THUMB = (940, 529)
CAP = 46


def main():
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    movie, tl_path, fr_path, n = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    offset = float(sys.argv[5]) if len(sys.argv) > 5 else 0.6

    tl = json.load(open(tl_path, encoding="utf-8"))["cenas"][n]
    marcas = json.load(open(fr_path, encoding="utf-8"))[n]["marcas"]
    start = float(tl["inicio"])

    step = max(1, len(marcas) // MAX_CUES)
    cues = marcas[::step]

    outdir = os.path.join(os.path.dirname(os.path.abspath(movie)), "qa")
    os.makedirs(outdir, exist_ok=True)
    frames = []
    for i, m in enumerate(cues):
        t = start + float(m["t"]) + offset
        p = os.path.join(outdir, f"sync{n}_{i}.png")
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{t:.2f}", "-i", movie, "-frames:v", "1", p], check=True)
        frames.append((p, float(m["t"]), m["txt"]))

    rows = (len(frames) + COLS - 1) // COLS
    sh = Image.new("RGB", (COLS * THUMB[0], rows * (THUMB[1] + CAP)), (18, 22, 21))
    d = ImageDraw.Draw(sh)
    font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 17) if os.name == "nt" \
        else ImageFont.load_default()
    for i, (p, c, txt) in enumerate(frames):
        x = (i % COLS) * THUMB[0]
        y = (i // COLS) * (THUMB[1] + CAP) + CAP
        sh.paste(Image.open(p).resize((THUMB[0] - 10, THUMB[1] - 10), Image.LANCZOS), (x, y))
        d.text((x + 6, y - 34), f"cena {n} · t+{c:.1f}s", font=font, fill=(74, 222, 128))
        d.text((x + 6, y - 18), txt[:88], font=font, fill=(150, 162, 155))
    out = os.path.join(outdir, f"sync_sc{int(n):02d}.png")
    sh.save(out)
    print("ok", out, sh.size)


if __name__ == "__main__":
    main()
