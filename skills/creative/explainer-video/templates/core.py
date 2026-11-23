# -*- coding: utf-8 -*-
"""core.py - biblioteca visual compartilhada de um video explicativo.

Copie para gfx/core.py do projeto e importe em cada cena:
    from core import *
    def draw(t, f): ...
    render(60.5, draw, "out/sc01.mp4")
"""
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
MARGIN = 120
SAFE = (MARGIN, 84, W - MARGIN, H - 84)

BG_TOP, BG_BOT = (14, 19, 17), (8, 10, 9)
INK, SOFT, GREY = (242, 245, 243), (196, 205, 200), (128, 141, 134)
DIM, LINE = (74, 86, 80), (48, 58, 52)
GREEN, AMBER = (74, 222, 128), (245, 170, 68)
KICK = "NOME DO PROJETO  ·  BLOCO"

_FD = "C:/Windows/Fonts/"
BLACK = lambda s: ImageFont.truetype(_FD + "arialbd.ttf", int(s))
REG = lambda s: ImageFont.truetype(_FD + "arial.ttf", int(s))
MONO = lambda s: ImageFont.truetype(_FD + "consola.ttf", int(s))
MONOB = lambda s: ImageFont.truetype(_FD + "consolab.ttf", int(s))


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def seg(t, t0, t1):
    return 1.0 if t1 <= t0 and t >= t1 else clamp((t - t0) / (t1 - t0)) if t1 > t0 else 0.0


def ease_out(x):
    return 1 - (1 - x) ** 3


def ease_io(x):
    return 3 * x * x - 2 * x * x * x


def lerp(a, b, k):
    return a + (b - a) * k


def mix(c1, c2, k):
    return tuple(int(round(lerp(a, b, k))) for a, b in zip(c1, c2))


def rgba(c, a):
    return (c[0], c[1], c[2], int(round(255 * clamp(a))))


def fade(t, t_in, t_out=None, d_in=0.6, d_out=0.5):
    a = ease_out(seg(t, t_in, t_in + d_in))
    if t_out is not None:
        a *= 1 - ease_io(seg(t, t_out - d_out, t_out))
    return a


def br(v, dec=0):
    """numero no formato brasileiro"""
    s = f"{v:,.{dec}f}"
    return s.replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")


def tracked(d, xy, s, fnt, fill, tr=4):
    x, y = xy
    for ch in s:
        d.text((x, y), ch, font=fnt, fill=fill)
        x += fnt.getlength(ch) + tr


def tracked_w(s, fnt, tr=4):
    return sum(fnt.getlength(c) + tr for c in s) - tr


def wrap(s, fnt, max_w):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if fnt.getlength(t) > max_w and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def fit_size(text, maker, max_w, start, floor=18):
    s = start
    while s > floor and maker(s).getlength(text) > max_w:
        s -= 2
    return s


def _bg():
    grad = Image.new("RGB", (8, 128))
    gd = ImageDraw.Draw(grad)
    for y in range(128):
        gd.line([(0, y), (8, y)], fill=mix(BG_TOP, BG_BOT, y / 127))
    return grad.resize((W, H), Image.BILINEAR)


_BG = _bg()


