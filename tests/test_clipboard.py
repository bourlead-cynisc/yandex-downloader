"""Clipboard behavior must not require an X server for unit tests."""
import tkinter as tk

from clipboard_utils import paste_from_clipboard


class FakeEntry:
    def __init__(self, text="", caret=0, selection=None):
        self.text = text
        self.caret = caret
        self.selection = selection

    def index(self, name):
        if isinstance(name, int):
            return name
        if name == "insert":
            return self.caret
        if name.startswith("sel.") and self.selection is not None:
            return self.selection[0] if name == "sel.first" else self.selection[1]
        raise tk.TclError("no selection")

    def delete(self, first, last):
        start, end = self.index(first), self.index(last)
        self.text = self.text[:start] + self.text[end:]
        self.caret = start
        self.selection = None

    def insert(self, index, value):
        at = self.index(index)
        self.text = self.text[:at] + value + self.text[at:]
        self.caret = at + len(value)


def test_paste_full_yandex_music_url():
    url = "https://music.yandex.ru/album/42389520/track/111124021"
    entry = FakeEntry()
    assert paste_from_clipboard(entry, lambda: url)
    assert entry.text == url


def test_paste_at_caret():
    entry = FakeEntry("AB", caret=1)
    assert paste_from_clipboard(entry, lambda: "x")
    assert entry.text == "AxB"


def test_paste_replaces_selection():
    entry = FakeEntry("old-value", caret=9, selection=(0, 9))
    assert paste_from_clipboard(entry, lambda: "new")
    assert entry.text == "new"


def test_empty_clipboard_does_not_modify():
    entry = FakeEntry("original", caret=3)
    assert not paste_from_clipboard(entry, lambda: "")
    assert entry.text == "original"


def test_unavailable_clipboard_does_not_crash():
    entry = FakeEntry("original", caret=3)
    def unavailable():
        raise tk.TclError("selection does not exist")
    assert not paste_from_clipboard(entry, unavailable)
    assert entry.text == "original"
