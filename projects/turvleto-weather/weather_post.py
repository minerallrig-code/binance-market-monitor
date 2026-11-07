import os
import math
import subprocess
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

LAT, LON = 12.2388, 109.1967
CITY = "НЯЧАНГ"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
WIDTH, HEIGHT = 1080, 1920


def weather_description(code):
    if code == 0:
        return "ЯСНОЕ НЕБО"
    if code in (1, 2):
        return "НЕБОЛЬШАЯ ОБЛАЧНОСТЬ"
    if code == 3:
        return "ОБЛАЧНО"
    if code in (45, 48):
        return "ТУМАН"
    if code in (51, 53, 55, 56, 57):
        return "МОРОСЬ"
    if code in (61, 63, 65, 66, 67):
        return "ДОЖДЬ"
    if code in (71, 73, 75, 77):
        return "СНЕГ"
    if code in (80, 81, 82):
        return "ЛИВЕНЬ"
    if code in (95, 96, 99):
        return "ГРОЗА"
    return "ПОГОДА СЕГОДНЯ"


def get_weather():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "Asia/Ho_Chi_Minh",
        "forecast_days": 1,
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    current = data["current"]
    daily = data["daily"]
    return {
        "temp": round(current["temperature_2m"]),
        "feels": round(current["apparent_temperature"]),
        "humidity": round(current["relative_humidity_2m"]),
        "wind": round(current["wind_speed_10m"]),
        "code": current["weather_code"],
        "high": round(daily["temperature_2m_max"][0]),
        "low": round(daily["temperature_2m_min"][0]),
        "rain": daily["precipitation_probability_max"][0],
    }


def load_font(size, bold=False):
    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(path, size)


def make_card(weather, output_png):
    # Deep teal background with a warm gold glow.
    image = Image.new("RGB", (WIDTH, HEIGHT), (5, 42, 52))
    pixels = image.load()
    for y in range(HEIGHT):
        blend = y / HEIGHT
        base = (int(5 + 4 * blend), int(42 - 12 * blend), int(52 - 8 * blend))
        for x in range(WIDTH):
            dx, dy = (x - 850) / 850, (y - 400) / 850
            glow = max(0, 1 - math.sqrt(dx * dx + dy * dy)) * 0.23
            pixels[x, y] = (
                min(255, int(base[0] + 190 * glow)),
                min(255, int(base[1] + 145 * glow)),
                min(255, int(base[2] + 45 * glow)),
            )

    draw = ImageDraw.Draw(image)
    white = (245, 248, 242)
    gold = (239, 190, 91)
    muted = (177, 211, 207)

    draw.rounded_rectangle((64, 70, 1016, 330), radius=42, outline=(239, 190, 91), width=3)
    draw.text((105, 110), "ТУР В ЛЕТО", font=load_font(76, True), fill=white)
    draw.text((110, 220), "ПОГОДА ВО ВЬЕТНАМЕ", font=load_font(34, True), fill=gold)

    now = datetime.now(TZ)
    date_text = now.strftime("%d.%m.%Y")
    draw.text((110, 420), CITY, font=load_font(54, True), fill=gold)
    draw.text((110, 505), date_text, font=load_font(32), fill=muted)

    draw.text((90, 650), f'{weather["temp"]}°', font=load_font(300, True), fill=white, stroke_width=2, stroke_fill=(5, 42, 52))
    draw.text((115, 1010), weather_description(weather["code"]), font=load_font(43, True), fill=gold)
    draw.text((115, 1090), f'Ощущается как {weather["feels"]}°', font=load_font(34), fill=muted)

    draw.rounded_rectangle((75, 1240, 1005, 1580), radius=38, fill=(8, 63, 70), outline=(72, 126, 122), width=2)
    rows = [
        (f'Днём до {weather["high"]}°', f'Ночью {weather["low"]}°'),
        (f'Влажность {weather["humidity"]}%', f'Ветер {weather["wind"]} км/ч'),
        (f'Вероятность дождя {weather["rain"] if weather["rain"] is not None else "—"}%', "Хорошего отдыха!"),
    ]
    y = 1290
    for left, right in rows:
        draw.text((120, y), left, font=load_font(29, True), fill=white)
        draw.text((590, y), right, font=load_font(27), fill=muted)
        y += 92

    draw.text((110, 1690), "Экскурсии и отдых в Нячанге", font=load_font(34, True), fill=white)
    draw.text((110, 1760), "turvleto.com", font=load_font(30), fill=gold)
    image.save(output_png, quality=95)


def make_video(png_path, mp4_path):
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", png_path,
        "-t", "12", "-vf",
        "scale=1080:1920,zoompan=z='min(zoom+0.00035,1.035)':d=1:s=1080x1920:fps=25,format=yuv420p",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-movflags", "+faststart", mp4_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def send_video(video_path, weather):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "@chat100turvietnam")
    caption = (
        f'☀️ Погода в Нячанге сегодня: {weather["temp"]}°C, '
        f'{weather_description(weather["code"]).lower()}\n'
        f'Днём до {weather["high"]}°, ночью {weather["low"]}°.\n'
        'ТУР В ЛЕТО — экскурсии и отдых во Вьетнаме'
    )
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    with open(video_path, "rb") as video:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"video": ("nha-trang-weather.mp4", video, "video/mp4")},
            timeout=120,
        )
    try:
        result = response.json()
    except ValueError:
        result = {"ok": False, "description": response.text[:500]}

    if response.status_code >= 400 or not result.get("ok"):
        # Report Telegram's explanation without ever printing the bot token.
        description = result.get("description", "Unknown Telegram API error")
        error_code = result.get("error_code", response.status_code)
        raise RuntimeError(
            f"Telegram API error {error_code}: {description}. "
            f"Check that the bot is an administrator of {chat_id} "
            "and has permission to post messages."
        )


def main():
    weather = get_weather()
    with tempfile.TemporaryDirectory() as tmp:
        png_path = os.path.join(tmp, "weather.png")
        mp4_path = os.path.join(tmp, "weather.mp4")
        make_card(weather, png_path)
        make_video(png_path, mp4_path)
        send_video(mp4_path, weather)


if __name__ == "__main__":
    main()
