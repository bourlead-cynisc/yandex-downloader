#!/usr/bin/env bash
# For the precompiled Linux release tarball produced by GitHub Actions.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x "$ROOT/yandex-downloader/yandex-downloader" ]]; then
  echo 'Не найден исполняемый файл yandex-downloader/yandex-downloader. Распакуйте полный архив релиза.' >&2
  exit 1
fi
INSTALL="$HOME/.local/opt/yandex-downloader"
mkdir -p "$HOME/.local/opt" "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/256x256/apps"
if [[ -d "$INSTALL" ]]; then
  rm -rf -- "$INSTALL"
fi
cp -a -- "$ROOT/yandex-downloader" "$INSTALL"
if [[ -f "$ROOT/icon.png" ]]; then
  cp "$ROOT/icon.png" "$HOME/.local/share/icons/hicolor/256x256/apps/yandex-downloader.png"
fi
cat > "$HOME/.local/share/applications/yandex-downloader.desktop" <<ENTRY
[Desktop Entry]
Name=Yandex Downloader
GenericName=Music Downloader
Comment=Download available music from Yandex Music
Exec=$INSTALL/yandex-downloader
Icon=yandex-downloader
Type=Application
Terminal=false
Categories=Audio;Network;
StartupNotify=true
ENTRY
chmod +x "$HOME/.local/share/applications/yandex-downloader.desktop"
echo "Установлено: $INSTALL. Запускайте через меню Omarchy (Super+Space)."