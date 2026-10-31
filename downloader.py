"""Yandex Music download orchestration, with no UI or credential persistence.

Uses the unofficial yandex-music package and only the authenticated user's access.
The service may disallow a track or change its API at any moment.
"""
from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import parse_qs, unquote, urlsplit

import requests


class DownloadCancelled(Exception):
    """User interrupted the current transfer."""


class InvalidMusicURL(ValueError):
    """URL is not a supported music.yandex link."""


@dataclass(frozen=True)
class Link:
    kind: str
    item_id: str
    owner: str = ""


@dataclass
class TrackItem:
    track: object
    title: str
    artist: str
    track_id: str
    album: str = ""
    album_artist: str = ""
    year: str = ""
    track_number: str = ""


def parse_link(link: str) -> Link:
    """Parse track, playlist, and album URLs; reject lookalike domains."""
    raw = link.strip()
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https"):
        raise InvalidMusicURL("Вставьте полную ссылку https://music.yandex.ru/...")
    if (parts.hostname or "").lower() not in {"music.yandex.ru", "music.yandex.com", "music.yandex.kz", "music.yandex.by"}:
        raise InvalidMusicURL("Ссылка должна вести на music.yandex.ru (или другой домен Яндекс Музыки).")
    path = [unquote(p) for p in parts.path.split("/") if p]
    # Liked tracks are the user's library, not a public playlist.
    if path in (["collection"], ["collection", "tracks"], ["collection", "liked"]):
        parameters = parse_qs(parts.query)
        if path != ["collection"] or parameters.get("type", ["liked"])[0] in ("liked", "tracks"):
            return Link("likes", "liked")
    if not path:
        raise InvalidMusicURL("В ссылке нет идентификатора трека или плейлиста.")
    # /album/123/track/456; /track/456
    if len(path) >= 4 and path[0] == "album" and path[1].isdigit() and path[2] == "track" and path[3].isdigit():
        return Link("track", path[3])
    if len(path) >= 2 and path[0] == "track" and path[1].isdigit():
        return Link("track", path[1])
    # /users/login/playlists/kind
    if len(path) >= 4 and path[0] == "users" and path[2] == "playlists":
        if not re.fullmatch(r"[\w.@-]{1,128}", path[1]) or not path[3].isdigit():
            raise InvalidMusicURL("Неизвестный формат ссылки на плейлист.")
        if path[3] == "3":
            return Link("likes", "liked", path[1])
        return Link("playlist", path[3], path[1])
    # /playlists/UID:KIND; /playlists/<UUID>
    if len(path) >= 2 and path[0] == "playlists":
        value = path[1]
        if re.fullmatch(r"\d+:\d+", value):
            owner, ident = value.split(":", 1)
            if ident == "3":
                return Link("likes", "liked", owner)
            return Link("playlist", ident, owner)
        if re.fullmatch(r"[a-fA-F0-9-]{32,36}", value):
            return Link("playlist_uuid", value)
    if len(path) >= 2 and path[0] == "album" and path[1].isdigit():
        return Link("album", path[1])
    raise InvalidMusicURL("Поддерживаются ссылки на трек, альбом или плейлист Яндекс Музыки.")


