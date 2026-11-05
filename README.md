# Скачать видео со звуком · Video Saver with Sound

> Расширение для Chrome/Vivaldi + локальный сервис (macOS), которые находят HLS-потоки
> страницы и скачивают видео **вместе с аудио** через `yt-dlp`.
> A Chrome/Vivaldi extension plus a tiny local macOS service that finds the page's HLS
> streams and downloads video **with audio** via `yt-dlp`.

[EN](#english-readme)

---

## Что это / What it does

- Расширение **само находит** потоки на странице (перехватывает `.m3u8`, которые грузит плеер,
  даже через JS) — не нужно копировать ссылки из кода страницы.
- Локальный Python-сервис качает через `yt-dlp`, берёт видео **и** аудио-дорожки отдельно
  и склеивает их в один MP4. Решает типовую проблему «скачал, а звука нет» (DASH/HLS).
- Попап показывает **очередь и историю** загрузок (живёт на сервере, переживает навигацию),
  настраиваются: число одновременных загрузок, добавление тега стрима к имени, папка сохранения.

## Требования / Requirements

- macOS (расширение шлёт запросы на `localhost:8765`, где крутится локальный сервис)
- Python 3.9+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (`brew install yt-dlp`)
- [ffmpeg](https://ffmpeg.org/) для склейки видео и аудио (`brew install ffmpeg`)
- Chrome / Vivaldi / любой Chromium-браузер

## Установка / Install

### 1. Сервис (один раз) · Service (once)

```bash
git clone https://github.com/AzamatMurra/video-saver-browser.git
cd video-saver-browser
chmod +x install.sh
./install.sh
```

Проверка: `curl http://localhost:8765/` → `{"ok":true,...}`

### 2. Расширение (один раз) · Extension (once)

1. Тот же клон: сервис уже установлен, папка расширения — `extension/`.
2. Откройте `chrome://extensions` (в Vivaldi — `vivaldi://extensions`).
3. Включите «Режим разработчика» → «Загрузить распакованное расширение» → папка `extension/`.
4. Закрепите иконку на панели (опционально).

## Использование / Usage

1. Откройте страницу с видео, дайте плееру начать проигрывание (тогда `.m3u8` будут пойманы).
2. Клик по иконке → выберите поток (`master.m3u8` обычно с аудио), качество, при желании
   поменяйте имя файла и папку → **«Добавить в очередь»**.
3. Загрузки идут по очереди (лимит настраивается), статусы и прогресс видны в попапе,
   список — это же история, есть кнопка «Очистить историю».
4. Готовый файл появляется в выбранной папке (по умолчанию `~/Downloads`).

## Настройки / Settings

| Параметр | Что делает |
|---|---|
| Одновременных загрузок | лимит параллельных задач (1–5) |
| «Добавлять тег стрима к имени файла» | при выключении в имени нет тега (осторожно: одинаковые заголовки перезапишутся) |
| Папка для файлов | каталог сохранения (создаётся автоматически, запоминается) |

## Полезное / Useful

- Лог сервиса: `~/.local/share/video-saver/server.log`
- Перезапуск: `launchctl kickstart -k gui/$(id -u)/com.user.video-saver`
- Отключить автозапуск: `launchctl bootout gui/$(id -u)/com.user.video-saver`
- Ограничение: расширение завязано на локальный сервис на этом Mac — оно не «облачное»,
  скачивание идёт на компьютер, где установлен сервис.

## Внутренности / Internals

- Как всё устроено — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- История версий — [docs/CHANGELOG.md](docs/CHANGELOG.md)

## Лицензия / License

[MIT](LICENSE)

---

## English readme

A browser extension + local service that downloads **video with sound** from pages
where the player loads HLS (`.m3u8`) streams via JS.

- The extension finds real streams on the page (it doesn't send the address-bar URL to yt-dlp).
- The local Python service runs `yt-dlp -f "bv*+ba/b" --merge-output-format mp4`,
  merging separate video and audio tracks into one MP4 (needs ffmpeg).
- The popup shows a persistent **download queue/history** (server-side, survives navigation)
  and settings: parallel download limit, stream-tag in the filename (can be disabled),
  and a destination folder chooser (auto-created and remembered).

Requirements: macOS, Python 3.9+, `yt-dlp`, `ffmpeg`, Chromium-based browser.

Install: clone → `./install.sh` (registers the launchd service) → load `extension/`
from `chrome://extensions` (Developer mode). Then open a video page, let the player start,
click the icon, pick the stream and quality, and add to queue.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/CHANGELOG.md](docs/CHANGELOG.md).

License: MIT.