class Frame:
    def __init__(self):
        self.base = _BG.copy().convert("RGBA")
        self.ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.ov)

    def text(self, xy, s, size, color, a=1.0, bold=True, tracking=0, max_w=None, mono=False):
        if a <= 0.01 or not s:
            return
        maker = MONOB if mono else (BLACK if bold else REG)
        fnt = maker(size)
        if max_w and fnt.getlength(s) > max_w:
            fnt = maker(fit_size(s, maker, max_w, size))
        if tracking:
            tracked(self.d, xy, s, fnt, rgba(color, a), tracking)
        else:
            self.d.text(xy, s, font=fnt, fill=rgba(color, a))

    def para(self, xy, s, size, color, a=1.0, max_w=None, lead=1.28, bold=False):
        if a <= 0.01 or not s:
            return xy[1]
        fnt = (BLACK if bold else REG)(size)
        y = xy[1]
        for ln in wrap(s, fnt, max_w or (W - 2 * MARGIN)):
            self.d.text((xy[0], y), ln, font=fnt, fill=rgba(color, a))
            y += int(size * lead)
        return y

    def rect(self, box, color, a=1.0, r=0):
        if a <= 0.01:
            return
        if r:
            self.d.rounded_rectangle(box, radius=r, fill=rgba(color, a))
        else:
            self.d.rectangle(box, fill=rgba(color, a))

    def line(self, pts, color, a=1.0, w=2):
        if a > 0.01:
            self.d.line(pts, fill=rgba(color, a), width=w)

    def circle(self, box, color, a=1.0, outline=False, w=3):
        if a <= 0.01:
            return
        if outline:
            self.d.ellipse(box, outline=rgba(color, a), width=w)
        else:
            self.d.ellipse(box, fill=rgba(color, a))

    def chrome(self, a=1.0):
        tracked(self.d, (MARGIN, 84), KICK, MONO(20), rgba(GREY, a), 3)
        self.d.rectangle([MARGIN, 130, MARGIN + 56, 133], fill=rgba(GREEN, a))

    def source(self, s, a=1.0):
        tracked(self.d, (MARGIN, H - 92), s, MONO(19), rgba(DIM, a), 1)

    def img(self):
        self.base.alpha_composite(self.ov)
        return self.base.convert("RGB")


def slate(f, label, sub="", a=1.0, box=None):
    x0, y0, x1, y1 = box or (MARGIN, 300, W - MARGIN, 780)
    f.rect((x0, y0, x1, y1), (18, 24, 21), a, r=14)
    f.d.rectangle([x0, y0, x1, y1], outline=rgba((52, 64, 58), a), width=2)
    tracked(f.d, (x0 + 44, y0 + 40), "B-ROLL", MONO(22), rgba(GREEN, a * 0.85), 4)
    tracked(f.d, (x0 + 44, y0 + 120), label, MONOB(34), rgba(INK, a), 2)
    if sub:
        f.para((x0 + 44, y0 + 200), sub, 28, GREY, a, max_w=max(200, x1 - x0 - 88))


def counter(f, xy, value, size=300, color=INK, a=1.0, dec=0, suffix=None):
    if a <= 0.01:
        return
    s = br(value, dec)
    f.d.text(xy, s, font=BLACK(size), fill=rgba(color, a))
    if suffix:
        x = xy[0] + BLACK(size).getlength(s) + 16
        f.d.text((x, xy[1] + size * 0.52), suffix, font=BLACK(int(size * 0.32)), fill=rgba(GREEN, a))


def label(f, xy, s, color=GREY, a=1.0, size=20, tr=3):
    tracked(f.d, xy, s, MONO(size), rgba(color, a), tr)


def chip(f, xy, text, color=SOFT, a=1.0, size=24, pad=(18, 10)):
    fnt = MONO(size)
    w = tracked_w(text, fnt, 2) + 2 * pad[0]
    h = size + 2 * pad[1]
    f.d.rectangle((xy[0], xy[1], xy[0] + w, xy[1] + h),
                  outline=rgba(mix(color, BG_BOT, 0.45), a), width=2)
    tracked(f.d, (xy[0] + pad[0], xy[1] + pad[1] - 2), text, fnt, rgba(color, a), 2)
    return xy[0] + w


def render(dur, draw, out, q=18, verbose=True):
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    n = int(round(dur * FPS))
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", str(q), "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        f = Frame()
        draw(i / FPS, f)
        p.stdin.write(f.img().tobytes())
        if verbose and i and i % 300 == 0:
            print(f"  {i}/{n} frames", flush=True)
    p.stdin.close()
    p.wait()
    print(f"ok {out}  {n} frames  {os.path.getsize(out)//1024} KB", flush=True)


def preview(dur, draw, times, outdir):
    os.makedirs(outdir, exist_ok=True)
    for t in times:
        f = Frame()
        draw(float(t), f)
        p = os.path.join(outdir, f"t{t:06.2f}.png")
        f.img().save(p)
        print("frame", p, flush=True)
