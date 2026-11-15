"""Production-ready renderer for the Turvleto weather card.

Not yet wired into `weather_post.py` and not committed to GitHub.
`render_card()` takes exactly the list produced by the existing `get_weather()` calls,
so integration is a small change in the publishing step.

Contract:
    weather_list = [{"name": str, "temp": int, "feels": int, "condition": str,
                     "high": int, "low": int, "rain": int | None,
                     "code": int | None}, ...]   # "code" optional (WMO)
    path = render_card(weather_list, "card.png")

Card height adapts to the number of cities (4 -> 1350 px, 5 -> 1536 px), so adding a
destination needs no layout edits. Icons are vector primitives (see weather_icons.py),
not emoji: no emoji font is required on the runner, and the icon is derived from the
same WMO code as the text.
"""
from __future__ import annotations

import os
from datetime import date

from PIL import Image, ImageDraw, ImageFont

from weather_icons import draw_weather_icon, icon_code_for

W, MIN_H = 1080, 1350
BG_TOP = (6, 53, 63)
BG_BOTTOM = (11, 96, 108)
CARD = (10, 84, 95)
CARD_EDGE = (26, 122, 133)
BADGE = (16, 104, 116)
INK = (255, 255, 255)
MUTED = (176, 214, 219)
ACCENT = (255, 208, 102)

CARD_H, GAP, TOP = 190, 22, 240
FOOTER_BLOCK = 210

# Linux runners have DejaVu; Windows dev boxes have Segoe UI / Arial.
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", r"C:\Windows\Fonts", ""]
BOLD_NAMES = ["DejaVuSans-Bold.ttf", "seguisb.ttf", "arialbd.ttf", "segoeuib.ttf"]
REG_NAMES = ["DejaVuSans.ttf", "segoeui.ttf", "arial.ttf", "calibri.ttf"]

COUNT_PHRASES = {
    1: "одно направление",
    2: "два направления",
    3: "три направления",
    4: "четыре направления",
    5: "пять направлений",
    6: "шесть направлений",
    7: "семь направлений",
    8: "восемь направлений",
}


def _font(names, size):
    for directory in FONT_DIRS:
        for name in names:
            path = os.path.join(directory, name) if directory else name
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    continue
    return ImageFont.load_default(size)


def _gradient(height):
    img = Image.new("RGB", (W, height))
    d = ImageDraw.Draw(img)
    for y in range(height):
        t = y / (height - 1)
        d.line(
            [(0, y), (W, y)],
            fill=(
                round(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t),
                round(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t),
                round(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t),
            ),
        )
    return img


def _rain_text(value):
    return "—" if value is None else f"{value}%"


def _plain(text):
    """Drop emoji and symbol glyphs: Pillow has no emoji font on the runner."""
    return "".join(ch for ch in str(text) if ord(ch) < 0x2000).strip()


def render_card(weather_list, path="weather_card.png", day=None, title="ПОГОДА ВО ВЬЕТНАМЕ"):
    """Render the branded card and return the absolute path of the PNG."""
    if not weather_list:
        raise ValueError("weather_list is empty")

    n = len(weather_list)
    fy = TOP + n * (CARD_H + GAP) + 26
    height = max(MIN_H, fy + FOOTER_BLOCK)

    img = _gradient(height)
    d = ImageDraw.Draw(img)

    f_title = _font(BOLD_NAMES, 62)
    f_date = _font(REG_NAMES, 34)
    f_city = _font(BOLD_NAMES, 44)
    f_temp = _font(BOLD_NAMES, 76)
    f_body = _font(REG_NAMES, 30)
    f_detail = _font(REG_NAMES, 25)
    f_foot = _font(BOLD_NAMES, 34)
    f_site = _font(REG_NAMES, 28)
    f_tag = _font(REG_NAMES, 22)

    day = day or date.today()
    count_phrase = COUNT_PHRASES.get(n, f"{n} направлений")

    d.text((60, 58), title, font=f_title, fill=INK)
    d.text((60, 136), f"{day.strftime('%d.%m.%Y')}  ·  {count_phrase}",
           font=f_date, fill=MUTED)
    d.line([(60, 200), (W - 60, 200)], fill=ACCENT, width=4)

    for i, c in enumerate(weather_list):
        y0 = TOP + i * (CARD_H + GAP)
        d.rounded_rectangle([(50, y0), (W - 50, y0 + CARD_H)], radius=28,
                            fill=CARD, outline=CARD_EDGE, width=2)

        # icon badge, chosen from the WMO code (falls back to the Russian text)
        d.rounded_rectangle([(74, y0 + 45), (174, y0 + 145)], radius=24, fill=BADGE)
        code = c.get("code")
        draw_weather_icon(d, (85, y0 + 56, 78),
                          code if code is not None else icon_code_for(c.get("condition")))

        tx = 200
        d.text((tx, y0 + 26), str(c["name"]).upper(), font=f_city, fill=INK)
        d.text((tx, y0 + 86), _plain(c["condition"]), font=f_body, fill=MUTED)
        d.text((tx, y0 + 130),
               f"Днём +{c['high']}° · ночью +{c['low']}° · дождь {_rain_text(c['rain'])}",
               font=f_detail, fill=MUTED)

        temp = f"+{c['temp']}°"
        d.text((W - 100 - d.textlength(temp, font=f_temp), y0 + 30), temp,
               font=f_temp, fill=ACCENT)
        feels = f"ощущается как +{c['feels']}°"
        d.text((W - 100 - d.textlength(feels, font=f_detail), y0 + 126), feels,
               font=f_detail, fill=MUTED)

    d.line([(60, fy), (W - 60, fy)], fill=CARD_EDGE, width=2)
    d.text((60, fy + 32), "ТУР В ЛЕТО | Экскурсии и отдых во Вьетнаме", font=f_foot, fill=INK)
    d.text((60, fy + 84), "turvleto.com", font=f_site, fill=ACCENT)
    tags = "#ТурВЛето #ПогодаВоВьетнаме"
    d.text((W - 60 - d.textlength(tags, font=f_tag), fy + 92), tags, font=f_tag, fill=MUTED)

    full = os.path.abspath(path)
    img.save(full, "PNG")
    return full


if __name__ == "__main__":
    # Smoke test with PLACEHOLDER values (not API data, nothing is sent anywhere).
    demo = [
        {"name": "Нячанг", "temp": 29, "feels": 33, "condition": "небольшая облачность",
         "high": 31, "low": 24, "rain": 20, "code": 2},
        {"name": "Муйне", "temp": 28, "feels": 32, "condition": "дождь",
         "high": 30, "low": 23, "rain": 70, "code": 61},
        {"name": "Фукуок", "temp": 30, "feels": 35, "condition": "ясно",
         "high": 32, "low": 25, "rain": 0, "code": 0},
        {"name": "Дананг", "temp": 26, "feels": 28, "condition": "гроза",
         "high": 28, "low": 22, "rain": None, "code": 95},
        {"name": "Далат", "temp": 18, "feels": 19, "condition": "туман",
         "high": 21, "low": 14, "rain": 30, "code": 45},
    ]
    print("saved:", render_card(demo, "card_preview.png", day=date(2026, 11, 17)))
