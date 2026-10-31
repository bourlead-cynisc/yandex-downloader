"""Paste from clipboard at the caret, replacing selection when present."""
import tkinter as tk


def paste_from_clipboard(entry, clipboard_get):
    try:
        value = clipboard_get()
    except (tk.TclError, UnicodeError):
        return False
    if not isinstance(value, str) or not value:
        return False
    try:
        first = entry.index("sel.first")
    except tk.TclError:
        entry.insert("insert", value)
    else:
        entry.delete("sel.first", "sel.last")
        entry.insert(first, value)
    return True