def safe_name(value: str, limit: int = 120) -> str:
    """Ensure every platform accepts filenames and paths stay under chosen directory."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (value or "Без названия"))
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value or value.upper().split(".")[0] in {
        "CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]
    }:
        value = "_" + (value or "untitled")
    return value[:limit].rstrip(" .") or "untitled"


def track_item(track: object) -> TrackItem:
    title = getattr(track, "title", None) or "Без названия"
    artists = getattr(track, "artists", None) or []
    artist = ", ".join(str(getattr(a, "name", "")) for a in artists if getattr(a, "name", "")) or "Неизвестный исполнитель"
    albums = getattr(track, "albums", None) or []
    album = albums[0] if albums else None
    album_title = getattr(album, "title", None) or ""
    album_artists = getattr(album, "artists", None) or []
    album_artist = ", ".join(str(getattr(a, "name", "")) for a in album_artists if getattr(a, "name", "")) or artist
    year = str(getattr(album, "year", "") or "")
    position = getattr(track, "track_position", None)
    number = getattr(position, "index", None) or getattr(track, "track_number", None) or ""
    return TrackItem(track=track, title=str(title), artist=artist,
                     track_id=str(getattr(track, "id", "")), album=str(album_title),
                     album_artist=album_artist, year=year, track_number=str(number))


def _liked_tracks(client: object, owner: str = "") -> list[TrackItem]:
    """Resolve liked TrackShort items, including large libraries, in API batches."""
    result = client.users_likes_tracks(user_id=owner) if owner else client.users_likes_tracks()
    shorts = getattr(result, "tracks", result) or []
    # Keep the original order of liked tracks, even if API batch responses
    # arrive shuffled or some IDs are not available to the current account.
    ordered: list[tuple[str, TrackItem | None]] = []
    ids: list[str] = []
    for short in shorts:
        if not short:
            continue
        track = getattr(short, "track", None)
        if track and getattr(track, "title", None):
            ordered.append((str(getattr(track, "id", "")), track_item(track)))
            continue
        ident = getattr(short, "track_id", None) or getattr(short, "id", None)
        if ident:
            ident = str(ident)
            ids.append(ident)
            ordered.append((ident, None))
        elif hasattr(short, "fetch_track"):
            full = short.fetch_track()
            if full:
                ordered.append((str(getattr(full, "id", "")), track_item(full)))
    fetched: dict[str, TrackItem] = {}
    for offset in range(0, len(ids), 100):
        for track in client.tracks(ids[offset:offset + 100]) or []:
            if track:
                item = track_item(track)
                fetched[item.track_id] = item
    return [item or fetched.get(ident.split(":", 1)[0])
            for ident, item in ordered
            if item or ident.split(":", 1)[0] in fetched]


def resolve_link(client: object, link: Link) -> tuple[str, list[TrackItem]]:
    """Return folder title and full track objects. Service can omit unavailable entries."""
    if link.kind == "likes":
        return "Мне нравится", _liked_tracks(client, link.owner)
    if link.kind == "track":
        tracks = client.tracks([link.item_id]) or []
        return "Один трек", [track_item(t) for t in tracks if t]
    if link.kind in {"playlist", "playlist_uuid"}:
        if link.kind == "playlist_uuid":
            playlist = client.playlist(link.item_id)
        else:
            playlist = client.users_playlists(link.item_id, user_id=link.owner)
        if not playlist:
            return "Плейлист", []
        rows = getattr(playlist, "tracks", None)
        if rows is None:
            rows = playlist.fetch_tracks()
        # Playlist entries usually contain a hydrated .track. Resolve missing ones.
        tracks = []
        for entry in rows or []:
            obj = getattr(entry, "track", None)
            if not obj and hasattr(entry, "fetch_track"):
                obj = entry.fetch_track()
            if obj:
                tracks.append(track_item(obj))
        return str(getattr(playlist, "title", "Плейлист") or "Плейлист"), tracks
    if link.kind == "album":
        album = client.albums_with_tracks(link.item_id)
        tracks = [track_item(t) for volume in (getattr(album, "volumes", None) or []) for t in volume if t]
        return str(getattr(album, "title", "Альбом") or "Альбом"), tracks
    raise InvalidMusicURL("Неподдерживаемая ссылка")


def human_bytes(size: int | float | None) -> str:
    if size is None:
        return "—"
    size = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if abs(size) < 1024 or unit == "ГБ":
            return f"{size:.1f} {unit}" if unit != "Б" else f"{int(size)} Б"
        size /= 1024
    return "—"


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    s = int(seconds)
    if s < 60:
        return f"{s} с"
    return f"{s // 60} мин {s % 60} с"


def _extension(codec: str) -> str:
    codec = (codec or "mp3").lower()
    return ".m4a" if codec.endswith("-mp4") else (".flac" if codec == "flac" else ".aac" if codec in ("aac", "he-aac") else ".mp3")


def _pick_file(client: object, item: TrackItem, quality: str):
    """Try newer authenticated file endpoint. Legacy API is a fallback for MP3."""
    codecs = ["flac", "flac-mp4", "aac-mp4", "mp3"] if quality == "lossless" else ["mp3"]
    first_error = None
    for transport in ("raw", "encraw"):
        try:
            info = client.tracks_file_info(item.track_id, quality=quality, codecs=codecs, transport=transport)
            # yandex-music 3.2.x returns FileInfo, whose download_info
            # contains the actual FileDownloadInfo / URLs / codec.
            info = getattr(info, "download_info", info)
            if isinstance(info, (list, tuple)):
                info = info[0] if info else None
            if info and (getattr(info, "url", None) or getattr(info, "urls", None)):
                return ("new", info, str(getattr(info, "codec", "mp3") or "mp3"))
        except Exception as exc:
            first_error = exc
    if quality != "lossless":
        try:
            legacy = client.tracks_download_info(item.track_id) or []
            options = [x for x in legacy if getattr(x, "codec", "") == "mp3" and not getattr(x, "preview", False)]
            if options:
                best = max(options, key=lambda x: int(getattr(x, "bitrate_in_kbps", 0) or 0))
                return ("legacy", best, "mp3")
        except Exception as exc:
            first_error = exc
    raise RuntimeError("Сервис не предоставил доступный аудиофайл для этого трека.") from first_error


def _stream_url(url: str, temp_path: Path, on_bytes: Callable[[int, int | None, float], None], cancel: threading.Event) -> int:
    if urlsplit(url).scheme != "https":
        raise RuntimeError("Сервис вернул небезопасную ссылку на файл.")
    start = time.monotonic()
    read = 0
    last_report = 0.0
    with requests.get(url, stream=True, timeout=(12, 30)) as response:
        response.raise_for_status()
        content_len = response.headers.get("Content-Length")
        total = int(content_len) if content_len and content_len.isdigit() else None
        if total is not None and total <= 0:
            total = None
        with temp_path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=128 * 1024):
                if cancel.is_set():
                    raise DownloadCancelled()
                if chunk:
                    file.write(chunk)
                    read += len(chunk)
                    now = time.monotonic()
                    if now - last_report >= 0.15:
                        on_bytes(read, total, read / max(now - start, 0.001))
                        last_report = now
        on_bytes(read, total, read / max(time.monotonic() - start, 0.001))
    if read == 0:
        raise RuntimeError("Сервис вернул пустой файл.")
    if total is not None and read != total:
        raise RuntimeError(f"Получен неполный файл: {read} из {total} байт")
    return read


def write_audio_tags(path: Path, item: TrackItem, *, missing_only: bool = False) -> bool:
    """Write real audio metadata (ID3/Vorbis/MP4), not just an audio filename.

    Unsupported or malformed audio is left intact. This is important for
    preserving a downloaded file if the service changes its format.
    """
    from mutagen import File as AudioFile
    from mutagen import MutagenError

    try:
        # `easy=True` normalizes common tags across MP3, FLAC, and M4A.
        audio = AudioFile(path, easy=True)
        if audio is None:
            return False
        if audio.tags is None:
            audio.add_tags()
        fields = {"title": item.title, "artist": item.artist,
                  "album": item.album, "albumartist": item.album_artist,
                  "date": item.year, "tracknumber": item.track_number}
        for key, value in fields.items():
            if value and (not missing_only or not audio.get(key)):
                audio[key] = [str(value)]
        audio.save()
        return True
    except (MutagenError, ValueError, KeyError, TypeError, OSError):
        return False


def download_one(client: object, item: TrackItem, folder: Path, quality: str,
                 progress: Callable[[int, int | None, float], None], cancel: threading.Event) -> tuple[Path, int, bool]:
    """Use temp files + atomic rename; never overwrite a pre-existing music file."""
    mode, info, codec = _pick_file(client, item, quality)
    name = safe_name(f"{item.artist} - {item.title}", 140)
    filename = f"{name} [{safe_name(item.track_id, 32)}]{_extension(codec)}"
    output = folder / filename
    if output.exists():
        # Repair missing metadata on files downloaded by older versions.
        write_audio_tags(output, item, missing_only=True)
        return output, output.stat().st_size, True
    part = folder / (filename + ".part")
    try:
        if cancel.is_set():
            raise DownloadCancelled()
        if mode == "new" and getattr(info, "transport", "raw") == "encraw":
            # Library performs authenticated download and decoding. Its API does
            # not expose incremental byte callbacks; do not invent progress.
            info.download(str(part))
            if cancel.is_set():
                raise DownloadCancelled()
            size = part.stat().st_size
            progress(size, size, None)  # decoded transfer speed is unavailable
        else:
            url = (str(getattr(info, "url", None) or (getattr(info, "urls", None) or [""])[0])
                   if mode == "new" else info.get_direct_link())
            size = _stream_url(url, part, progress, cancel)
        if size <= 0:
            raise RuntimeError("Получен пустой файл.")
        # Write tags before publish so media players can read artist/title/album.
        # Mutagen may add ID3 frames, so the resulting file can grow slightly.
        write_audio_tags(part, item)
        # Atomic rename. Each track has a distinct ID in the filename.
        os.replace(part, output)
        return output, output.stat().st_size, False
    except Exception:
        part.unlink(missing_ok=True)
        raise


EventHandler = Callable[[str, dict], None]


def download_all(client: object, url: str, destination: Path, quality: str, subfolder: bool,
                 emit: EventHandler, cancel: threading.Event) -> None:
    parsed = parse_link(url)
    title, items = resolve_link(client, parsed)
    if not items:
        raise RuntimeError("Не удалось получить треки. Возможно, плейлист скрыт или пуст.")
    folder = destination / safe_name(title) if subfolder and parsed.kind != "track" else destination
    folder.mkdir(parents=True, exist_ok=True)
    emit("resolved", {"count": len(items), "title": title, "folder": str(folder)})
    done = 0
    failed = 0
    skipped = 0
    for index, item in enumerate(items, 1):
        if cancel.is_set():
            emit("cancelled", {"done": done, "failed": failed, "skipped": skipped})
            return
        emit("track", {"index": index, "count": len(items), "name": f"{item.artist} — {item.title}"})
        try:
            path, size, existed = download_one(client, item, folder, quality,
                 lambda got, total, speed: emit("bytes", {"got": got, "total": total, "speed": speed}), cancel)
            if existed:
                skipped += 1
                emit("skipped", {"name": path.name})
            else:
                done += 1
                emit("saved", {"name": path.name, "size": size})
        except DownloadCancelled:
            emit("cancelled", {"done": done, "failed": failed, "skipped": skipped})
            return
        except Exception as exc:
            failed += 1
            emit("error", {"name": item.title, "message": str(exc)[:240]})
        emit("overall", {"index": index, "count": len(items)})
    emit("finished", {"done": done, "failed": failed, "skipped": skipped, "folder": str(folder)})