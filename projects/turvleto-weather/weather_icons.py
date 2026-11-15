"""Vector weather icons for the Turvleto card.

No emoji fonts, no SVG files, no network: icons are drawn from primitives with
ImageDraw, so they render identically on the ubuntu runner and on Windows.

`icon_code_for(condition_text)` is the fallback for the current data shape
(get_weather() returns only the Russian `condition` string). Once weather_post.py
exposes the raw WMO `code`, the icon is chosen directly from it — and the icon
can never disagree with the text.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

SUN = (255, 208, 102)
CLOUD = (226, 236, 238)
CLOUD_EDGE = (196, 212, 216)
RAIN = (156, 216, 246)
SNOW = (244, 250, 252)


def icon_code_for(condition_text):
    """Map the Russian condition text back to a WMO-like code (fallback path)."""
    t = (condition_text or "").lower()
    if "гроза" in t:
        return 95
    if "ливн" in t:
        return 80
    if "морос" in t:
        return 51
    if "дожд" in t:
        return 61
    if "снег" in t:
        return 71
    if "туман" in t:
        return 45
    if "облачн" in t and "небольш" in t:
        return 2
    if "облачн" in t:
        return 3
    if "ясно" in t:
        return 0
    return -1


def _p(x, y, s, u, v):
    return (x + u * s, y + v * s)


def _cloud(d, x, y, s, scale=1.0, color=CLOUD, edge=CLOUD_EDGE):
    """Cloud built from three discs on a rounded base."""
    cx, cy = 0.5, 0.5
    w = 0.30 * scale
    for ox, oy, r in ((-0.20, 0.03, 0.135), (0.0, -0.05, 0.175), (0.20, 0.04, 0.125)):
        bx, by = _p(x, y, s, cx + ox, cy + oy)
        rr = r * s * scale
        d.ellipse([bx - rr, by - rr, bx + rr, by + rr], fill=color)
    x0, y0 = _p(x, y, s, cx - 0.34 * scale, cy + 0.0)
    x1, y1 = _p(x, y, s, cx + 0.34 * scale, cy + 0.16 * scale)
    d.rounded_rectangle([x0, y0, x1, y1], radius=int(0.08 * s * scale), fill=color)


def _sun(d, x, y, s, r=0.20, rays=8, color=SUN, cx=0.5, cy=0.5, ray_in=0.27, ray_out=0.40, width=None):
    bx, by = _p(x, y, s, cx, cy)
    rr = r * s
    d.ellipse([bx - rr, by - rr, bx + rr, by + rr], fill=color)
    w = width or max(2, int(0.045 * s))
    import math

    for i in range(rays):
        a = 2 * math.pi * i / rays
        d.line([(bx + math.cos(a) * ray_in * s, by + math.sin(a) * ray_in * s),
                (bx + math.cos(a) * ray_out * s, by + math.sin(a) * ray_out * s)],
               fill=color, width=w)


def _drops(d, x, y, s, count=3, length=0.16, color=RAIN):
    w = max(2, int(0.045 * s))
    for i in range(count):
        u = 0.32 + i * 0.18
        d.line([_p(x, y, s, u, 0.80), _p(x, y, s, u - 0.07, 0.80 + length)],
               fill=color, width=w)


def _flakes(d, x, y, s, count=3, color=SNOW):
    import math

    w = max(2, int(0.035 * s))
    for i in range(count):
        u = 0.34 + i * 0.16
        cx, cy = _p(x, y, s, u, 0.84)
        r = 0.075 * s
        for k in range(3):
            a = math.pi * k / 3
            d.line([(cx - math.cos(a) * r, cy - math.sin(a) * r),
                    (cx + math.cos(a) * r, cy + math.sin(a) * r)], fill=color, width=w)


def _bolt(d, x, y, s, color=SUN):
    pts = [_p(x, y, s, 0.54, 0.66), _p(x, y, s, 0.40, 0.86), _p(x, y, s, 0.50, 0.86),
           _p(x, y, s, 0.44, 1.00), _p(x, y, s, 0.62, 0.80), _p(x, y, s, 0.51, 0.80)]
    d.polygon(pts, fill=color)


def draw_weather_icon(d, box, code):
    """Draw the icon for a WMO code into box=(x, y, size)."""
    x, y, s = box
    code = -1 if code is None else int(code)

    if code == 0:                                   # clear
        _sun(d, x, y, s, r=0.21, rays=8, ray_in=0.28, ray_out=0.42)
    elif code in (1, 2):                            # mostly clear / partly cloudy
        _sun(d, x, y, s, r=0.145, rays=7, cx=0.62, cy=0.36, ray_in=0.20, ray_out=0.30)
        _cloud(d, x, y, s, scale=0.92)
    elif code == 3:                                 # overcast
        _cloud(d, x, y, s, scale=1.05)
    elif code in (45, 48):                          # fog
        _cloud(d, x, y, s, scale=0.95)
        w = max(2, int(0.045 * s))
        for v in (0.84, 0.94):
            d.line([_p(x, y, s, 0.24, v), _p(x, y, s, 0.76, v)], fill=CLOUD_EDGE, width=w)
    elif code in (51, 53, 55, 56, 57):               # drizzle
        _cloud(d, x, y, s, scale=0.95)
        _drops(d, x, y, s, count=3, length=0.08)
    elif code in (61, 63, 65, 66, 67):               # rain
        _cloud(d, x, y, s, scale=0.95)
        _drops(d, x, y, s, count=3, length=0.16)
    elif code in (80, 81, 82):                       # showers
        _cloud(d, x, y, s, scale=0.95)
        _drops(d, x, y, s, count=4, length=0.20)
    elif code in (71, 73, 75, 77):                   # snow
        _cloud(d, x, y, s, scale=0.95)
        _flakes(d, x, y, s, count=3)
    elif code in (95, 96, 99):                       # thunderstorm
        _cloud(d, x, y, s, scale=0.95)
        _bolt(d, x, y, s)
    else:                                            # unknown -> sun behind cloud
        _sun(d, x, y, s, r=0.145, rays=7, cx=0.62, cy=0.36, ray_in=0.20, ray_out=0.30)
        _cloud(d, x, y, s, scale=0.92)


def _font(size):
    for directory in ["/usr/share/fonts/truetype/dejavu", r"C:\Windows\Fonts"]:
        for name in ("DejaVuSans.ttf", "segoeui.ttf", "arial.ttf"):
            path = os.path.join(directory, name)
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    continue
    return ImageFont.load_default(size)


if __name__ == "__main__":
    # Visual self-check sheet: every icon at 4x scale, labelled.
    cases = [
        (0, "ясно"), (2, "небольшая облачность"), (3, "облачно"), (45, "туман"),
        (51, "морось"), (61, "дождь"), (80, "ливни"), (71, "снег"),
        (95, "гроза"), (-1, "нет данных"),
    ]
    cols, cell, pad = 5, 240, 20
    rows = (len(cases) + cols - 1) // cols
    img = Image.new("RGB", (cols * cell + pad, rows * (cell + 46) + pad), (10, 84, 95))
    d = ImageDraw.Draw(img)
    f = _font(20)
    for i, (code, label) in enumerate(cases):
        cx = pad + (i % cols) * cell
        cy = pad + (i // cols) * (cell + 46)
        d.rounded_rectangle([cx, cy, cx + cell - 10, cy + cell - 10], radius=18,
                            fill=(16, 104, 116))
        draw_weather_icon(d, (cx + 55, cy + 30, 120), code)
        d.text((cx + 12, cy + cell - 2), f"{code}: {label}", font=f, fill=(226, 236, 238))
    out = os.path.abspath("icon_sheet.png")
    img.save(out, "PNG")
    print("saved:", out, img.size)
