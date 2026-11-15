import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from weather_card import render_card

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
CITIES = [
    ("НЯЧАНГ", 12.2388, 109.1967),
    ("МУЙНЕ", 10.9333, 108.2833),
    ("ФУКУОК", 10.2899, 103.9840),
    ("ДАНАНГ", 16.0544, 108.2022),
    ("ДАЛАТ", 11.9404, 108.4583),
]
API_URL = "https://api.open-meteo.com/v1/forecast"
RETRY_DELAYS = (2, 4, 8)
ATTEMPTS = 3
CARD_PATH = "weather_card.png"
CAPTION_LIMIT = 1024
# The post is the card alone: no caption is attached. Put text here to bring a
# caption back (1024 characters max) — e.g. hashtags, which only work in text.
PHOTO_CAPTION = ""


def weather_description(code):
    if code == 0:
        return "☀️ ясно"
    if code in (1, 2):
        return "🌤 небольшая облачность"
    if code == 3:
        return "☁️ облачно"
    if code in (45, 48):
        return "🌫 туман"
    if code in (51, 53, 55, 56, 57):
        return "🌦 морось"
    if code in (61, 63, 65, 66, 67):
        return "🌧 дождь"
    if code in (71, 73, 75, 77):
        return "❄️ снег"
    if code in (80, 81, 82):
        return "🌧 ливни"
    if code in (95, 96, 99):
        return "⛈ гроза"
    return "🌡 переменная погода"


def _backoff(attempt):
    return RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]


def fetch_forecast(params, city, attempts=ATTEMPTS):
    """GET Open-Meteo. Retries network errors and 5xx; a 4xx answer is not retried."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(API_URL, params=params, timeout=25)
            if response.status_code >= 500:
                raise requests.RequestException(f"Open-Meteo HTTP {response.status_code}")
            if response.status_code >= 400:
                raise RuntimeError(f"{city}: Open-Meteo rejected the request (HTTP {response.status_code})")
            return response.json()
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt == attempts:
                break
            delay = _backoff(attempt)
            print(f"{city}: attempt {attempt} failed ({error}); retry in {delay}s", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"{city}: Open-Meteo unavailable after {attempts} attempts: {last_error}")


def field(payload, city, section, key, index=None):
    """Read a required value and fail with a readable message instead of KeyError."""
    try:
        value = payload[section][key]
    except (KeyError, TypeError):
        raise RuntimeError(f"{city}: field {section}.{key} is missing in Open-Meteo response") from None
    if index is not None:
        if not isinstance(value, list) or len(value) <= index:
            raise RuntimeError(f"{city}: field {section}.{key} is empty in Open-Meteo response")
        value = value[index]
    if value is None:
        raise RuntimeError(f"{city}: field {section}.{key} is null in Open-Meteo response")
    return value


def optional_field(payload, section, key, index=None):
    """Same as field() but returns None: used for values the post can live without."""
    try:
        value = payload[section][key]
    except (KeyError, TypeError):
        return None
    if index is not None:
        if not isinstance(value, list) or len(value) <= index:
            return None
        value = value[index]
    return value


def get_weather(name, lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "Asia/Ho_Chi_Minh",
        "forecast_days": 1,
    }
    data = fetch_forecast(params, name)
    if not isinstance(data.get("current"), dict) or not isinstance(data.get("daily"), dict):
        raise RuntimeError(f"{name}: unexpected Open-Meteo response (no current/daily blocks)")

    code = field(data, name, "current", "weather_code")
    humidity = optional_field(data, "current", "relative_humidity_2m")
    wind = optional_field(data, "current", "wind_speed_10m")
    return {
        "name": name,
        "code": code,
        "temp": round(field(data, name, "current", "temperature_2m")),
        "feels": round(field(data, name, "current", "apparent_temperature")),
        "humidity": None if humidity is None else round(humidity),
        "wind": None if wind is None else round(wind),
        "condition": weather_description(code),
        "high": round(field(data, name, "daily", "temperature_2m_max", 0)),
        "low": round(field(data, name, "daily", "temperature_2m_min", 0)),
        "rain": optional_field(data, "daily", "precipitation_probability_max", 0),
    }


def collect_weather(cities=CITIES):
    """Fetch every city; return values plus per-city errors (never a silent partial post)."""
    weather, errors = [], []
    for name, lat, lon in cities:
        try:
            weather.append(get_weather(name, lat, lon))
        except Exception as error:  # noqa: BLE001 - reported, never published
            errors.append(f"{name}: {error}")
    return weather, errors


def build_message(weather_list):
    now = datetime.now(TZ)
    lines = [
        f"☀️ ПОГОДА ВО ВЬЕТНАМЕ | {now.strftime('%d.%m.%Y')}",
        "",
        "Планируете отдых или экскурсию? Вот что сегодня по погоде в популярных городах Вьетнама:",
        "",
    ]
    for w in weather_list:
        rain = "—" if w["rain"] is None else f'{w["rain"]}%'
        lines.extend([
            f'📍 {w["name"]} — {w["temp"]}°C (ощущается как {w["feels"]}°C), {w["condition"]}',
            f'   Днём {w["high"]}° / ночью {w["low"]}° · дождь {rain}',
            "",
        ])
    lines.extend([
        "Выбирайте маршрут под погоду и отдыхайте с удовольствием! 🌴",
        "",
        "ТУР В ЛЕТО | Экскурсии и отдых во Вьетнаме",
        "🌐 turvleto.com",
        "",
        "#ТурВЛето #ПогодаВоВьетнаме #Нячанг #Муйне #Фукуок #Дананг #Далат #Вьетнам",
    ])
    return "\n".join(lines)


def telegram_call(method, data, files=None, attempts=ATTEMPTS):
    """Call a Bot API method.

    Retried: transport failures, HTTP 429 and 5xx. Not retried: a 4xx answer or an
    ``ok: false`` reply — repeating a rejected message cannot help.
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/{method}"
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(url, data=data, files=files, timeout=60)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.RequestException(f"Telegram {method} HTTP {response.status_code}")
            try:
                result = response.json()
            except ValueError:
                raise requests.RequestException(f"Telegram {method} returned non-JSON body") from None
            if not result.get("ok"):
                raise RuntimeError(
                    f'Telegram {method} rejected: {result.get("description", "unknown error")}'
                )
            return result["result"]
        except requests.RequestException as error:
            last_error = error
            if attempt == attempts:
                break
            delay = _backoff(attempt)
            print(f"Telegram {method}: attempt {attempt} failed ({error}); retry in {delay}s", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"Telegram {method} unavailable after {attempts} attempts: {last_error}")


