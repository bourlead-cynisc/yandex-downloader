"""Yandex Downloader desktop UI: Windows / Arch (Omarchy)."""
from __future__ import annotations

import queue
import sys
import tkinter as tk
import threading
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from auth_store import SecureStorageUnavailable, delete_token, load_token, save_token
from clipboard_utils import paste_from_clipboard
from downloader import InvalidMusicURL, download_all, format_eta, human_bytes, parse_link


VERSION = "1.0.4"
BG = "#101114"
PANEL = "#1A1C20"
INPUT = "#23262C"
FG = "#F2F3F5"
MUTED = "#9298A3"
ACCENT = "#FFCC32"
ACCENT_HOVER = "#E9B918"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Yandex Downloader")
        self.geometry("900x760")
        self.minsize(740, 680)
        self.configure(fg_color=BG)
        icon_file = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "assets" / "icon.png"
        if icon_file.exists():
            try:
                self._icon = tk.PhotoImage(file=str(icon_file))
                self.iconphoto(True, self._icon)
            except tk.TclError:
                pass
        self.events = queue.Queue()
        self.client = None
        self.cancel_event = threading.Event()
        self.busy = False
        self.auth_busy = False
        self.folder = ctk.StringVar(value=str(Path.home() / "Music"))
        self.link = ctk.StringVar()
        self.quality = ctk.StringVar(value="Высокое · MP3")
        self.make_subfolder = ctk.BooleanVar(value=True)
        self.remember_login = ctk.BooleanVar(value=True)
        self._build()
        self.after(100, self._poll)
        self.after(250, self._restore_login)

    def _label(self, parent, text, size=13, color=FG, bold=False, **kwargs):
        return ctk.CTkLabel(parent, text=text, font=("Arial", size, "bold" if bold else "normal"),
                            text_color=color, **kwargs)

    def _build(self):
        shell = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        shell.pack(fill="both", expand=True, padx=38, pady=(26, 22))
        header = ctk.CTkFrame(shell, fg_color="transparent")
        header.pack(fill="x", pady=(0, 18))
        ctk.CTkLabel(header, text="↓", width=52, height=52, corner_radius=15,
                     fg_color=ACCENT, text_color="#171717", font=("Arial", 35, "bold")).pack(side="left", padx=(0, 16))
        names = ctk.CTkFrame(header, fg_color="transparent")
        names.pack(side="left", fill="x", expand=True)
        self._label(names, "yandex downloader", size=27, bold=True).pack(anchor="w")
        self._label(names, "Музыка и плейлисты — в выбранную папку", color=MUTED).pack(anchor="w", pady=(4, 0))
        self._label(header, f"v{VERSION}", color=MUTED).pack(side="right", anchor="n")

        auth_card = ctk.CTkFrame(shell, fg_color=PANEL, corner_radius=17)
        auth_card.pack(fill="x", pady=(0, 14))
        auth_inner = ctk.CTkFrame(auth_card, fg_color="transparent")
        auth_inner.pack(fill="x", padx=22, pady=18)
        self._label(auth_inner, "01  АККАУНТ", size=12, color=ACCENT, bold=True).pack(anchor="w")
        auth_controls = ctk.CTkFrame(auth_inner, fg_color="transparent")
        auth_controls.pack(fill="x", pady=(10, 0))
        self.auth_label = self._label(auth_controls, "Не выполнен вход", size=14, color=MUTED)
        self.auth_label.pack(side="left", expand=True, anchor="w")
        self.login_button = ctk.CTkButton(auth_controls, text="Войти через Яндекс", width=190,
                        fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#141414", font=("Arial", 13, "bold"),
                        command=self.login, height=38, corner_radius=10)
        self.login_button.pack(side="right")
        self.logout_button = ctk.CTkButton(auth_controls, text="Выйти", width=74,
                         height=38, fg_color="#383D45", hover_color="#505660",
                         command=self.logout, state="disabled")
        self.logout_button.pack(side="right", padx=(0, 9))
        manual = ctk.CTkFrame(auth_inner, fg_color="transparent")
        manual.pack(fill="x", pady=(12, 0))
        self.token_entry = ctk.CTkEntry(manual, placeholder_text="Или вставьте OAuth-токен (не сохраняется)",
                            show="•", fg_color=INPUT, border_width=0, height=36, corner_radius=9)
        self.token_entry.pack(side="left", fill="x", expand=True, padx=(0, 9))
        self._setup_entry_clipboard(self.token_entry)
        ctk.CTkButton(manual, text="Подключить", width=118, height=36, fg_color="#383D45",
                      hover_color="#505660", command=self.login_token).pack(side="right")
        ctk.CTkCheckBox(auth_inner, text="Запомнить вход в защищённом хранилище системы",
                        variable=self.remember_login, fg_color=ACCENT,
                        hover_color=ACCENT_HOVER, border_color=MUTED,
                        text_color=FG, checkmark_color="#151515").pack(anchor="w", pady=(12, 0))

        task_card = ctk.CTkFrame(shell, fg_color=PANEL, corner_radius=17)
        task_card.pack(fill="x", pady=(0, 14))
        content = ctk.CTkFrame(task_card, fg_color="transparent")
        content.pack(fill="x", padx=22, pady=20)
        self._label(content, "02  СКАЧИВАНИЕ", size=12, color=ACCENT, bold=True).pack(anchor="w", pady=(0, 14))
        self._label(content, "Ссылка на трек, альбом или плейлист", size=13, bold=True).pack(anchor="w")
        link_row = ctk.CTkFrame(content, fg_color="transparent")
        link_row.pack(fill="x", pady=(7, 8))
        self.link_entry = ctk.CTkEntry(link_row, textvariable=self.link,
                     placeholder_text="https://music.yandex.ru/users/.../playlists/...",
                     fg_color=INPUT, border_width=0, height=43, corner_radius=9)
        self.link_entry.pack(side="left", fill="x", expand=True, padx=(0, 9))
        self._setup_entry_clipboard(self.link_entry)
        self.paste_button = ctk.CTkButton(link_row, text="Вставить", width=105, height=43,
                     fg_color="#383D45", hover_color="#505660", command=self.paste_link)
        self.paste_button.pack(side="right")
        self.likes_button = ctk.CTkButton(content, text="♥ Скачать «Мне нравится»", height=34,
                     width=210, fg_color="#383D45", hover_color="#505660", command=self.download_likes)
        self.likes_button.pack(anchor="w", pady=(0, 15))
        self._label(content, "Папка сохранения", size=13, bold=True).pack(anchor="w")
        folder_row = ctk.CTkFrame(content, fg_color="transparent")
        folder_row.pack(fill="x", pady=(7, 16))
        self.folder_entry = ctk.CTkEntry(folder_row, textvariable=self.folder, fg_color=INPUT,
                     border_width=0, height=43, corner_radius=9)
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 9))
        self._setup_entry_clipboard(self.folder_entry)
        ctk.CTkButton(folder_row, text="Обзор…", width=105, height=43, fg_color="#383D45",
                      hover_color="#505660", command=self.choose_folder).pack(side="right")
        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x")
        opts = ctk.CTkFrame(row, fg_color="transparent")
        opts.pack(side="left", fill="x", expand=True)
        self._label(opts, "Качество", size=13, bold=True).pack(anchor="w", pady=(0, 6))
        ctk.CTkOptionMenu(opts, variable=self.quality, values=["Высокое · MP3", "Обычное · MP3", "Lossless · FLAC (при доступности)"],
                          fg_color=INPUT, button_color="#414650", button_hover_color="#555C66",
                          width=270, height=38, corner_radius=9).pack(anchor="w")
        ctk.CTkCheckBox(row, text="Папка с названием плейлиста", variable=self.make_subfolder,
                        border_color=MUTED, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        text_color=FG, checkmark_color="#151515").pack(side="right", anchor="s", pady=(0, 8))
        buttons = ctk.CTkFrame(content, fg_color="transparent")
        buttons.pack(fill="x", pady=(21, 0))
        self.start_button = ctk.CTkButton(buttons, text="↓  Скачать", height=46, fg_color=ACCENT,
                           hover_color=ACCENT_HOVER, text_color="#141414", corner_radius=11,
                           font=("Arial", 15, "bold"), command=self.start)
        self.start_button.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.cancel_button = ctk.CTkButton(buttons, text="Отмена", height=46, width=118,
                         fg_color="#383D45", hover_color="#505660", corner_radius=11,
                         state="disabled", command=self.cancel)
        self.cancel_button.pack(side="right")

        monitor = ctk.CTkFrame(shell, fg_color=PANEL, corner_radius=17)
        monitor.pack(fill="both", expand=True)
        content = ctk.CTkFrame(monitor, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=22, pady=19)
        self._label(content, "03  ПРОГРЕСС", size=12, color=ACCENT, bold=True).pack(anchor="w", pady=(0, 8))
        self.status = self._label(content, "Ожидание ссылки", size=15, bold=True, anchor="w")
        self.status.pack(fill="x")
        self.overall = ctk.CTkProgressBar(content, height=8, progress_color=ACCENT, fg_color="#383C43")
        self.overall.pack(fill="x", pady=(13, 9))
        self.overall.set(0)
        self.detail = self._label(content, "0 / 0 треков", color=MUTED, anchor="w")
        self.detail.pack(fill="x")
        self.current = ctk.CTkProgressBar(content, height=6, progress_color="#D7DCE2", fg_color="#383C43")
        self.current.pack(fill="x", pady=(12, 8))
        self.current.set(0)
        self.speed = self._label(content, "Скорость: —       Размер: —       Осталось: —", color=MUTED, anchor="w")
        self.speed.pack(fill="x")
        self.log = ctk.CTkTextbox(content, height=115, fg_color=INPUT, corner_radius=10,
                                  text_color="#C3C8D0", font=("Consolas", 12), wrap="word")
        self.log.pack(fill="both", expand=True, pady=(15, 0))
        self.log.configure(state="disabled")

        self._label(shell, "Используйте только музыку, которую вправе сохранять. Доступность файлов определяет Яндекс Музыка.",
                    size=12, color=MUTED, wraplength=760).pack(anchor="w", pady=(14, 0))

    def _setup_entry_clipboard(self, entry):
        native = entry._entry
        for sequence in ("<Control-v>", "<Control-V>", "<Control-Shift-v>",
                         "<Control-Shift-V>", "<Shift-Insert>", "<<Paste>>"):
            native.bind(sequence, lambda event, target=native: self._paste_into(target), add="+")
        native.bind("<Button-3>", lambda event, target=native:
                    self._show_entry_context_menu(event, target), add="+")

    def _paste_into(self, native):
        paste_from_clipboard(native, self.clipboard_get)
        return "break"

    def paste_link(self):
        self.link_entry.focus_set()
        self._paste_into(self.link_entry._entry)

    def _show_entry_context_menu(self, event, native):
        native.focus_set()
        if getattr(self, "_context_menu", None) is not None:
            self._context_menu.destroy()
        menu = tk.Menu(self, tearoff=False, bg=INPUT, fg=FG,
                       activebackground=ACCENT, activeforeground="#151515")
        self._context_menu = menu
        menu.add_command(label="Вырезать", command=lambda: native.event_generate("<<Cut>>"))
        menu.add_command(label="Копировать", command=lambda: native.event_generate("<<Copy>>"))
        menu.add_command(label="Вставить", command=lambda: self._paste_into(native))
        menu.add_separator()
        menu.add_command(label="Выделить всё", command=lambda: (native.select_range(0, "end"),
                                                               native.icursor("end")))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def download_likes(self):
        self.link.set("https://music.yandex.ru/collection?type=liked")
        self.start()

    def _restore_login(self):
        if self.auth_busy or self.client is not None:
            return
        self.auth_busy = True
        self.auth_label.configure(text="Проверка сохранённого входа…", text_color=MUTED)
        self.login_button.configure(state="disabled")
        threading.Thread(target=self._auth_thread, kwargs={"restore": True}, daemon=True).start()

    def logout(self):
        if self.busy or self.auth_busy:
            return
        try:
            delete_token()
        except SecureStorageUnavailable as exc:
            self.write_log("⚠ Не удалось удалить вход из хранилища: " + str(exc))
        self.client = None
        self.auth_label.configure(text="Выполнен выход", text_color=MUTED)
        self.login_button.configure(text="Войти через Яндекс")
        self.logout_button.configure(state="disabled")
        self.write_log("■ Вы вышли из аккаунта")

    def write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder.get() if Path(self.folder.get()).is_dir() else str(Path.home()))
        if folder:
            self.folder.set(folder)

    def _auth_thread(self, token=None, restore=False, remember=True):
        try:
            from yandex_music import Client
            if restore:
                try:
                    token = load_token()
                except SecureStorageUnavailable as exc:
                    self.events.put(("auth_restore_missing", {"message": str(exc)}))
                    return
                if not token:
                    self.events.put(("auth_restore_missing", {"message": ""}))
                    return
            if token:
                access_token = token
                client = Client(token)
            else:
                client = Client()
                token_obj = client.device_auth(on_code=lambda code: self.events.put(("auth_code", {
                    "url": code.verification_url, "code": code.user_code})))
                access_token = getattr(token_obj, "access_token", None)
                if not access_token:
                    raise RuntimeError("Яндекс не подтвердил авторизацию.")
            client.init()
            if not restore:
                try:
                    if remember:
                        save_token(access_token)
                    else:
                        delete_token()
                except SecureStorageUnavailable as exc:
                    self.events.put(("auth_warning", {"message": str(exc)}))
            self.client = client
            self.events.put(("auth_ok", {"restored": restore}))
        except Exception as exc:
            # Do not erase a saved token after a network/region error: the
            # user may be able to reconnect on the next launch.
            self.events.put(("auth_error", {"message": str(exc)[:260], "restored": restore}))

    def login(self):
        if self.auth_busy or self.busy:
            return
        self.auth_busy = True
        self.login_button.configure(state="disabled", text="Авторизация…")
        self.auth_label.configure(text="Ожидание входа в аккаунт…", text_color=ACCENT)
        threading.Thread(target=self._auth_thread,
                         kwargs={"remember": self.remember_login.get()}, daemon=True).start()

    def login_token(self):
        if self.auth_busy or self.busy:
            return
        token = self.token_entry.get().strip()
        if not token:
            messagebox.showwarning("Токен", "Введите OAuth-токен или нажмите «Войти через Яндекс».")
            return
        self.token_entry.delete(0, "end")
        self.auth_busy = True
        self.login_button.configure(state="disabled")
        self.auth_label.configure(text="Проверка токена…", text_color=ACCENT)
        threading.Thread(target=self._auth_thread, args=(token,),
                         kwargs={"remember": self.remember_login.get()}, daemon=True).start()

    def start(self):
        if self.busy or self.auth_busy:
            return
        if self.client is None:
            messagebox.showwarning("Авторизация", "Сначала войдите в аккаунт Яндекса.")
            return
        try:
            parse_link(self.link.get())
        except InvalidMusicURL as exc:
            messagebox.showerror("Ссылка", str(exc))
            return
        output = Path(self.folder.get()).expanduser()
        try:
            output.mkdir(parents=True, exist_ok=True)
            if not output.is_dir():
                raise ValueError("Это не папка")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Папка", f"Невозможно использовать эту папку: {exc}")
            return
        self.busy = True
        self.cancel_event.clear()
        self.start_button.configure(state="disabled", text="Скачивание…")
        self.cancel_button.configure(state="normal")
        self.overall.set(0)
        self.current.set(0)
        quality = "lossless" if "Lossless" in self.quality.get() else "nq" if "Обычное" in self.quality.get() else "hq"
        self.write_log("▶ Новая задача")
        threading.Thread(target=self._download_thread, args=(self.link.get(), output, quality, self.make_subfolder.get()), daemon=True).start()

    def _download_thread(self, url, output, quality, subfolder):
        try:
            download_all(self.client, url, output, quality, subfolder,
                         lambda kind, data: self.events.put((kind, data)), self.cancel_event)
        except Exception as exc:
            self.events.put(("fatal", {"message": str(exc)[:260]}))

    def cancel(self):
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status.configure(text="Остановка после текущего действия…")

    def _set_idle(self):
        self.busy = False
        self.start_button.configure(state="normal", text="↓  Скачать")
        self.cancel_button.configure(state="disabled")

    def _poll(self):
        try:
            for _ in range(200):
                kind, data = self.events.get_nowait()
                if kind == "auth_code":
                    url, code = data["url"], data["code"]
                    popup = ctk.CTkToplevel(self)
                    popup.title("Вход через Яндекс")
                    popup.geometry("455x235")
                    popup.attributes("-topmost", True)
                    self._label(popup, "Откройте сайт и введите код", size=19, bold=True).pack(pady=(23, 10))
                    self._label(popup, code, size=29, bold=True, color=ACCENT).pack(pady=7)
                    ctk.CTkButton(popup, text="Открыть страницу входа", fg_color=ACCENT, text_color="#171717",
                                  hover_color=ACCENT_HOVER, command=lambda url=url: webbrowser.open(url)).pack(pady=14)
                    self._label(popup, "После подтверждения окно можно закрыть", color=MUTED).pack()
                    webbrowser.open(url)
                elif kind == "auth_ok":
                    self.auth_busy = False
                    self.login_button.configure(state="normal", text="Войти снова")
                    self.logout_button.configure(state="normal")
                    self.auth_label.configure(text="● Аккаунт подключён", text_color="#80E4AD")
                    self.write_log("✓ Вход восстановлен" if data.get("restored") else "✓ Вход выполнен")
                elif kind == "auth_restore_missing":
                    self.auth_busy = False
                    self.login_button.configure(state="normal", text="Войти через Яндекс")
                    self.auth_label.configure(text="Не выполнен вход", text_color=MUTED)
                    if data.get("message"):
                        self.write_log("ℹ Автовход недоступен: " + data["message"])
                elif kind == "auth_warning":
                    self.write_log("⚠ Вход выполнен, но не сохранён: " + data["message"])
                elif kind == "auth_error":
                    self.auth_busy = False
                    self.login_button.configure(state="normal", text="Войти через Яндекс")
                    self.auth_label.configure(text="Сохранённый вход истёк" if data.get("restored") else "Не удалось авторизоваться", text_color="#FFA6A6")
                    self.write_log("✕ Ошибка входа: " + data["message"])
                elif kind == "resolved":
                    self.write_log(f"Найдено {data['count']} треков · {data['title']}")
                    self.detail.configure(text=f"0 / {data['count']} треков")
                elif kind == "track":
                    self.status.configure(text=data["name"][:100])
                    self.detail.configure(text=f"Трек {data['index']} из {data['count']}")
                    self.current.set(0)
                    self.speed.configure(text="Скорость: —       Размер: —       Осталось: —")
                elif kind == "bytes":
                    got, total, speed = data["got"], data["total"], data["speed"]
                    if total:
                        self.current.set(min(1, got / total))
                    self.speed.configure(text=f"Скорость: {human_bytes(speed)}/с       Загружено: {human_bytes(got)}"
                                              f" / {human_bytes(total)}       Осталось: {format_eta((total-got)/speed) if total and speed and speed > 0 else '—'}")
                elif kind == "saved":
                    self.current.set(1)
                    self.write_log(f"✓ {data['name']} · {human_bytes(data['size'])}")
                elif kind == "skipped":
                    self.current.set(1)
                    self.write_log(f"↷ Уже скачано: {data['name']}")
                elif kind == "error":
                    self.write_log(f"✕ {data['name']}: {data['message']}")
                elif kind == "overall":
                    self.overall.set(data["index"] / data["count"])
                    self.detail.configure(text=f"Обработано {data['index']} / {data['count']} треков")
                elif kind == "finished":
                    self._set_idle()
                    self.status.configure(text=f"Готово: {data['done']} загружено, {data['skipped']} пропущено, {data['failed']} ошибок")
                    self.write_log("■ Готово · папка: " + data["folder"])
                    if data["failed"]:
                        messagebox.showwarning("Частично завершено", f"Не удалось скачать: {data['failed']} трек(ов). Проверьте журнал.")
                elif kind == "cancelled":
                    self._set_idle()
                    self.status.configure(text="Загрузка остановлена")
                    self.write_log("■ Отменено")
                elif kind == "fatal":
                    self._set_idle()
                    self.status.configure(text="Ошибка задания")
                    self.write_log("✕ " + data["message"])
                    messagebox.showerror("Не удалось скачать", data["message"])
        except queue.Empty:
            pass
        self.after(100, self._poll)


if __name__ == "__main__":
    App().mainloop()