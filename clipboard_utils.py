"""Testable clipboard insertion shared by native Tk entries in the desktop UI."""
from __future__ import annotations

import tkinter as tk
from typing import Callable


def paste_from_clipboard(entry, clipboard_get: Callable[[], str]) -> bool:
    """Paste at the caret, replacing selected text; never clear the clipboard.

    Returns False for an empty/unavailable clipboard instead of raising TclError.
    """
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
