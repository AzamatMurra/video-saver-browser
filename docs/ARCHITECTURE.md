# Архитектура / Architecture

## Русский

Проект состоит из двух частей, которые общаются по HTTP на `localhost:8765`:

```
[Страница с видео]  ──(перехват сети)──▶  Расширение (background.js)
      │                                         │
      │  content.js ищет .m3u8 в DOM/перформансе │
      ▼                                         ▼
   Попап (popup.js) ◀──streams──  сервис-мост через runtime.sendMessage
      │  ▶ POST /download {url, format, name, save_dir}
      ▼
Локальный Python-сервис (server.py)
   - очередь заданий (QUEUE + ACTIVE до max_concurrent)
   - вызов yt-dlp -f "bv*+ba/b" --merge-output-format mp4
   - парсинг прогресса и имени файла из stdout
   - настройки в settings.json (макс. параллельные, тег стрима, папка)
      │
      ▼
  MP4 (видео + аудио) в выбранной папке (по умолчанию ~/Downloads)
```

### Ключевые решения
1. **Расширение не передаёт адресную строку** в yt-dlp: многие платформы (VOD-плееры,
   образовательные сайты) не поддерживаются yt-dlp напрямую. Вместо этого расширение
   само находит реальные потоки HLS: `background.js` слушает webRequest вкладки
   и запоминает `.m3u8` (в том числе те, что грузятся плеером через JS), а `content.js`
   дополнительно сканирует DOM и `performance.getEntriesByType("resource")`.
2. **Видео + аудио отдельно:** `-f "bv*+ba/b"` — yt-dlp берёт лучшую видео- и аудио-дорожки
   и склеивает их в один MP4 (нужен `ffmpeg`). Это решает проблему «скачал, а звука нет»,
   которая у сайтов с DASH/HLS — типовая.
3. **Очередь живёт на сервере**, а не в расширении: она переживает перезагрузки вкладок,
   навигацию и даже закрытый попап. `/jobs` отдаёт и активные задания, и историю.
4. **Имя файла = заголовок страницы** (поле в попапе), с очисткой спецсимволов
   и необязательным тегом стрима (короткий идентификатор из URL) для защиты от перезаписи.
5. **Прогресс:** у yt-dlp флаг `--print` подавляет вывод прогресса — поэтому сервис читает
   `--newline` вывод и извлекает `NN%` по регулярному выражению.

### Эндпоинты сервиса
| Метод | Путь | Назначение |
|---|---|---|
| GET  | `/`         | health (`{"ok": true, ...}`) |
| GET  | `/status?id=`| состояние одного задания |
| GET  | `/jobs`     | очередь + история + настройки |
| GET  | `/settings` | текущие настройки |
| GET  | `/probe?path=` | кодеки файла через ffprobe (проверка звука) |
| POST | `/download` | поставить задание в очередь `{url, format, name, save_dir}` |
| POST | `/settings`  | сохранить настройки (частично, по ключам) |
| POST | `/clear`    | очистить историю (завершённые; активные не трогаются) |
| POST | `/remove`   | удалить готовый файл (только из папки сохранения) |

## English

The project has two parts talking over HTTP on `localhost:8765`:

1. **Browser extension** (Manifest V3): `background.js` intercepts the tab's web requests
   and remembers every `.m3u8` playlist (works even when the player loads HLS via JS);
   `content.js` additionally scans the DOM and `performance` resource entries.
   The popup (`popup.js`) lists found streams, lets the user pick quality and destination
   folder, and dispatches the job to the service.
2. **Local Python service** (`server.py`): keeps a persistent download queue
   (up to `max_concurrent` jobs in parallel), runs `yt-dlp -f "bv*+ba/b"
   --merge-output-format mp4` (video + audio merged into one MP4 — needs ffmpeg),
   parses progress from stdout, and stores settings in `settings.json`.

Key decisions:
- Never send the address-bar URL to yt-dlp — find real HLS streams on the page instead.
- The queue lives server-side, so it survives navigation, tab reloads and closed popups.
- Filename defaults to the page title with optional stream tag (dedupe safeguard).
- `--print` suppresses yt-dlp progress output — the service parses `NN%` from `--newline` output.
