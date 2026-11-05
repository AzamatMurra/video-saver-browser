#!/bin/bash
# Установка и перезапуск сервиса video-saver из этого репозитория.
# Копирует код в ~/.local/share/video-saver и регистрирует launchd-агент (macOS).
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
DIR="$HOME/.local/share/video-saver"
AGENT="$HOME/Library/LaunchAgents/com.user.video-saver.plist"

mkdir -p "$DIR" "$HOME/Library/LaunchAgents"

# код проекта (без приватного: settings.json, server.log — их создаёт сам сервис)
cp -R "$SRC/extension" "$DIR/"
cp "$SRC/server.py" "$DIR/server.py"
[ -f "$SRC/gen_icons.py" ] && cp "$SRC/gen_icons.py" "$DIR/" || true

# шаблон launchd-агента: подставляем реальный путь пользователя
sed "s|__DIR__|$DIR|g" "$SRC/examples/com.user.video-saver.plist" > "$AGENT"

launchctl bootout "gui/$(id -u)" "$AGENT" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENT" 2>/dev/null || launchctl load -w "$AGENT"
sleep 1

# ждём, пока поднимется
for i in $(seq 1 10); do
  if curl -s -m 2 "http://localhost:8765/" >/dev/null; then
    echo "OK: сервис запущен http://localhost:8765"
    exit 0
  fi
  sleep 1
done
echo "ВНИМАНИЕ: сервис не ответил. Лог: $DIR/server.log"
tail -5 "$DIR/server.log" 2>/dev/null || true
exit 1