def send_post(message, image_path=None):
    """Publish exactly one message: the card, without a caption.

    The card carries all the numbers, the brand and the site, so a text post would
    duplicate it. The text is only a fallback for the case where Telegram refuses
    the photo.
    """
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    thread_id = os.environ.get("TELEGRAM_MESSAGE_THREAD_ID")

    if image_path:
        data = {"chat_id": chat_id}
        if thread_id:
            data["message_thread_id"] = thread_id
        caption = PHOTO_CAPTION.strip()
        if caption:
            data["caption"] = caption[:CAPTION_LIMIT]
        try:
            with open(image_path, "rb") as photo:
                result = telegram_call(
                    "sendPhoto", data,
                    files={"photo": (os.path.basename(image_path), photo, "image/png")},
                )
            print("Weather card sent; message_id =", result["message_id"])
            return
        except Exception as error:  # noqa: BLE001 - fall back, keep the post alive
            print(f"Photo post failed ({error}); falling back to text post", flush=True)

    data = {"chat_id": chat_id, "text": message}
    if thread_id:
        data["message_thread_id"] = thread_id
    result = telegram_call("sendMessage", data)
    print("Weather text sent; message_id =", result["message_id"])


def main():
    weather, errors = collect_weather()
    if errors:
        print("Publishing skipped: forecast is incomplete, a partial post is not allowed.")
        for line in errors:
            print("  error:", line)
        raise SystemExit(1)

    message = build_message(weather)
    print(message)
    print("message length:", len(message))

    image_path = None
    try:
        image_path = render_card(weather, CARD_PATH, day=datetime.now(TZ).date())
        print("weather card rendered:", image_path)
    except Exception as error:  # noqa: BLE001 - text post must still go out
        print(f"Card rendering failed ({error}); posting text only", flush=True)

    send_post(message, image_path)


if __name__ == "__main__":
    main()
