import os
import math
import subprocess
import tempfile
import re
import json
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



CAMERA_PAGE = "https://nhatrang.live/ru/kamery/"
CAMERA_SECONDS = 4


def get_camera_ids():
    response = requests.get(CAMERA_PAGE, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()

    # The webcam page links to YouTube channels; it does not expose /embed/ IDs
    # in its server-rendered HTML. Resolve each channel's current live stream
    # through yt-dlp instead of searching only for iframe embed URLs.
    channel_pattern = (
        r"""https?://(?:www\.)?youtube\.com/"""
        r"""(?:@[\w.-]+|channel/[\w-]+|c/[\w.-]+|user/[\w.-]+)"""
    )
    channels = []
    for channel_url in re.findall(channel_pattern, response.text):
        channel_url = channel_url.rstrip("/")
        if channel_url not in channels:
            channels.append(channel_url)

    if not channels:
        # Page content can be rendered by its CMS with relative/protocol-relative links.
        for handle in re.findall(r"""(?:youtube\.com/)(@[\w.-]+)""", response.text):
            channel_url = "https://www.youtube.com/" + handle
            if channel_url not in channels:
                channels.append(channel_url)

    found = []
    for channel_url in channels:
        try:
            result = subprocess.run(
                ["yt-dlp", "--flat-playlist", "--dump-single-json",
                 channel_url + "/streams"],
                check=True, capture_output=True, text=True, timeout=75,
            )
            playlist = json.loads(result.stdout)
            entries = playlist.get("entries") or []
            live_entries = [
                entry for entry in entries
                if entry and (
                    entry.get("is_live") is True
                    or entry.get("live_status") == "is_live"
                )
            ]
            candidates = live_entries or [
                entry for entry in entries
                if entry and entry.get("id")
                and entry.get("live_status") not in ("was_live", "not_live")
            ]
            for entry in candidates:
                video_id = entry.get("id")
                if video_id and video_id not in found:
                    found.append(video_id)
                if len(found) == 2:
                    return found
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                json.JSONDecodeError) as error:
            print(f"Could not resolve live stream from {channel_url}: {error}")

    if not found:
        raise RuntimeError(
            "No live YouTube streams could be resolved from the webcam page. "
            "The camera page may have changed or the channels may be offline."
        )
    return found[:2]

def record_camera_clip(video_id, output_path):
    page_url = f"https://www.youtube.com/watch?v={video_id}"
    result = subprocess.run(
        ["yt-dlp", "--no-warnings", "-f", "best[height<=720]/best", "-g", page_url],
        check=True, capture_output=True, text=True, timeout=60,
    )
    stream_url = result.stdout.strip().splitlines()[0]
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1,"
        "drawbox=x=35:y=55:w=1010:h=150:color=0x063f46@0.72:t=fill,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        "text='TUR V LETO  |  NHA TRANG':fontcolor=white:fontsize=42:x=65:y=105"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", stream_url,
         "-t", str(CAMERA_SECONDS), "-vf", vf, "-an", "-r", "25",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
         "-pix_fmt", "yuv420p", output_path],
        check=True, timeout=90,
    )


def make_video(png_path, mp4_path):
    with tempfile.TemporaryDirectory() as tmp:
        camera_ids = get_camera_ids()
        clips = []
        for index, video_id in enumerate(camera_ids):
            clip_path = os.path.join(tmp, f"camera_{index}.mp4")
            record_camera_clip(video_id, clip_path)
            clips.append(clip_path)

        card_path = os.path.join(tmp, "weather_card.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", png_path,
             "-t", "5", "-vf",
             "scale=1080:1920,zoompan=z='min(zoom+0.00035,1.035)':d=1:s=1080x1920:fps=25,format=yuv420p",
             "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-movflags", "+faststart", card_path],
            check=True, timeout=60,
        )
        concat_file = os.path.join(tmp, "concat.txt")
        ordered = clips + [clips[0], card_path]
        with open(concat_file, "w", encoding="utf-8") as handle:
            for path in ordered:
                handle.write(f"file '{path}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", concat_file, "-c", "copy", "-movflags", "+faststart", mp4_path],
            check=True, timeout=60,
        )


def send_video(video_path, weather):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    thread_id = os.environ.get("TELEGRAM_MESSAGE_THREAD_ID")
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
            data={
                "chat_id": chat_id,
                "caption": caption,
                **({"message_thread_id": thread_id} if thread_id else {}),
            },
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
    png_path = os.path.abspath("weather.png")
    mp4_path = os.path.abspath("weather.mp4")
    make_card(weather, png_path)
    make_video(png_path, mp4_path)
    print(f"Video generated: {mp4_path}")
    send_video(mp4_path, weather)


if __name__ == "__main__":
    main()
