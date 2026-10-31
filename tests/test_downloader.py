from pathlib import Path
from types import SimpleNamespace as NS
from threading import Event
from unittest.mock import patch, MagicMock
import pytest

from downloader import (DownloadCancelled, InvalidMusicURL, _extension,
                        download_one, format_eta, human_bytes, parse_link,
                        resolve_link, safe_name, _stream_url)

@pytest.mark.parametrize("url,kind,ident,owner", [
    ("https://music.yandex.ru/album/17/track/42?utm_source=test", "track", "42", ""),
    ("https://music.yandex.ru/track/42", "track", "42", ""),
    ("https://music.yandex.ru/users/test-user/playlists/111", "playlist", "111", "test-user"),
    ("https://music.yandex.ru/playlists/1234:5678", "playlist", "5678", "1234"),
    ("https://music.yandex.com/album/123", "album", "123", ""),
    ("https://music.yandex.ru/playlists/9a6fce71-3da7-4fe1-bab5-47f238d29c2e", "playlist_uuid", "9a6fce71-3da7-4fe1-bab5-47f238d29c2e", ""),
])
def test_parsing(url,kind,ident,owner):
    result = parse_link(url)
    assert (result.kind,result.item_id,result.owner) == (kind,ident,owner)

@pytest.mark.parametrize("url", ["https://music.yandex.ru.evil.org/track/33", "file:///etc/passwd",
                                   "https://evil.com/track/44", "https://music.yandex.ru/track/nope"])
def test_reject(url):
    with pytest.raises(InvalidMusicURL):
        parse_link(url)

@pytest.mark.parametrize("value", ["../evil/../", "CON", "bad:name?.mp3", "a\\b"])
def test_safe_name(value):
    result = safe_name(value)
    assert result and all(c not in result for c in '/\\:*?"<>|')


def test_playlist_resolution():
    track = NS(id="12", title="Hello", artists=[NS(name="Artist")])
    entry = NS(track=track)
    client = MagicMock()
    client.users_playlists.return_value = NS(title="My Playlist", tracks=[entry])
    title, result = resolve_link(client, parse_link("https://music.yandex.ru/users/xyz/playlists/7"))
    assert title == "My Playlist" and len(result) == 1
    assert result[0].artist == "Artist"
    client.users_playlists.assert_called_once_with("7", user_id="xyz")


def test_album_resolution():
    client = MagicMock()
    client.albums_with_tracks.return_value = NS(title="Album", volumes=[[NS(id="22",title="Song",artists=[])]])
    title, items = resolve_link(client, parse_link("https://music.yandex.ru/album/123"))
    assert title == "Album" and items[0].track_id == "22"


def test_progress_math():
    assert human_bytes(1024) == "1.0 КБ"
    assert format_eta(91) == "1 мин 31 с"
    assert _extension("flac-mp4") == ".m4a"


def test_atomic_and_skip(tmp_path):
    from downloader import TrackItem
    track = TrackItem(track=object(),title="Song",artist="Artist",track_id="42")
    client = MagicMock()
    info = NS(transport="raw",codec="mp3",url="https://example.com/file.mp3")
    def fake_stream(url, temp, progress, cancel):
        temp.write_bytes(b"audiotest")
        progress(9,9,100)
        return 9
    with patch("downloader._pick_file",return_value=("new",info,"mp3")), patch("downloader._stream_url", side_effect=fake_stream) as called:
        name, count, exists = download_one(client, track, tmp_path, "hq", lambda *a:None, Event())
        assert not exists and count == 9 and name.read_bytes() == b"audiotest"
        name2,count2,exists2 = download_one(client, track, tmp_path, "hq", lambda *a:None, Event())
        assert exists2 and name2 == name
        assert called.call_count == 1
    assert not list(tmp_path.glob("*.part"))


