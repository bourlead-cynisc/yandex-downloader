#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "$ROOT/run-omarchy.sh"
mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/256x256/apps"
cp "$ROOT/assets/icon.png" "$HOME/.local/share/icons/hicolor/256x256/apps/yandex-downloader.png"
# Escape double-quotes and backslashes in desktop entry path.
DESKTOP_ROOT="${ROOT//\\/\\\\}"
DESKTOP_ROOT="${DESKTOP_ROOT//\"/\\\"}"
cat > "$HOME/.local/share/applications/yandex-downloader.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Yandex Downloader
Comment=Yandex Music track and playlist downloader
Exec="$DESKTOP_ROOT/run-omarchy.sh"
Path=$ROOT
Icon=yandex-downloader
Terminal=false
Categories=Audio;Network;
StartupNotify=true
EOF
echo "Готово. Найдите Yandex Downloader через Super+Space."
echo "Первый запуск установит Python-зависимости в папку .venv."