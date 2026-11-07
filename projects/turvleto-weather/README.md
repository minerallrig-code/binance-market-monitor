# Turvleto — Daily Weather Telegram Publisher

Отдельный подпроект для ежедневной публикации погодного видео Нячанга в Telegram-канал `@chat100turvietnam`.

Планируемая реализация: GitHub Actions, запуск ежедневно в 08:00 по времени Вьетнама (01:00 UTC), получение прогноза через Open-Meteo, генерация вертикального видео 9:16 и отправка через Telegram Bot API.

Секрет GitHub Actions: `TELEGRAM_BOT_TOKEN`. Канал уже указан в workflow: `@chat100turvietnam`.


## Настройка публикации

1. В GitHub открой **Settings → Secrets and variables → Actions** этого репозитория.
2. Создай секрет:
   - `TELEGRAM_BOT_TOKEN` — токен бота из BotFather (не публикуй его в коде).
3. Убедись, что бот `@Mirtour_bot` — администратор канала и ему разрешена публикация сообщений.
4. Открой **Actions → Daily Nha Trang Weather Video → Run workflow** для первого ручного запуска.

Далее workflow запускается ежедневно в 08:00 по времени Вьетнама. Видео создаётся в формате 1080×1920, длительность 12 секунд. Погода берётся из Open-Meteo.

## Файлы

- `weather_post.py` — получение погоды, генерация MP4 и отправка в Telegram.
- `requirements.txt` — зависимости Python.
- `.github/workflows/turvleto-daily-weather.yml` — ежедневное расписание и запуск.