def test_cancel_cleans_part(tmp_path):
    from downloader import TrackItem
    track = TrackItem(track=object(),title="Song",artist="Artist",track_id="2")
    info = NS(transport="raw",codec="mp3",url="https://example.com/file.mp3")
    def broken(url, temp, progress, cancel):
        temp.write_bytes(b"incomplete")
        raise DownloadCancelled()
    with patch("downloader._pick_file",return_value=("new",info,"mp3")), patch("downloader._stream_url",side_effect=broken):
        with pytest.raises(DownloadCancelled):
            download_one(MagicMock(), track, tmp_path,"hq",lambda *a:None,Event())
    assert not list(tmp_path.iterdir())


def test_streams_content_length_and_progress(tmp_path):
    class FakeResponse:
        headers = {"Content-Length": "5"}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            yield b"abc"
            yield b"de"
    seen = []
    with patch("downloader.requests.get", return_value=FakeResponse()) as req:
        size = _stream_url("https://cdn.example/file", tmp_path / "test.part",
                           lambda read,total,speed: seen.append((read,total,speed)),Event())
    assert size == 5
    assert (tmp_path / "test.part").read_bytes() == b"abcde"
    assert seen[-1][:2] == (5,5)
    req.assert_called_once()


def test_stream_fails_if_file_is_short(tmp_path):
    class FakeResponse:
        headers = {"Content-Length": "10"}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def raise_for_status(self): pass
        def iter_content(self, chunk_size): yield b"abc"
    with patch("downloader.requests.get", return_value=FakeResponse()):
        with pytest.raises(RuntimeError, match="неполный файл"):
            _stream_url("https://cdn.example/file",tmp_path/"test.part",lambda *args:None,Event())


def test_new_file_info_nested_raw():
    from downloader import TrackItem, _pick_file
    client = MagicMock()
    track = TrackItem(track=object(), title="Title", artist="Artist", track_id="42")
    download = NS(codec="mp3", transport="raw", url="https://cdn.example/42.mp3")
    client.tracks_file_info.return_value = NS(download_info=download)
    mode, info, codec = _pick_file(client, track, "hq")
    assert mode == "new" and info is download and codec == "mp3"
    client.tracks_file_info.assert_called_once_with(
        "42", quality="hq", codecs=["mp3"], transport="raw")


def test_encrypted_file_delegates_download_to_library(tmp_path):
    from downloader import TrackItem
    track = TrackItem(track=object(), title="Song", artist="Artist", track_id="27")
    class EncryptedFile:
        transport = "encraw"
        codec = "flac"
        url = "https://cdn.example/encrypted"
        def download(self, path):
            Path(path).write_bytes(b"mock_decoded_audio")
    info = EncryptedFile()
    calls=[]
    with patch("downloader._pick_file", return_value=("new", info, "flac")):
        output, size, existed=download_one(MagicMock(), track, tmp_path, "lossless", lambda *a:calls.append(a),Event())
    assert not existed and size == len(b"mock_decoded_audio")
    assert output.suffix == ".flac" and output.read_bytes() == b"mock_decoded_audio"
    assert calls[-1][2] is None


def test_legacy_fallback_when_new_file_unavailable():
    from downloader import TrackItem, _pick_file
    track = TrackItem(track=object(), title="Song", artist="Artist", track_id="7")
    client = MagicMock()
    client.tracks_file_info.return_value = NS(download_info=None)
    mp3 = NS(codec="mp3", bitrate_in_kbps=320, preview=False)
    preview = NS(codec="mp3", bitrate_in_kbps=999, preview=True)
    client.tracks_download_info.return_value = [mp3, preview]
    mode, info, codec = _pick_file(client, track, "hq")
    assert (mode, info, codec) == ("legacy", mp3, "mp3")


def test_lossless_requires_available_new_file():
    from downloader import TrackItem, _pick_file
    track = TrackItem(track=object(), title="Song", artist="Artist", track_id="7")
    client = MagicMock()
    client.tracks_file_info.return_value = None
    with pytest.raises(RuntimeError, match="не предоставил"):
        _pick_file(client, track, "lossless")
    client.tracks_download_info.assert_not_called()