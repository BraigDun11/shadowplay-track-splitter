# -*- coding: utf-8 -*-
"""ShadowPlay Track Splitter - window.  Run: python gui.py   (or the built .exe)

The whole window is one canvas that is redrawn from a small state (see App.render):
  empty   - nothing chosen yet: big "drop a video here / click to choose" card
  ready   - a video is chosen: frame, name, mode, options, Start
  working - the job runs: progress bar and the current step
  done    - finished: "Done!" and the buttons that open the folders
"""
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import font as tkfont

import core

try:  # drag & drop of files into the window (optional)
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAVE_DND = True
except Exception:  # pragma: no cover
    DND_FILES = TkinterDnD = None
    HAVE_DND = False

APP_VERSION = "1.4.2"

# palette taken from the design mock-ups
GREEN = "#55D900"
BG = "#131313"
PANEL = "#363636"
PANEL_HI = "#464646"
MENU_BG = "#2A2A2A"
WHITE = "#FFFFFF"
GRAY = "#9A9A9A"
DIM = "#5A5A5A"
RED = "#FF6B6B"

W, H = 780, 700            # client size at 100 % scaling

UI = {
    "en": {
        "title": "ShadowPlay Track Splitter",
        "drop": "Drop a video here or click to choose",
        "modes": ["Split mixed audio tracks", "Extract audio tracks from a normal video"],
        "swap": "Swap the audio tracks",
        "stretch": "Stretch video to the audio length",
        "save": "Save audio tracks as separate files",
        "video_sound": "Sound in the video",
        "no_audio": "No sound",
        "all": "All",
        "pc": "PC",
        "mic": "Microphone",
        "start": "Start",
        "working": "Working...",
        "done": "Done!",
        "failed": "Something went wrong",
        "open": "Open folder",
        "reports": "Reports folder",
        "ffmpeg_ok": "app version v%s",
        "ffmpeg_no": "ffmpeg not found - click to choose ffmpeg.exe",
        "ffmpeg_dialog": "Choose ffmpeg.exe",
        "no_ffmpeg": "ffmpeg was not found.\nDownload it from https://www.gyan.dev/ffmpeg/builds/ (essentials build) "
                     "and either put ffmpeg.exe next to this program or choose it in the settings (the gear in the corner).",
        "nothing_to_do": "Nothing to do: the video already has this single track. "
                         "Choose \"No sound\" or tick \"Save audio tracks as separate files\".",
        "error": "Error",
        "report": "A report was saved: {p}",
        "video_types": "Video files",
        "all_types": "All files",
        "checking": "Checking the file...",
        "hint_repair": "Looks like a video repaired with untrunc: PC and microphone are mixed in one track.",
        "hint_extract": "The video has normal audio tracks ({n}).",
        "hint_unreadable": "Could not read this file. If it is the original damaged recording, repair it first.",
        "empty_track": " (empty)",
        "settings": "Settings",
        "out_folder": "Folder for repaired videos",
        "change": "Change",
        "reset_default": "Back to default folder",
        "free": "Free space: {gb:.1f} GB",
        "ffmpeg_title": "ffmpeg",
        "ffmpeg_installed": "Installed",
        "ffmpeg_missing": "Not found - it is needed to work with video",
        "choose": "Choose...",
        "close": "Done",
        "audio_only": "Audio only",
        "tracks_info": "Audio tracks in the file: {n}.",
        "pick_folder": "Choose the folder for repaired videos",
        "need_space": "Not enough free space on drive {where}: about {need:.1f} GB needed, {free:.1f} GB free.\n\n"
                      "Free up space or choose another folder in the settings (gear). Open the settings now?",
    },
    "ru": {
        "title": "ShadowPlay Track Splitter",
        "drop": "Перетащи или нажми, чтобы выбрать",
        "modes": ["Разделить смешанные аудиодорожки", "Достать аудиодорожки из обычного видео"],
        "swap": "Поменять аудиодорожки местами",
        "stretch": "Растянуть видео под длину звука",
        "save": "Сохранить аудиодорожки отдельными файлами",
        "video_sound": "Звук в видео",
        "no_audio": "Без звука",
        "all": "Все",
        "pc": "ПК",
        "mic": "Микрофон",
        "start": "Начать",
        "working": "Работаю...",
        "done": "Готово!",
        "failed": "Что-то пошло не так",
        "open": "Открыть папку",
        "reports": "Папка отчетов",
        "ffmpeg_ok": "версия приложения v%s",
        "ffmpeg_no": "ffmpeg не найден - нажми, чтобы указать ffmpeg.exe",
        "ffmpeg_dialog": "Выберите ffmpeg.exe",
        "no_ffmpeg": "Не найден ffmpeg.\nСкачайте его на https://www.gyan.dev/ffmpeg/builds/ (essentials) и либо "
                     "положите ffmpeg.exe рядом с программой, либо выберите его в настройках (шестерёнка в углу).",
        "nothing_to_do": "Нечего делать: в видео уже лежит эта единственная дорожка. "
                         "Выберите «Без звука» или включите «Сохранить аудиодорожки отдельными файлами».",
        "error": "Ошибка",
        "report": "Отчёт сохранён: {p}",
        "video_types": "Видеофайлы",
        "all_types": "Все файлы",
        "checking": "Проверяю файл...",
        "hint_repair": "Похоже на видео, восстановленное untrunc: ПК и микрофон смешаны в одной дорожке.",
        "hint_extract": "В видео обычные аудиодорожки ({n}).",
        "hint_unreadable": "Не получилось прочитать файл. Если это исходная повреждённая запись, сначала восстановите её.",
        "empty_track": " (пустая)",
        "settings": "Настройки",
        "out_folder": "Папка для восстановленных видео",
        "change": "Изменить",
        "reset_default": "Вернуть папку по умолчанию",
        "free": "Свободно на диске: {gb:.1f} ГБ",
        "ffmpeg_title": "ffmpeg",
        "ffmpeg_installed": "Установлен",
        "ffmpeg_missing": "Не найден - он нужен для работы с видео",
        "choose": "Указать...",
        "close": "Готово",
        "audio_only": "Только звук",
        "tracks_info": "Аудиодорожек в файле: {n}.",
        "pick_folder": "Выберите папку для восстановленных видео",
        "need_space": "Не хватает места на диске {where}: нужно примерно {need:.1f} ГБ, свободно {free:.1f} ГБ.\n\n"
                      "Освободите место или выберите другую папку в настройках (шестерёнка). Открыть настройки сейчас?",
    },
}


