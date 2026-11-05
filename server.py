#!/usr/bin/env python3
"""Локальный сервис скачивания видео через yt-dlp (видео+аудио склеиваются в mp4)."""
import json, os, re, shutil, subprocess, threading, time, uuid
import urllib.request, hashlib
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

HOST = "localhost"
PORT = 8765
DL_DIR = os.path.expanduser("~/Downloads")
YTDLP = next((p for p in (shutil.which("yt-dlp"), "/opt/homebrew/bin/yt-dlp", "/usr/local/bin/yt-dlp") if p), None)
ENV = dict(os.environ, PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
FORMATS = {"best": "bv*+ba/b", "lite": "bv*[height<=480]+ba/b"}
DEFAULTS = {"max_concurrent": 2, "add_stream_tag": True, "save_dir": DL_DIR}
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
JOBS = {}     # id -> job (вся история + очередь)
QUEUE = []    # FIFO ожидающих
LOCK = threading.Lock()
ACTIVE = {"n": 0}
HIST_CAP = 200


def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            s = json.load(f)
        return {**DEFAULTS, **{k: int(v) for k, v in s.items() if k in DEFAULTS}}
    except Exception:
        return dict(DEFAULTS)


def save_settings():
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(SETTINGS, f)
    except Exception:
        pass


SETTINGS = load_settings()


def cors(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")


def send_json(h, code, obj):
    b = json.dumps(obj, ensure_ascii=False).encode()
    h.send_response(code)
    cors(h)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(b)))
    h.end_headers()
    h.wfile.write(b)


def upgrade_to_master(url):
    """Если дали media_N.m3u8 (видео без аудио) — пробуем заменить на master.m3u8, где есть звук."""
    m = re.search(r"media_\d+\.m3u8", url)
    if not m:
        return url
    cand = url[:m.start()] + "master.m3u8"
    try:
        req = urllib.request.Request(cand, method="HEAD")
        with urllib.request.urlopen(req, timeout=6) as r:
            if r.status == 200:
                return cand
    except Exception:
        pass
    return url


def probe(path):
    """Возвращает список дорожек файла (ffprobe). Работает из-под сервиса — у него есть доступ к Downloads."""
    ff = next((p for p in (shutil.which("ffprobe"), "/usr/local/bin/ffprobe", "/opt/homebrew/bin/ffprobe") if p), None)
    if not ff:
        return {"streams": None, "error": "ffprobe не найден"}
    try:
        out = subprocess.run([ff, "-v", "error", "-of", "json", "-show_entries",
                              "stream=codec_type,codec_name,width,height",
                              "-show_entries", "format=duration", path],
                             capture_output=True, text=True, timeout=60, env=ENV)
        if out.returncode != 0:
            return {"streams": None, "error": (out.stderr or "ffprobe failed").strip()[:200]}
        data = json.loads(out.stdout)
        streams = [{"type": s.get("codec_type"), "codec": s.get("codec_name"),
                   "w": s.get("width"), "h": s.get("height")} for s in data.get("streams", [])]
        return {"streams": streams, "duration": data.get("format", {}).get("duration")}
    except Exception as e:
        return {"streams": None, "error": str(e)}


def safe_name(n):
    """Заголовок страницы -> безопасное имя файла (без спецсимволов, ~180 символов)."""
    s = re.sub(r"[/\\:*?\"<>|%\x00-\x1f]", " ", (n or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:180].strip() or None


def check_dir(p):
    """Нормализует путь к папке: разворачивает ~, требует абсолютный путь без '..'."""
    p = (p or "").strip()
    if not p:
        return None
    p = os.path.expanduser(p)
    if not os.path.isabs(p) or ".." in p.split(os.sep):
        return None
    return p


def out_tpl(url, name=None, out_dir=None):
    """Шаблон имени файла. Тег стрима добавляется, пока включён add_stream_tag."""
    m = re.search(r"([0-9a-f]{8})", url)
    tag = m.group(1) if m else hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    out_dir = out_dir or DL_DIR
    if name:
        base = name
        if SETTINGS.get("add_stream_tag", True):
            base = name + "." + tag
        return os.path.join(out_dir, base + ".%(ext)s")
    return os.path.join(out_dir, "%(title).50s." + tag + ".%(ext)s")


def worker(jid):
    job = JOBS[jid]
    url, fmt, name = job["url"], job["fmt"], job["name"]
    try:
        job["state"] = "downloading"
        job["started"] = time.time()
        job["percent"] = 0.0
        args = [YTDLP, "-f", fmt, "--merge-output-format", "mp4", "--newline",
                "--embed-metadata", "--no-playlist", "--no-update",
                "-o", out_tpl(url, name, job.get("dir")), url]
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, env=ENV)
        for line in p.stdout:
            line = line.strip()
            job["last"] = line[-120:]
            job["tail"] = (job.get("tail", "") + line[-300:] + "\n")[-3000:]
            m = re.search(r"(?:\[download\]\s+|^P\s*)(\d+(?:\.\d+)?)%", line)
            if m:
                job["percent"] = float(m.group(1))
            md = re.search(r"\[download\] Destination: (.+)$", line)
            if md and not job.get("filename"):
                job["filename"] = md.group(1).strip('" ')
            me = re.search(r"\[download\] (\S+) has already been downloaded", line)
            if me and not job.get("filename"):
                job["filename"] = me.group(1)
            mm = re.search(r"\[Merger\] Merging formats into \"(.+?)\"", line)
            if mm:
                job["filename"] = mm.group(1)
            if line.startswith("ERROR"):
                job["error"] = line
        p.wait()
        if p.returncode == 0 and job.get("filename"):
            job["state"] = "done"
            job["streams"] = probe(job["filename"])
        else:
            job["state"] = "error"
            job["error"] = job.get("error") or "yt-dlp завершился с кодом %s" % p.returncode
    except Exception as e:
        job["state"], job["error"] = "error", str(e)
    finally:
        job["finished"] = time.time()
        with LOCK:
            ACTIVE["n"] -= 1
            schedule_locked()
            evict_history_locked()


