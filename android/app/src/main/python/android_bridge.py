"""Small Chaquopy bridge for the Android UI.

The Java activity receives only structured status events. Authentication tokens
stay in Python RAM and are never written to preferences, files or logs.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from downloader import download_all, parse_link

_client = None
_cancel = threading.Event()


def _send(listener, kind: str, **data):
    listener.onEvent(kind, json.dumps(data, ensure_ascii=False))


def login_device(listener):
    global _client
    from yandex_music import Client

    try:
        client = Client()

        def show_code(code):
            _send(listener, "auth_code", url=code.verification_url, code=code.user_code)

        token = client.device_auth(on_code=show_code)
        if not token or not getattr(token, "access_token", None):
            raise RuntimeError("Сервис не предоставил токен авторизации.")
        client.init()
        _client = client
        _send(listener, "auth_ok")
    except Exception as exc:
        _client = None
        _send(listener, "auth_error", message=str(exc)[:350])


def login_token(token: str, listener):
    global _client
    from yandex_music import Client

    try:
        token = token.strip()
        if not token:
            raise ValueError("Введите ваш OAuth-токен.")
        client = Client(token).init()
        _client = client
        _send(listener, "auth_ok")
    except Exception as exc:
        _client = None
        _send(listener, "auth_error", message=str(exc)[:350])


def is_authenticated():
    return _client is not None


def cancel():
    _cancel.set()


def run_download(url: str, target_cache_dir: str, quality: str, listener):
    if _client is None:
        _send(listener, "fatal", message="Сначала войдите в аккаунт.")
        return
    _cancel.clear()
    try:
        parse_link(url)
        path = Path(target_cache_dir)
        path.mkdir(parents=True, exist_ok=True)
        # A playlist subfolder is created by Android SAF (DocumentFile), not here.
        download_all(_client, url, path, quality, False,
                     lambda kind, data: _send(listener, kind, **data), _cancel)
    except Exception as exc:
        _send(listener, "fatal", message=str(exc)[:400])