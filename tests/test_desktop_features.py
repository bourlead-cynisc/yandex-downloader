"""Regression coverage for liked tracks, media tags and secure account storage."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest

from downloader import parse_link, resolve_link, track_item, write_audio_tags
from auth_store import SecureStorageUnavailable, load_token, save_token, delete_token


@pytest.mark.parametrize("url,owner", [
    ("https://music.yandex.ru/collection?type=liked", ""),
    ("https://music.yandex.ru/collection/tracks", ""),
    ("https://music.yandex.ru/users/my.login/playlists/3", "my.login"),
    ("https://music.yandex.ru/playlists/1234:3", "1234"),
])
def test_liked_links(url,owner):
    result=parse_link(url)
    assert result.kind == "likes"
    assert result.owner == owner


def test_likes_batch_fetch_and_no_per_track_requests():
    client=MagicMock()
    client.users_likes_tracks.return_value=NS(tracks=[NS(id=str(i), track=None) for i in range(215)])
    client.tracks.side_effect=lambda ids: [NS(id=int(i), title=f"Title {i}", artists=[NS(name="Artist")]) for i in ids]
    title,items=resolve_link(client,parse_link("https://music.yandex.ru/collection?type=liked"))
    assert title == "Мне нравится"
    assert len(items)==215
    assert items[0].track_id == "0" and items[-1].track_id == "214"
    assert client.tracks.call_count == 3
    sizes=[len(a.args[0]) for a in client.tracks.call_args_list]
    assert sizes == [100,100,15]


def test_likes_trackshort_with_hydrated_track():
    client=MagicMock()
    track=NS(id="7", title="Трек", artists=[NS(name="Певец")])
    client.users_likes_tracks.return_value=NS(tracks=[NS(track=track)])
    title,items=resolve_link(client,parse_link("https://music.yandex.ru/collection?type=liked"))
    assert (title,items[0].title,items[0].artist)==("Мне нравится","Трек","Певец")
    client.tracks.assert_not_called()


def test_likes_error_does_not_invent_songs():
    client=MagicMock()
    client.users_likes_tracks.return_value=NS(tracks=[])
    title,items=resolve_link(client,parse_link("https://music.yandex.ru/collection?type=liked"))
    assert title == "Мне нравится" and items==[]


def test_metadata_fields_from_yandex_track():
    track=NS(id="99", title="Название", artists=[NS(name="Артист")],
             albums=[NS(title="Альбом",year=2020,artists=[NS(name="Автор альбома")])],
             track_position=NS(index=5))
    item=track_item(track)
    assert (item.title,item.artist,item.album,item.album_artist,item.year,item.track_number)==(
        "Название","Артист","Альбом","Автор альбома","2020","5")


def test_write_tags_real_mp3(tmp_path):
    import subprocess
    from mutagen import File
    ffmpeg=__import__('shutil').which('ffmpeg')
    if not ffmpeg:
        pytest.skip('ffmpeg is not installed; real audio tag check runs in fixture-enabled env')
    path=tmp_path/'fixture.mp3.part'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','anullsrc=r=44100:cl=mono',
                    '-t','0.12','-codec:a','libmp3lame','-f','mp3','-y',str(path)],
                   capture_output=True,check=False)
    # FFmpeg guesses output codec from .part; explicitly specify MP3 output.
    if not path.exists():
        pytest.skip('FFmpeg did not create an MP3 fixture')
    item=__import__('downloader').TrackItem(object(), 'Трек', 'Артист', '42',
                                          'Альбом', 'Автор', '2023', '7')
    assert write_audio_tags(path,item)
    audio=File(path,easy=True)
    assert audio['title']==['Трек'] and audio['artist']==['Артист']
    assert audio['album']==['Альбом'] and audio['date']==['2023']
    assert write_audio_tags(path,__import__('downloader').TrackItem(object(),'Другое','Иной','42'),missing_only=True)
    assert File(path,easy=True)['title']==['Трек']


class FakeKeyring:
    def __init__(self):
        self.saved={}
    def get_password(self,service,user):
        return self.saved.get((service,user))
    def set_password(self,service,user,token):
        self.saved[(service,user)]=token
    def delete_password(self,service,user):
        self.saved.pop((service,user),None)


def test_store_persists_login_and_logs_out():
    fake=FakeKeyring()
    with patch('auth_store._keyring',return_value=fake):
        assert load_token() is None
        save_token('example-test-token')
        assert load_token()=='example-test-token'
        delete_token()
        assert load_token() is None


def test_insecure_keyring_is_never_used():
    class Insecure:
        priority=-1
    with patch('sys.modules',{'keyring':NS(get_keyring=lambda: Insecure())}):
        with pytest.raises(SecureStorageUnavailable):
            save_token('unsafe')