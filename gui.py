# -*- coding: utf-8 -*-
"""ShadowPlay Track Splitter - simple window.  Run: python gui.py   (or the built .exe)"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import core

try:  # drag & drop of files into the window (optional)
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAVE_DND = True
except Exception:  # pragma: no cover
    DND_FILES = TkinterDnD = None
    HAVE_DND = False

APP_VERSION = "1.2"

UI = {
    "en": {
        "title": "ShadowPlay Track Splitter",
        "file": "Video file (you can drag it into this window):",
        "browse": "Browse...",
        "mode": "What to do",
        "m_repair": "Split mixed tracks (video repaired with untrunc: PC and mic are mixed in one track)",
        "m_extract": "Separate audio from a normal video (keep a track in the video, save audio as files)",
        "swap": "Swap tracks (if PC and mic came out the other way round)",
        "stretch": "Stretch video to match audio length (fixes growing lag)",
        "save_audio": "Also save PC and mic as separate audio files (.m4a)",
        "keep": "Sound in the video:",
        "no_audio": "No sound (video only)",
        "nothing_to_do": "Nothing to do: tick at least one option for saving audio files (otherwise the result would be the same video).",
        "save_others": "Save the other tracks as separate audio files",
        "save_kept": "Also save the track that stays in the video as an audio file",
        "start": "Start",
        "working": "Working...",
        "ffmpeg_ok": "ffmpeg: found",
        "ffmpeg_no": "ffmpeg not found",
        "ffmpeg_pick": "Choose ffmpeg.exe...",
        "ffmpeg_dialog": "Choose ffmpeg.exe",
        "open": "Open folder",
        "reports": "Reports folder",
        "pick_first": "Choose a video file first.",
        "no_ffmpeg": "ffmpeg was not found.\nDownload it from https://www.gyan.dev/ffmpeg/builds/ (essentials build) "
                     "and either put ffmpeg.exe next to this program or choose it with the button.",
        "done": "Done. The files are next to your video.",
        "error": "Error",
        "report": "A report was saved: {p}",
        "video_types": "Video files",
        "all_types": "All files",
        "checking": "Checking the file...",
        "tracks": "Audio tracks in the file: {n}.",
        "track_item": "{i}: {codec}{title}{note}",
        "empty": " (empty)",
        "hint_repair": "Looks like a repaired video with mixed tracks: 'Split mixed tracks' is selected.",
        "hint_extract": "The file has normal audio track(s): 'Separate audio' is selected.",
        "hint_unreadable": "Could not read the file. If it is the original damaged recording, repair it first.",
    },
    "ru": {
        "title": "ShadowPlay Track Splitter",
        "file": "Видеофайл (можно перетащить в это окно):",
        "browse": "Выбрать...",
        "mode": "Что сделать",
        "m_repair": "Разделить смешанные дорожки (видео восстановлено untrunc: ПК и микрофон в одной дорожке)",
        "m_extract": "Отделить звук от обычного видео (оставить дорожку в видео, звук сохранить файлами)",
        "swap": "Поменять дорожки местами (если ПК и микрофон оказались наоборот)",
        "stretch": "Растянуть видео под длину звука (если звук всё сильнее отстаёт)",
        "save_audio": "Также сохранить ПК и микрофон отдельными аудиофайлами (.m4a)",
        "keep": "Звук в видео:",
        "no_audio": "Без звука (только картинка)",
        "nothing_to_do": "Нечего делать: отметь хотя бы один пункт сохранения аудиофайлов (иначе получится то же самое видео).",
        "save_others": "Сохранить остальные дорожки отдельными аудиофайлами",
        "save_kept": "Также сохранить дорожку, которая остаётся в видео, как аудиофайл",
        "start": "Начать",
        "working": "Работаю...",
        "ffmpeg_ok": "ffmpeg: найден",
        "ffmpeg_no": "ffmpeg не найден",
        "ffmpeg_pick": "Выбрать ffmpeg.exe...",
        "ffmpeg_dialog": "Выберите ffmpeg.exe",
        "open": "Открыть папку",
        "reports": "Папка отчётов",
        "pick_first": "Сначала выберите видеофайл.",
        "no_ffmpeg": "Не найден ffmpeg.\nСкачайте его на https://www.gyan.dev/ffmpeg/builds/ (essentials) и либо "
                     "положите ffmpeg.exe рядом с программой, либо выберите его кнопкой.",
        "done": "Готово. Файлы лежат рядом с вашим видео.",
        "error": "Ошибка",
        "report": "Отчёт сохранён: {p}",
        "video_types": "Видеофайлы",
        "all_types": "Все файлы",
        "checking": "Проверяю файл...",
        "tracks": "Аудиодорожек в файле: {n}.",
        "track_item": "{i}: {codec}{title}{note}",
        "empty": " (пустая)",
        "hint_repair": "Похоже на восстановленное видео со смешанными дорожками: выбрано «Разделить смешанные».",
        "hint_extract": "В файле обычные аудиодорожки: выбрано «Отделить звук».",
        "hint_unreadable": "Не получилось прочитать файл. Если это исходная повреждённая запись, сначала восстановите её.",
    },
}


class App:
    def __init__(self, root, preset=None):
        self.root = root
        self.lang = core.detect_lang()
        self.t = UI[self.lang]
        self.q = queue.Queue()
        self.ffmpeg = core.find_ffmpeg()
        self.out_dir = None
        self.lines = []
        self.streams = []
        self.probe_token = 0

        root.title("%s %s" % (self.t["title"], APP_VERSION))
        root.geometry("780x700")
        root.minsize(680, 600)
        pad = {"padx": 12, "pady": 4}

        row = ttk.Frame(root)
        row.pack(fill="x", **pad)
        ttk.Label(row, text=self.t["file"]).pack(anchor="w")
        self.path = tk.StringVar(value=preset or "")
        self.entry = ttk.Entry(row, textvariable=self.path)
        self.entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=self.t["browse"], command=self.browse).pack(side="left", padx=(8, 0))

        self.info = ttk.Label(root, text="", wraplength=740, justify="left")
        self.info.pack(anchor="w", **pad)

        ttk.Label(root, text=self.t["mode"]).pack(anchor="w", padx=12, pady=(8, 0))
        self.mode = tk.StringVar(value="repair")
        ttk.Radiobutton(root, text=self.t["m_repair"], variable=self.mode, value="repair",
                        command=self.update_mode).pack(anchor="w", padx=24)
        self.swap = tk.BooleanVar(value=False)
        self.stretch = tk.BooleanVar(value=True)
        self.save_audio = tk.BooleanVar(value=False)
        self.cb_swap = ttk.Checkbutton(root, text=self.t["swap"], variable=self.swap)
        self.cb_swap.pack(anchor="w", padx=48)
        self.cb_stretch = ttk.Checkbutton(root, text=self.t["stretch"], variable=self.stretch)
        self.cb_stretch.pack(anchor="w", padx=48)
        self.cb_saveaudio = ttk.Checkbutton(root, text=self.t["save_audio"], variable=self.save_audio)
        self.cb_saveaudio.pack(anchor="w", padx=48)

        ttk.Radiobutton(root, text=self.t["m_extract"], variable=self.mode, value="extract",
                        command=self.update_mode).pack(anchor="w", padx=24, pady=(6, 0))
        krow = ttk.Frame(root)
        krow.pack(fill="x", padx=48, pady=2)
        ttk.Label(krow, text=self.t["keep"]).pack(side="left")
        self.keep = tk.StringVar(value="")
        self.combo = ttk.Combobox(krow, textvariable=self.keep, state="readonly", width=44,
                                  values=[self.t["no_audio"]])
        self.combo.pack(side="left", padx=8)
        self.keep.set(self.t["no_audio"])
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.update_kept_state())
        self.save_others = tk.BooleanVar(value=True)
        self.save_kept = tk.BooleanVar(value=False)
        self.cb_others = ttk.Checkbutton(root, text=self.t["save_others"], variable=self.save_others)
        self.cb_others.pack(anchor="w", padx=48)
        self.cb_kept = ttk.Checkbutton(root, text=self.t["save_kept"], variable=self.save_kept)
        self.cb_kept.pack(anchor="w", padx=48)

        frow = ttk.Frame(root)
        frow.pack(fill="x", **pad)
        self.ffl = ttk.Label(frow, text="")
        self.ffl.pack(side="left")
        ttk.Button(frow, text=self.t["ffmpeg_pick"], command=self.pick_ffmpeg).pack(side="left", padx=8)
        self.refresh_ffmpeg()

        brow = ttk.Frame(root)
        brow.pack(fill="x", **pad)
        self.btn = ttk.Button(brow, text=self.t["start"], command=self.start)
        self.btn.pack(side="left")
        self.openbtn = ttk.Button(brow, text=self.t["open"], command=self.open_folder, state="disabled")
        self.openbtn.pack(side="left", padx=8)
        ttk.Button(brow, text=self.t["reports"], command=self.open_reports).pack(side="left")

        self.bar = ttk.Progressbar(root, maximum=1.0)
        self.bar.pack(fill="x", **pad)

        lf = ttk.Frame(root)
        lf.pack(fill="both", expand=True, **pad)
        self.text = tk.Text(lf, height=10, wrap="word", state="disabled", font=("Consolas", 9))
        sb = ttk.Scrollbar(lf, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        self.update_mode()
        self.path.trace_add("write", lambda *a: self.schedule_probe())
        self.setup_dnd()
        if preset:
            self.schedule_probe()
        self.root.after(100, self.poll)

    # ---- drag & drop
    def setup_dnd(self):
        if not HAVE_DND:
            return
        try:
            for w in (self.root, self.entry, self.text):
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
                self.path.set(f)
                break
        return event.action if hasattr(event, "action") else None

    # ---- helpers
    def update_mode(self):
        repair = self.mode.get() == "repair"
        st_r = "normal" if repair else "disabled"
        st_x = "disabled" if repair else "normal"
        for w in (self.cb_swap, self.cb_stretch, self.cb_saveaudio):
            w.configure(state=st_r)
        for w in (self.cb_others, self.cb_kept):
            w.configure(state=st_x)
        self.combo.configure(state="disabled" if repair else "readonly")
        self.update_kept_state()

    def update_kept_state(self):
        """Keep the two audio checkboxes consistent with the chosen track.
        Silent video: every track is "other" and goes to audio files (nothing "stays").
        One track kept out of one: there are no "other" tracks to save."""
        if self.mode.get() == "repair":
            return
        silent = self.keep.get() == self.t["no_audio"]
        n = len(getattr(self, "streams", []) or [])
        if silent:
            self.save_kept.set(False)
            self.save_others.set(True)
        self.cb_kept.configure(state="disabled" if silent else "normal")
        no_others = (not silent) and n <= 1
        if no_others:
            # one track kept in the video, nothing else to save: the only useful result
            # is a copy of that track as an audio file, so that box is on and locked
            self.save_others.set(False)
            self.save_kept.set(True)
            self.cb_kept.configure(state="disabled")
        self.cb_others.configure(state="disabled" if no_others else "normal")

    def refresh_ffmpeg(self):
        self.ffl.configure(text=self.t["ffmpeg_ok"] if self.ffmpeg else self.t["ffmpeg_no"])

    def browse(self):
        p = filedialog.askopenfilename(filetypes=[(self.t["video_types"], "*.mp4 *.mov *.mkv *.m4v"),
                                                  (self.t["all_types"], "*.*")])
        if p:
            self.path.set(p)

    def pick_ffmpeg(self):
        p = filedialog.askopenfilename(title=self.t["ffmpeg_dialog"],
                                       filetypes=[("ffmpeg", "ffmpeg*"), (self.t["all_types"], "*.*")])
        if p:
            found = core.find_ffmpeg(p)
            if found:
                self.ffmpeg = found
                self.refresh_ffmpeg()
                self.schedule_probe()

    def add_log(self, s):
        self.lines.append(s)
        self.text.configure(state="normal")
        self.text.insert("end", s + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def _open(self, path):
        try:
            if os.name == "nt":
                os.startfile(path)  # noqa
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def open_folder(self):
        if self.out_dir:
            self._open(self.out_dir)

    def open_reports(self):
        self._open(core.reports_dir())

    # ---- looking at the chosen file (in background)
    def schedule_probe(self):
        video = self.path.get().strip().strip('"')
        self.probe_token += 1
        if not video or not os.path.isfile(video) or not self.ffmpeg:
            return
        self.info.configure(text=self.t["checking"])
        threading.Thread(target=self.probe_worker, args=(self.probe_token, video, self.ffmpeg),
                         daemon=True).start()

    def probe_worker(self, token, video, ffmpeg):
        try:
            streams = core.probe_audio(ffmpeg, video, self.lang)
            self.q.put(("probe", (token, streams)))
        except Exception:
            self.q.put(("probe", (token, None)))

    def apply_probe(self, token, streams):
        if token != self.probe_token:
            return
        if streams is None:
            self.info.configure(text=self.t["hint_unreadable"])
            return
        self.streams = streams
        items = [self.t["no_audio"]]
        for s in streams:
            items.append(self.t["track_item"].format(
                i=s["index"] + 1, codec=s["codec"],
                title=(" '%s'" % s["title"]) if s["title"] else "",
                note=self.t["empty"] if s["mb"] < 0.01 else ""))
        self.combo.configure(values=items)
        full = [s for s in streams if s["mb"] >= 0.01]
        if len(streams) >= 2 and len(full) < 2:
            # two streams but only one has data: the signature of a repaired video
            self.mode.set("repair")
            hint = self.t["hint_repair"]
            self.keep.set(items[1] if len(items) > 1 else items[0])
        else:
            self.mode.set("extract")
            hint = self.t["hint_extract"]
            # several tracks: keep the first in the video; a single track: make a silent video + audio file
            self.keep.set(items[1] if len(streams) >= 2 else items[0])
        self.update_mode()
        self.info.configure(text="%s  %s" % (self.t["tracks"].format(n=len(streams)), hint))

    # ---- run
    def start(self):
        video = self.path.get().strip().strip('"')
        if not video or not os.path.isfile(video):
            messagebox.showinfo(self.t["title"], self.t["pick_first"])
            return
        if not self.ffmpeg:
            messagebox.showerror(self.t["error"], self.t["no_ffmpeg"])
            return
        keep = -1
        if self.mode.get() == "extract":
            vals = list(self.combo.cget("values"))
            cur = self.keep.get()
            idx = vals.index(cur) if cur in vals else 0
            keep = idx - 1          # 0 in the list = "no sound" -> -1
            if keep >= 0 and not self.save_others.get() and not self.save_kept.get():
                messagebox.showinfo(self.t["title"], self.t["nothing_to_do"])
                return
        self.out_dir = os.path.dirname(os.path.abspath(video))
        self.lines = []
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self.btn.configure(state="disabled", text=self.t["working"])
        self.openbtn.configure(state="disabled")
        self.bar["value"] = 0
        opts = dict(mode=self.mode.get(), video=video, ffmpeg=self.ffmpeg, swap=self.swap.get(),
                    stretch=self.stretch.get(), save_audio=self.save_audio.get(), keep=keep,
                    save_others=self.save_others.get(), save_kept=self.save_kept.get())
        threading.Thread(target=self.worker, args=(opts,), daemon=True).start()

    def worker(self, o):
        log = lambda s: self.q.put(("log", s))
        prog = lambda f: self.q.put(("progress", f))
        try:
            if o["mode"] == "extract":
                core.extract_tracks(o["video"], ffmpeg=o["ffmpeg"], keep=o["keep"], save_others=o["save_others"],
                                    save_kept=o["save_kept"], log=log, progress=prog, lang=self.lang)
            else:
                core.process(o["video"], ffmpeg=o["ffmpeg"], swap=o["swap"], match_video=o["stretch"],
                             log=log, progress=prog, lang=self.lang, save_audio_files=o["save_audio"])
            self.q.put(("done", o["video"]))
        except core.SplitError as e:
            self.q.put(("error", (o["video"], str(e))))
        except Exception as e:  # unexpected
            import traceback
            self.q.put(("error", (o["video"], "%s\n%s" % (e, traceback.format_exc()))))

    def save_report(self, video):
        p = core.save_report(video, self.lines, APP_VERSION)
        if p:
            self.add_log(self.t["report"].format(p=p))

    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.add_log(val)
                elif kind == "progress":
                    self.bar["value"] = val
                elif kind == "probe":
                    self.apply_probe(*val)
                elif kind == "done":
                    self.btn.configure(state="normal", text=self.t["start"])
                    self.openbtn.configure(state="normal")
                    self.bar["value"] = 1.0
                    self.save_report(val)
                    messagebox.showinfo(self.t["title"], self.t["done"])
                elif kind == "error":
                    video, msg = val
                    self.btn.configure(state="normal", text=self.t["start"])
                    self.add_log(msg)
                    self.save_report(video)
                    messagebox.showerror(self.t["error"], msg)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def main():
    root = TkinterDnD.Tk() if HAVE_DND else tk.Tk()
    preset = sys.argv[1] if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]) else None
    App(root, preset)
    root.mainloop()


if __name__ == "__main__":
    main()
