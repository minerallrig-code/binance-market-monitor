import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
CITIES = [
    ("НЯЧАНГ", 12.2388, 109.1967),
    ("МУЙНЕ", 10.9333, 108.2833),
    ("ФУКУОК", 10.2899, 103.9840),
    ("ДАНАНГ", 16.0544, 108.2022),
]


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


def get_weather(name, lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "Asia/Ho_Chi_Minh",
        "forecast_days": 1,
    }
    response = requests.get(url, params=params, timeout=25)
    response.raise_for_status()
    data = response.json()
    current, daily = data["current"], data["daily"]
    return {
        "name": name,
        "temp": round(current["temperature_2m"]),
        "feels": round(current["apparent_temperature"]),
        "humidity": round(current["relative_humidity_2m"]),
        "wind": round(current["wind_speed_10m"]),
        "condition": weather_description(current["weather_code"]),
        "high": round(daily["temperature_2m_max"][0]),
        "low": round(daily["temperature_2m_min"][0]),
        "rain": daily["precipitation_probability_max"][0],
    }


def build_message(weather_list):
    now = datetime.now(TZ)
    lines = [
        f"☀️ ПОГОДА ВО ВЬЕТНАМЕ | {now.strftime('%d.%m.%Y')}",
        "",
        "Планируете отдых или экскурсию? Вот что сегодня по погоде в популярных курортных городах:",
        "",
    ]
    for w in weather_list:
        rain = "—" if w["rain"] is None else f'{w["rain"]}%'
        lines.extend([
            f'📍 {w["name"]} — {w["temp"]}°C, {w["condition"]}',
            f'   Днём {w["high"]}° / ночью {w["low"]}° · дождь {rain}',
            "",
        ])
    lines.extend([
        "Выбирайте маршрут под погоду и отдыхайте с удовольствием! 🌴",
        "",
        "ТУР В ЛЕТО | Экскурсии и отдых во Вьетнаме",
        "🌐 turvleto.com",
        "",
        "#ТурВЛето #ПогодаВоВьетнаме #Нячанг #Муйне #Фукуок #Дананг #Вьетнам",
    ])
    return "\n".join(lines)


def telegram_post(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": message,
    }
    thread_id = os.environ.get("TELEGRAM_MESSAGE_THREAD_ID")
    if thread_id:
        data["message_thread_id"] = thread_id
    response = requests.post(url, data=data, timeout=30)
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f'Telegram API error: {result.get("description", "unknown error")}')
    print("Daily weather text sent; message_id =", result["result"]["message_id"])


def main():
    weather = [get_weather(*city) for city in CITIES]
    message = build_message(weather)
    print(message)
    telegram_post(message)


if __name__ == "__main__":
    main()
