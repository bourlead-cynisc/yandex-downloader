"""OAuth access-token persistence in the OS credential vault, never in plaintext.

Windows uses Credential Manager; Linux needs a usable Secret Service/KWallet
session. If unavailable, the app keeps the login only in RAM and explains why.
"""
from __future__ import annotations

SERVICE = "YandexDownloader"
USER = "YandexMusicAccount"


class SecureStorageUnavailable(RuntimeError):
    pass


def _keyring():
    try:
        import keyring
        backend = keyring.get_keyring()
        name = type(backend).__module__
        allowed = ("keyring.backends.Windows", "keyring.backends.SecretService",
                   "keyring.backends.kwallet", "keyring.backends.macOS",
                   "keyring.backends.chainer")
        if not name.startswith(allowed) or backend.priority <= 0:
            raise SecureStorageUnavailable("В системе не настроено безопасное хранилище паролей.")
        return keyring
    except ImportError as exc:
        raise SecureStorageUnavailable("Не установлена библиотека keyring.") from exc
    except SecureStorageUnavailable:
        raise
    except Exception as exc:
        raise SecureStorageUnavailable("Не удалось открыть системное хранилище паролей.") from exc


def load_token() -> str | None:
    try:
        return _keyring().get_password(SERVICE, USER)
    except SecureStorageUnavailable:
        raise
    except Exception as exc:
        raise SecureStorageUnavailable("Не удалось прочитать сохранённый вход.") from exc


def save_token(token: str) -> None:
    if not token or not isinstance(token, str):
        raise ValueError("OAuth-токен отсутствует")
    try:
        _keyring().set_password(SERVICE, USER, token)
    except SecureStorageUnavailable:
        raise
    except Exception as exc:
        raise SecureStorageUnavailable("Не удалось сохранить вход в защищённом хранилище.") from exc


def delete_token() -> None:
    try:
        ring = _keyring()
        if ring.get_password(SERVICE, USER) is not None:
            ring.delete_password(SERVICE, USER)
    except SecureStorageUnavailable:
        raise
    except Exception as exc:
        raise SecureStorageUnavailable("Не удалось удалить сохранённый вход.") from exc