def asset(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


class App:
    # ------------------------------------------------------------ setup
    def __init__(self, root, preset=None):
        self.root = root
        self.lang = core.detect_lang()
        self.t = UI[self.lang]
        self.q = queue.Queue()
        self.cfg = core.load_settings()
        self.ffmpeg = core.find_ffmpeg(self.cfg.get("ffmpeg")) or core.find_ffmpeg()
        self.settings_open = False

        try:
            self.k = max(1.0, root.winfo_fpixels("1i") / 96.0)
        except Exception:
            self.k = 1.0
        S = self.S
        root.title(self.t["title"])
        root.configure(bg=BG)
        root.geometry("%dx%d" % (S(W), S(H)))
        root.resizable(False, False)
        self.set_icon()
        self.f_big = tkfont.Font(family="Segoe UI", size=-S(17), weight="bold")
        self.f_med = tkfont.Font(family="Segoe UI", size=-S(15), weight="bold")
        self.f_small = tkfont.Font(family="Segoe UI", size=-S(12), weight="bold")
        self.f_tiny = tkfont.Font(family="Segoe UI", size=-S(11), weight="bold")

        self.cv = tk.Canvas(root, width=S(W), height=S(H), bg=BG, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Button-1>", self.on_click)
        self.cv.bind("<Motion>", self.on_motion)
        self.cv.bind("<Leave>", lambda e: self.set_hover(None))

        # state
        self.state = "empty"
        self.video = ""
        self.thumb = None
        self.streams = []
        self.mode = 0                       # 0 = split mixed tracks, 1 = extract
        self.swap = False
        self.stretch = True
        self.save = False
        self.save_choice = 0                # repair: 0 both / 1 PC / 2 mic ; extract: 0 all / i = track i
        self.keep_idx = 0                   # extract: 0 = no sound, i = track i stays in the video
        self.progress = 0.0
        self.status = ""
        self.status_color = GRAY
        self.out_dir = None
        self.lines = []
        self.probe_token = 0
        self.hits = []
        self.hover = None
        self.menu = None                    # open drop-down: dict(items, x, y, w, cb)

        self.setup_dnd()
        self.render()
        self.root.after(150, self.paint_title_bar)
        self.root.after(100, self.poll)
        if preset:
            self.set_video(preset)

    def S(self, v):
        return int(round(v * self.k))

    def set_icon(self):
        try:
            self.icon_img = tk.PhotoImage(file=asset("icon_64.png"))
            self.root.iconphoto(True, self.icon_img)
        except Exception:
            pass
        if os.name == "nt":
            try:
                self.root.iconbitmap(asset("icon.ico"))
            except Exception:
                pass

    def paint_title_bar(self):
        """Windows 11: green title bar like in the design (silently ignored elsewhere)."""
        if os.name != "nt":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            def put(attr, r, g, b):
                val = ctypes.c_int(r | (g << 8) | (b << 16))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4)
            put(35, 0x55, 0xD9, 0x00)    # caption colour
            put(36, 0x13, 0x13, 0x13)    # caption text colour
            put(34, 0x55, 0xD9, 0x00)    # border colour
        except Exception:
            pass

    def setup_dnd(self):
        if not HAVE_DND:
            return
        try:
            for w in (self.root, self.cv):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self.on_drop)
        except Exception:
            pass

    def on_drop(self, event):
        try:
            files = self.root.tk.splitlist(event.data)
        except Exception:
            files = [event.data]
        for f in files:
            f = str(f).strip().strip("{}")
            if os.path.isfile(f):
                self.set_video(f)
                break
        return event.action if hasattr(event, "action") else None

    # ------------------------------------------------------------ drawing helpers
    def rrect(self, x1, y1, x2, y2, r, fill, outline="", tags=()):
        S = self.S
        x1, y1, x2, y2, r = S(x1), S(y1), S(x2), S(y2), S(r)
        r = min(r, (x2 - x1) // 2, (y2 - y1) // 2)
        pts = [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r,
               x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
               x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]
        return self.cv.create_polygon(pts, smooth=True, fill=fill, outline=outline, tags=tags)

    def text(self, x, y, s, font, fill=WHITE, anchor="w"):
        return self.cv.create_text(self.S(x), self.S(y), text=s, font=font, fill=fill, anchor=anchor)

    def chevron(self, cx, cy, color=WHITE, size=5):
        S = self.S
        self.cv.create_line(S(cx - size / 2), S(cy - size), S(cx + size / 2), S(cy), S(cx - size / 2), S(cy + size),
                            fill=color, width=max(2, S(2)), capstyle="round", joinstyle="round")

    def add_hit(self, x1, y1, x2, y2, fn, key=None):
        self.hits.append((self.S(x1), self.S(y1), self.S(x2), self.S(y2), fn, key))

    def hovered(self, key):
        return self.hover == key

    def pill(self, x1, y1, x2, y2, label, fn, key, fill=PANEL, color=WHITE, font=None, chevron=False,
             center=True, enabled=True):
        font = font or self.f_med
        hi = enabled and self.hovered(key)
        self.rrect(x1, y1, x2, y2, (y2 - y1) / 2, PANEL_HI if hi and fill == PANEL else fill)
        cy = (y1 + y2) / 2
        if center:
            self.text((x1 + x2) / 2 - (8 if chevron else 0), cy, label, font, color, "center")
        else:
            self.text(x1 + 16, cy, label, font, color, "w")
        if chevron:
            self.chevron(x2 - 20, cy, color)
        if enabled:
            self.add_hit(x1, y1, x2, y2, fn, key)

    def dropdown(self, right, cy, label, items, current, cb, key, h=30):
        """Pill with a chevron, right edge at `right`; the width follows the text."""
        S = self.S
        w = int(self.f_small.measure(label) / self.k) + 54
        x1 = right - w
        self.pill(x1, cy - h / 2, right, cy + h / 2, label, lambda: self.open_menu(items, x1, cy + h / 2 + 4, w, cb),
                  key, font=self.f_small, chevron=True)

    def checkbox(self, x, cy, label, value, fn, key, enabled=True):
        hi = enabled and self.hovered(key)
        size = 26
        col = GREEN if value else (PANEL_HI if hi else PANEL)
        self.rrect(x, cy - size / 2, x + size, cy + size / 2, 6, col)
        if value:
            S = self.S
            self.cv.create_line(S(x + 6), S(cy), S(x + 11), S(cy + 5), S(x + 20), S(cy - 5), fill=BG,
                                width=max(2, S(3)), capstyle="round", joinstyle="round")
        self.text(x + 40, cy, label, self.f_small, WHITE if enabled else DIM, "w")
        if enabled:
            wlab = int(self.f_small.measure(label) / self.k) + 40
            self.add_hit(x, cy - 16, x + wlab, cy + 16, fn, key)

    # ------------------------------------------------------------ the picture
    def render(self):
        S = self.S
        self.cv.delete("all")
        self.hits = []
        t = self.t
        working = self.state == "working"
        if self.settings_open:
            self.render_settings()
            return
        self.render_gear(working)

        # card with the frame / drop zone
        self.rrect(110, 32, 670, 247, 28, PANEL)
        if self.state == "empty":
            self.rrect(325, 96, 455, 182, 20, GREEN)
            self.cv.create_polygon(S(377), S(123), S(377), S(155), S(409), S(139), fill=PANEL, outline=PANEL)
            self.text(390, 266, t["drop"], self.f_big, WHITE, "center")
            self.add_hit(110, 32, 670, 300, self.choose_file, "card")
        else:
            if self.thumb is not None:
                self.cv.create_image(S(390), S(139), image=self.thumb)
            else:
                self.rrect(325, 96, 455, 182, 20, GREEN)
                self.cv.create_polygon(S(377), S(123), S(377), S(155), S(409), S(139), fill=PANEL, outline=PANEL)
            name = os.path.splitext(os.path.basename(self.video))[0]
            self.text(390, 266, self.fit(name, self.f_big, 560), self.f_big, WHITE, "center")
            if not working:
                self.add_hit(110, 32, 670, 280, self.choose_file, "card")

        if self.state != "empty":
            self.render_options(working)
            self.render_bottom(working)
        self.render_ffmpeg()
        if self.menu:
            self.render_menu()

    def fit(self, s, font, max_w):
        mw = self.S(max_w)
        if font.measure(s) <= mw:
            return s
        while len(s) > 3 and font.measure(s + "...") > mw:
            s = s[:-1]
        return s + "..."

    def render_options(self, working):
        t = self.t
        ok = not working
        # mode selector
        self.pill(110, 296, 670, 328, t["modes"][self.mode], lambda: self.open_menu(
            t["modes"], 110, 332, 560, self.set_mode), "mode", font=self.f_med, chevron=True, center=False,
            enabled=ok)
        y = 360
        if self.mode == 0:
            self.checkbox(110, y, t["swap"], self.swap, lambda: self.toggle("swap"), "swap", ok)
            self.checkbox(110, y + 40, t["stretch"], self.stretch, lambda: self.toggle("stretch"), "stretch", ok)
            self.checkbox(110, y + 80, t["save"], self.save, lambda: self.toggle("save"), "save", ok)
            if ok:
                items = [t["all"], t["pc"], t["mic"]]
                self.dropdown(670, y + 80, items[self.save_choice], items, self.save_choice, self.set_save_choice,
                              "save_dd")
        else:
            n = len(self.streams)
            if n == 1:
                items = [t["no_audio"], t["audio_only"]]
            else:
                items = [t["no_audio"]] + [self.track_label(s) for s in self.streams]
            self.keep_idx = min(self.keep_idx, len(items) - 1)
            self.text(110, y, t["video_sound"], self.f_small, WHITE, "w")
            if ok:
                self.dropdown(670, y, items[self.keep_idx], items, self.keep_idx, self.set_keep, "keep_dd")
            else:
                self.text(670, y, items[self.keep_idx], self.f_small, GRAY, "e")
            if n == 1:
                # one track: saving it is part of the choice above, so the box is shown but locked
                self.checkbox(110, y + 40, t["save"], True, lambda: None, "save", False)
            else:
                self.checkbox(110, y + 40, t["save"], self.save, lambda: self.toggle("save"), "save", ok)
                sitems = [t["all"]] + [self.track_label(s) for s in self.streams]
                self.save_choice = min(self.save_choice, len(sitems) - 1)
                if ok:
                    self.dropdown(670, y + 40, sitems[self.save_choice], sitems, self.save_choice,
                                  self.set_save_choice, "save_dd")

    def render_bottom(self, working):
        t = self.t
        y0 = 460 if self.mode == 1 else 500
        self.start_y = y0
        if working:
            self.rrect(210, y0, 570, y0 + 34, 17, "#2E5A10")
            self.text(390, y0 + 17, t["working"], self.f_med, GRAY, "center")
        else:
            hi = self.hovered("start")
            self.rrect(210, y0, 570, y0 + 34, 17, "#6BF000" if hi else GREEN)
            self.text(390, y0 + 17, t["start"], self.f_med, WHITE, "center")
            self.add_hit(210, y0, 570, y0 + 34, self.start, "start")
        # progress
        yb = y0 + 54
        self.rrect(110, yb, 670, yb + 20, 4, PANEL)
        if self.progress > 0:
            self.rrect(110, yb, 110 + max(10, 560 * self.progress), yb + 20, 4, GREEN)
        self.text(110, yb + 32, self.fit(self.status, self.f_tiny, 560), self.f_tiny, self.status_color, "w")
        # buttons
        yb2 = yb + 62
        done = self.state == "done"
        self.pill(180, yb2, 380, yb2 + 32, t["open"], self.open_folder, "open", font=self.f_med,
                  color=WHITE if done else DIM, enabled=done)
        self.pill(400, yb2, 600, yb2 + 32, t["reports"], self.open_reports, "reports", font=self.f_med,
                  color=WHITE)

    def render_ffmpeg(self):
        if self.ffmpeg:
            self.text(390, H - 16, self.t["ffmpeg_ok"] % APP_VERSION, self.f_tiny, DIM, "center")
        else:
            self.text(390, H - 16, self.t["ffmpeg_no"], self.f_tiny, RED, "center")
            self.add_hit(150, H - 30, 630, H, self.pick_ffmpeg, "ffmpeg")

    # ------------------------------------------------------------ gear + settings
    def gear(self, cx, cy, color, r=13):
        """A small gear drawn from a polygon: 8 teeth and a hole."""
        S = self.S
        pts = []
        teeth = 8
        for k in range(teeth):
            a0 = 2 * math.pi * k / teeth
            for da, rad in ((-0.30, r * 0.72), (-0.16, r), (0.16, r), (0.30, r * 0.72)):
                a = a0 + da
                pts += [S(cx + rad * math.cos(a)), S(cy + rad * math.sin(a))]
        self.cv.create_polygon(pts, fill=color, outline=color, smooth=False)
        self.cv.create_oval(S(cx - r * 0.72), S(cy - r * 0.72), S(cx + r * 0.72), S(cy + r * 0.72),
                            fill=color, outline=color)
        self.cv.create_oval(S(cx - r * 0.32), S(cy - r * 0.32), S(cx + r * 0.32), S(cy + r * 0.32),
                            fill=BG, outline=BG)

    def render_gear(self, working):
        hi = self.hovered("gear")
        self.gear(738, 30, WHITE if hi else GRAY)
        if not working:
            self.add_hit(716, 8, 760, 52, self.open_settings, "gear")

    def open_settings(self):
        self.settings_open = True
        self.menu = None
        self.render()

    def close_settings(self):
        self.settings_open = False
        self.render()

    def out_dir_cfg(self):
        return self.cfg.get("out_dir") or core.default_out_dir()

    def save_cfg(self):
        core.save_settings(self.cfg)

    def choose_out_dir(self):
        cur = self.out_dir_cfg()
        init = cur if os.path.isdir(cur) else core.documents_dir()
        p = filedialog.askdirectory(title=self.t["pick_folder"], initialdir=init)
        if p:
            self.cfg["out_dir"] = os.path.normpath(p)
            self.save_cfg()
            self.render()

    def reset_out_dir(self):
        self.cfg.pop("out_dir", None)
        self.save_cfg()
        self.render()

    def choose_ffmpeg(self):
        p = filedialog.askopenfilename(title=self.t["ffmpeg_dialog"],
                                       filetypes=[("ffmpeg", "ffmpeg*"), (self.t["all_types"], "*.*")])
        if p:
            found = core.find_ffmpeg(p)
            if found:
                self.ffmpeg = found
                self.cfg["ffmpeg"] = found
                self.save_cfg()
                if self.video:
                    self.set_video(self.video)
            self.render()

    def render_settings(self):
        t = self.t
        self.text(390, 52, t["settings"], self.f_big, WHITE, "center")
        # output folder
        self.rrect(110, 96, 670, 236, 24, PANEL)
        self.text(134, 122, t["out_folder"], self.f_small, GRAY, "w")
        path = self.out_dir_cfg()
        self.text(134, 156, self.fit(path, self.f_med, 400), self.f_med, WHITE, "w")
        free = core.free_bytes(path)
        if free is not None:
            gb = free / 1024 ** 3
            self.text(134, 192, t["free"].format(gb=gb), self.f_tiny, RED if gb < 5 else GRAY, "w")
        self.pill(550, 140, 650, 172, t["change"], self.choose_out_dir, "chg", fill=BG, font=self.f_small)
        if self.cfg.get("out_dir"):
            self.text(134, 214, t["reset_default"], self.f_tiny, GREEN, "w")
            self.add_hit(134, 204, 134 + int(self.f_tiny.measure(t["reset_default"]) / self.k), 224,
                         self.reset_out_dir, "reset")
        # ffmpeg
        self.rrect(110, 262, 670, 372, 24, PANEL)
        self.text(134, 288, t["ffmpeg_title"], self.f_small, GRAY, "w")
        if self.ffmpeg:
            self.text(134, 320, t["ffmpeg_installed"], self.f_med, GREEN, "w")
            shown = self.ffmpeg if os.path.isabs(self.ffmpeg) else (shutil.which(self.ffmpeg) or self.ffmpeg)
            self.text(134, 348, self.fit(shown, self.f_tiny, 400), self.f_tiny, GRAY, "w")
        else:
            self.text(134, 320, self.fit(t["ffmpeg_missing"], self.f_med, 400), self.f_med, RED, "w")
        self.pill(550, 306, 650, 338, t["choose"], self.choose_ffmpeg, "ffm", fill=BG, font=self.f_small)
        # close
        hi = self.hovered("close")
        self.rrect(260, 600, 520, 634, 17, "#6BF000" if hi else GREEN)
        self.text(390, 617, t["close"], self.f_med, WHITE, "center")
        self.add_hit(260, 600, 520, 634, self.close_settings, "close")
        if self.menu:
            self.render_menu()

    # ------------------------------------------------------------ drop-down menu
    def open_menu(self, items, x, y, w, cb):
        h = 32 * len(items) + 8
        if y + h > H - 8:                    # not enough room below: open upwards
            y = max(8, y - h - 44)
        self.menu = dict(items=items, x=x, y=y, w=max(w, 120), cb=cb)
        self.hover = None
        self.render()

    def render_menu(self):
        m = self.menu
        S = self.S
        h = 32 * len(m["items"]) + 8
        self.rrect(m["x"], m["y"], m["x"] + m["w"], m["y"] + h, 14, MENU_BG, outline=GREEN)
        hits = []
        for i, it in enumerate(m["items"]):
            y1 = m["y"] + 4 + 32 * i
            if self.hovered(("m", i)):
                self.rrect(m["x"] + 4, y1, m["x"] + m["w"] - 4, y1 + 32, 12, PANEL_HI)
            self.text(m["x"] + 16, y1 + 16, it, self.f_small, WHITE, "w")
            hits.append((S(m["x"]), S(y1), S(m["x"] + m["w"]), S(y1 + 32), (lambda i=i: self.pick(i)), ("m", i)))
        self.hits = hits                     # while a menu is open only its items are clickable

    def pick(self, i):
        cb = self.menu["cb"]
        self.menu = None
        cb(i)
        self.render()

    # ------------------------------------------------------------ events
    def hit_at(self, x, y):
        for x1, y1, x2, y2, fn, key in reversed(self.hits):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return fn, key
        return None, None

    def on_click(self, e):
        fn, key = self.hit_at(e.x, e.y)
        if self.menu is not None and fn is None:
            self.menu = None
            self.render()
            return
        if fn:
            fn()

    def on_motion(self, e):
        fn, key = self.hit_at(e.x, e.y)
        self.cv.configure(cursor="hand2" if fn else "")
        self.set_hover(key)

    def set_hover(self, key):
        if key != self.hover:
            self.hover = key
            self.render()

    def toggle(self, name):
        setattr(self, name, not getattr(self, name))
        self.render()

    def set_mode(self, i):
        self.mode = i
        if i == 1:
            self.extract_defaults()
        else:
            self.save, self.save_choice = False, 0
        self.render()

    def set_save_choice(self, i):
        self.save_choice = i
        self.save = True

    def set_keep(self, i):
        self.keep_idx = i

    def track_label(self, s):
        title = " %s" % s["title"] if s.get("title") else ""
        note = self.t["empty_track"] if s.get("mb", 1) < 0.01 else ""
        return "%d.  %s%s%s" % (s["index"] + 1, str(s["codec"]).upper(), title, note)

    def extract_defaults(self):
        n = len(self.streams)
        self.save = True
        if n >= 2:
            self.keep_idx = 1                # first track stays in the video
            self.save_choice = 2             # the second track goes to a file
        else:
            self.keep_idx = 0                # one track: silent video + the audio as a file
            self.save_choice = 0

    # ------------------------------------------------------------ choosing a file
    def choose_file(self):
        p = filedialog.askopenfilename(filetypes=[(self.t["video_types"], "*.mp4 *.mov *.mkv *.m4v"),
                                                  (self.t["all_types"], "*.*")])
        if p:
            self.set_video(p)

    def set_video(self, path):
        if self.state == "working":
            return
        self.video = path
        self.state = "ready"
        self.thumb = None
        self.streams = []
        self.progress = 0.0
        self.lines = []
        self.status, self.status_color = self.t["checking"], GRAY
        self.probe_token += 1
        self.render()
        if self.ffmpeg:
            threading.Thread(target=self.probe_worker, args=(self.probe_token, path, self.ffmpeg),
                             daemon=True).start()
        else:
            self.status, self.status_color = "", GRAY

    def probe_worker(self, token, video, ffmpeg):
        try:
            streams = core.probe_audio(ffmpeg, video, self.lang)
        except Exception:
            streams = None
        self.q.put(("probe", (token, streams)))
        # a frame for the card
        try:
            out = os.path.join(tempfile.gettempdir(), "tracksplit_thumb_%d.png" % os.getpid())
            S = self.S
            vf = "scale=%d:%d:force_original_aspect_ratio=decrease" % (S(520), S(195))
            for ss in ("3", "0"):
                if os.path.exists(out):
                    os.remove(out)
                core._run([ffmpeg, "-y", "-v", "error", "-ss", ss, "-i", video, "-frames:v", "1", "-vf", vf, out])
                if os.path.exists(out) and os.path.getsize(out) > 0:
                    self.q.put(("thumb", (token, out)))
                    return
        except Exception:
            pass

    def apply_probe(self, token, streams):
        if token != self.probe_token:
            return
        if streams is None:
            self.status, self.status_color = self.t["hint_unreadable"], RED
            self.render()
            return
        self.streams = streams
        self.extract_defaults()
        if self.mode == 0:
            self.save, self.save_choice = False, 0
        self.status, self.status_color = self.t["tracks_info"].format(n=len(streams)), GRAY
        self.render()

    def apply_thumb(self, token, path):
        if token != self.probe_token:
            return
        try:
            self.thumb = tk.PhotoImage(file=path)
        except Exception:
            self.thumb = None
        self.render()

    def pick_ffmpeg(self):
        self.open_settings()

    # ------------------------------------------------------------ folders
    def _open(self, path):
        try:
            if os.name == "nt":
                os.startfile(path)  # noqa
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def open_folder(self):
        if self.out_dir:
            self._open(self.out_dir)

    def open_reports(self):
        self._open(core.reports_dir())

    # ------------------------------------------------------------ run
    def start(self):
        t = self.t
        if not self.video or not os.path.isfile(self.video):
            self.state = "empty"
            self.render()
            return
        if not self.ffmpeg:
            messagebox.showerror(t["error"], t["no_ffmpeg"])
            return
        n = len(self.streams)
        if self.mode == 1 and not n:
            messagebox.showinfo(t["title"], t["hint_unreadable"])
            return
        opts = dict(mode=self.mode, video=self.video, ffmpeg=self.ffmpeg)
        if self.mode == 0:
            opts.update(swap=self.swap, stretch=self.stretch, save=self.save,
                        which=["both", "pc", "mic"][min(self.save_choice, 2)])
        else:
            if n == 1:
                # "No sound": silent video + the audio file;  "Audio only": just the audio file
                keep = -1 if self.keep_idx == 0 else 0
                save_tracks = [0]
            else:
                keep = self.keep_idx - 1                   # 0 in the list = "no sound" -> -1
                if not self.save:
                    save_tracks = []
                elif self.save_choice == 0:
                    save_tracks = list(range(n))
                else:
                    save_tracks = [self.save_choice - 1]
            opts.update(keep=keep, save_tracks=save_tracks)
        out_dir = self.out_dir_cfg()
        opts["out_dir"] = out_dir
        # enough room for the result?  (a full disk used to leave a half-written video)
        need = core.needed_space(self.video, self.streams, "repair" if self.mode == 0 else "extract",
                                 keep=opts.get("keep", -1), save_tracks=opts.get("save_tracks", ()),
                                 save_audio=bool(opts.get("save")))
        free = core.free_bytes(out_dir)
        if free is not None and free < need:
            drive = os.path.splitdrive(os.path.abspath(out_dir))[0] or out_dir
            gb = 1024 ** 3
            if messagebox.askyesno(t["error"], t["need_space"].format(where=drive, need=need / gb, free=free / gb)):
                self.open_settings()
            return
        self.out_dir = out_dir
        self.lines = []
        self.progress = 0.0
        self.status, self.status_color = t["working"], WHITE
        self.state = "working"
        self.render()
        threading.Thread(target=self.worker, args=(opts,), daemon=True).start()

    def worker(self, o):
        log = lambda s: self.q.put(("log", s))
        prog = lambda f: self.q.put(("progress", f))
        try:
            if o["mode"] == 1:
                core.extract_tracks(o["video"], ffmpeg=o["ffmpeg"], keep=o["keep"], save_tracks=o["save_tracks"],
                                    log=log, progress=prog, lang=self.lang, out_dir=o["out_dir"])
            else:
                core.process(o["video"], ffmpeg=o["ffmpeg"], swap=o["swap"], match_video=o["stretch"],
                             log=log, progress=prog, lang=self.lang, save_audio_files=o["save"],
                             audio_which=o["which"], out_dir=o["out_dir"])
            self.q.put(("done", o["video"]))
        except core.SplitError as e:
            self.q.put(("error", (o["video"], str(e))))
        except Exception as e:  # unexpected
            import traceback
            self.q.put(("error", (o["video"], "%s\n%s" % (e, traceback.format_exc()))))

    def save_report(self, video):
        try:
            core.save_report(video, self.lines, APP_VERSION)
        except Exception:
            pass

    def step_text(self, line):
        line = line.strip()
        if not line or line.startswith(("DONE", "ГОТОВО", "Audio files", "Аудиофайлы", "Tracks separately")):
            return None
        return re.sub(r"\s+", " ", line)

    def poll(self):
        dirty = False
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.lines.append(val)
                    if self.state == "working" and not val.startswith(" "):
                        s = self.step_text(val)
                        if s:
                            self.status, self.status_color = s, WHITE
                            dirty = True
                elif kind == "progress":
                    self.progress = float(val)
                    dirty = True
                elif kind == "probe":
                    self.apply_probe(*val)
                elif kind == "thumb":
                    self.apply_thumb(*val)
                elif kind == "done":
                    self.state = "done"
                    self.progress = 1.0
                    self.status, self.status_color = self.t["done"], GREEN
                    self.save_report(val)
                    dirty = True
                elif kind == "error":
                    video, msg = val
                    self.state = "ready"
                    self.progress = 0.0
                    self.status, self.status_color = self.t["failed"], RED
                    self.lines.append(msg)
                    self.save_report(video)
                    messagebox.showerror(self.t["error"], msg)
                    dirty = True
        except queue.Empty:
            pass
        if dirty:
            self.render()
        self.root.after(100, self.poll)


def main():
    if os.name == "nt":
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = TkinterDnD.Tk() if HAVE_DND else tk.Tk()
    preset = sys.argv[1] if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]) else None
    App(root, preset)
    root.mainloop()


if __name__ == "__main__":
    main()