def schedule_locked():
    """Запускает из очереди столько задач, сколько свободных слотов (≤ max_concurrent)."""
    while ACTIVE["n"] < SETTINGS.get("max_concurrent", 2) and QUEUE:
        jid = QUEUE.pop(0)
        ACTIVE["n"] += 1
        threading.Thread(target=worker, args=(jid,), daemon=True).start()


def evict_history_locked():
    """Держим историю в разумных пределах (см. HIST_CAP)."""
    finished = [j for j in JOBS.values() if j["state"] in ("done", "error")]
    if len(finished) <= HIST_CAP:
        return
    finished.sort(key=lambda j: j.get("finished") or 0)
    for j in finished[: len(finished) - HIST_CAP]:
        JOBS.pop(j["id"], None)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_OPTIONS(self):
        self.send_response(204)
        cors(self)
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return send_json(self, 200, {"ok": True, "name": "video-saver",
                                         "ytdlp": bool(YTDLP), "active": ACTIVE["n"]})
        if u.path == "/status":
            jid = (u.query or "").split("=")[-1]
            return send_json(self, 200, JOBS.get(jid) or {"state": "unknown"})
        if u.path == "/probe":
            path = unquote((u.query or "").split("=")[-1])
            if not path.startswith(DL_DIR):
                return send_json(self, 400, {"error": "можно проверять только файлы из ~/Downloads"})
            return send_json(self, 200, probe(path) or {"streams": None, "error": "файл не найден"})
        if u.path == "/jobs":
            with LOCK:
                items = [dict(j) for j in JOBS.values()]
            items.sort(key=lambda j: j.get("added", 0))
            return send_json(self, 200, {"jobs": items, "active": ACTIVE["n"],
                                         "queued": len(QUEUE), "settings": dict(SETTINGS)})
        if u.path == "/settings":
            return send_json(self, 200, dict(SETTINGS))
        send_json(self, 404, {"error": "нет такого пути"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/remove":
            try:
                data = self._body()
            except Exception:
                return send_json(self, 400, {"error": "JSON не прочитан"})
            path = (data.get("path") or "")
            if not path.startswith(DL_DIR) or not os.path.isfile(path):
                return send_json(self, 400, {"error": "можно удалять только файлы из ~/Downloads"})
            try:
                os.remove(path)
            except Exception as e:
                return send_json(self, 500, {"error": str(e)})
            return send_json(self, 200, {"ok": True, "removed": path})
        if u.path == "/clear":
            with LOCK:
                removed = [j for j in JOBS.values() if j["state"] in ("done", "error")]
                for j in removed:
                    JOBS.pop(j["id"], None)
            return send_json(self, 200, {"removed": len(removed)})
        if u.path == "/settings":
            try:
                data = self._body()
            except Exception:
                return send_json(self, 400, {"error": "JSON не прочитан"})
            keys = ("max_concurrent", "add_stream_tag", "save_dir")
            with LOCK:
                for k in keys:
                    if k in data:
                        if k == "max_concurrent":
                            SETTINGS[k] = max(1, min(int(data[k]), 5))
                        elif k == "add_stream_tag":
                            SETTINGS[k] = bool(data[k])
                        elif k == "save_dir":
                            d = check_dir(str(data[k]))
                            if not d:
                                return send_json(self, 400, {"error": "Некорректный путь"})
                            SETTINGS[k] = d
                            try:
                                os.makedirs(d, exist_ok=True)
                            except Exception as e:
                                return send_json(self, 400, {"error": "Папка недоступна: %s" % e})
                save_settings()
                schedule_locked()
            return send_json(self, 200, dict(SETTINGS))
        if u.path != "/download":
            return send_json(self, 404, {"error": "нет такого пути"})
        try:
            data = self._body()
        except Exception:
            return send_json(self, 400, {"error": "JSON не прочитан"})
        url = (data.get("url") or "").strip()
        url = upgrade_to_master(url)
        fmt = FORMATS.get(data.get("format"), FORMATS["best"])
        if not re.match(r"^https?://", url):
            return send_json(self, 400, {"error": "Ссылка должна начинаться с http(s)://"})
        name = safe_name(data.get("name"))
        out_dir = check_dir(data.get("save_dir")) or SETTINGS.get("save_dir") or DL_DIR
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            return send_json(self, 400, {"error": "Папка недоступна: %s" % e})
        jid = uuid.uuid4().hex[:10]
        job = {"id": jid, "url": url, "fmt": fmt, "name": name, "state": "queued",
               "percent": 0.0, "filename": None, "error": None, "last": "", "tail": "",
               "added": time.time(), "started": None, "finished": None, "dir": out_dir}
        with LOCK:
            if sum(1 for j in JOBS.values() if j["state"] in ("queued", "downloading")) >= 50:
                return send_json(self, 429, {"error": "Слишком много загрузок в очереди"})
            JOBS[jid] = job
            QUEUE.append(jid)
            schedule_locked()
        send_json(self, 200, {"ok": True, "id": jid, "url": url, "state": job["state"]})


if __name__ == "__main__":
    if not YTDLP:
        raise SystemExit("yt-dlp не найден — установите: brew install yt-dlp")
    print("video-saver слушает http://%s:%s (yt-dlp: %s)" % (HOST, PORT, YTDLP), flush=True)
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
