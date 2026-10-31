#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$(realpath "$0")")"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Не найден python3. Установите: sudo pacman -S --needed python tk' >&2
  exit 1
fi
if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
  echo 'Не найден tkinter. Установите: sudo pacman -S --needed tk' >&2
  exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python app.py