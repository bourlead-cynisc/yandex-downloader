#!/usr/bin/env bash
# Run once in the extracted project folder on a machine with git and GitHub CLI.
set -euo pipefail
cd -- "$(dirname -- "$(realpath "$0")")"
if ! command -v gh >/dev/null 2>&1; then
  echo 'Установите GitHub CLI (Omarchy: sudo pacman -S github-cli) и повторите запуск.' >&2
  exit 1
fi
if ! command -v git >/dev/null 2>&1; then
  echo 'Не найден git.' >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo 'Выполните gh auth login и повторите запуск.' >&2
  exit 1
fi
OWNER="$(gh api user --jq .login)"
REPO="${OWNER}/yandex-downloader"
if [[ ! -d .git ]]; then
  git init -b main
fi
if git remote get-url origin >/dev/null 2>&1; then
  CURRENT="$(git remote get-url origin)"
  case "$CURRENT" in
    "https://github.com/${REPO}.git"|"git@github.com:${REPO}.git") ;;
    *) echo "origin указывает на другой репозиторий: $CURRENT" >&2; exit 1 ;;
  esac
fi
git add README.md app.py downloader.py requirements.txt requirements-build.txt \
  assets/ .github/ tests/ .gitignore *.sh *.bat *.ps1
if ! git diff --cached --quiet; then
  git commit -m 'Initial release of Yandex Downloader'
fi
if gh repo view "$REPO" >/dev/null 2>&1; then
  if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "https://github.com/${REPO}.git"
  fi
  git push -u origin main
else
  gh repo create "$REPO" --public --source=. --remote=origin --push \
    --description 'Yandex Music desktop downloader for Windows and Omarchy Linux'
fi
echo "Проект опубликован: https://github.com/${REPO}"
echo "Сборки: https://github.com/${REPO}/actions"
echo "Релиз после успешной сборки: https://github.com/${REPO}/releases"