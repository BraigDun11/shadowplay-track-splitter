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

APP_VERSION = "1.1"

UI = {
    "en": {
        "title": "ShadowPlay Track Splitter",
        "file": "Video file:",
        "browse": "Browse...",
        "mode": "What to do",
        "m_repair": "Split mixed tracks (video repaired with untrunc: PC and mic are mixed in one track)",
        "m_extract": "Extract tracks from a normal video (keep one track in the video, save the others as audio)",
        "swap": "Swap tracks (if PC and mic came out the other way round)",
        "stretch": "Stretch video to match audio length (fixes growing lag)",
        "keep": "Track to keep in the video:",
        "save_others": "Save the other tracks as separate audio files",
        "start": "Start",
        "working": "Working...",
        "ffmpeg_ok": "ffmpeg: found",
        "ffmpeg_no": "ffmpeg not found",
        "ffmpeg_pick": "Choose ffmpeg.exe...",
        "ffmpeg_dialog": "Choose ffmpeg.exe",
        "open": "Open folder",
        "pick_first": "Choose a video file first.",
        "no_ffmpeg": "ffmpeg was not found.\nDownload it from https://www.gyan.dev/ffmpeg/builds/ (essentials build) "
                     "and either put ffmpeg.exe next to this program or choose it with the button.",
        "done": "Done. The files are next to your video.",
        "error": "Error",
        "report": "A report was saved: {p}",
        "video_types": "Video files",
        "all_types": "All files",
        "checking": "Checking the file...",
        "tracks": "Audio tracks in the file: {n}",
        "track_item": "{i}: {codec}{title}{note}",
        "empty": " (empty)",
        "hint_repair": "Looks like a repaired video with mixed tracks: 'Split mixed tracks' is selected.",
        "hint_extract": "The file already has separate audio tracks: 'Extract tracks' is selected.",
        "hint_unreadable": "Could not read the file. If it is the original damaged recording, repair it first.",
    },
    "ru": {
        "title": "ShadowPlay Track Splitter",
        "file": "Видеофайл:",
        "browse": "Выбрать...",
        "mode": "Что сделать",
        "m_repair": "Разделить смешанные дорожки (видео восстановлено untrunc: ПК и микрофон в одной дорожке)",
        "m_extract": "Достать дорожки из обычного видео (оставить одну в видео, остальные сохранить как аудио)",
        "swap": "Поменять дорожки местами (если ПК и микрофон оказались наоборот)",
        "stretch": "Растянуть видео под длину звука (если звук всё сильнее отстаёт)",
        "keep": "Какую дорожку оставить в видео:",
        "save_others": "Сохранить остальные дорожки отдельными аудиофайлами",
        "start": "Начать",
        "working": "Работаю...",
        "ffmpeg_ok": "ffmpeg: найден",
        "ffmpeg_no": "ffmpeg не найден",
        "ffmpeg_pick": "Выбрать ffmpeg.exe...",
        "ffmpeg_dialog": "Выберите ffmpeg.exe",
        "open": "Открыть папку",
        "pick_first": "Сначала выберите видеофайл.",
        "no_ffmpeg": "Не найден ffmpeg.\nСкачайте его на https://www.gyan.dev/ffmpeg/builds/ (essentials) и либо "
                     "положите ffmpeg.exe рядом с программой, либо выберите его кнопкой.",
        "done": "Готово. Файлы лежат рядом с вашим видео.",
        "error": "Ошибка",
        "report": "Отчёт сохранён: {p}",
        "video_types": "Видеофайлы",
        "all_types": "Все файлы",
        "checking": "Проверяю файл...",
        "tracks": "Аудиодорожек в файле: {n}",
        "track_item": "{i}: {codec}{title}{note}",
        "empty": " (пустая)",
        "hint_repair": "Похоже на восстановленное видео со смешанными дорожками: выбрано «Разделить смешанные дорожки».",
        "hint_extract": "В файле уже раздельные дорожки: выбрано «Достать дорожки».",
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
        root.geometry("760x640")
        root.minsize(660, 540)
        pad = {"padx": 12, "pady": 4}

        row = ttk.Frame(root)
        row.pack(fill="x", **pad)
        ttk.Label(row, text=self.t["file"]).pack(anchor="w")
        self.path = tk.StringVar(value=preset or "")
        ttk.Entry(row, textvariable=self.path).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=self.t["browse"], command=self.browse).pack(side="left", padx=(8, 0))

        self.info = ttk.Label(root, text="", wraplength=720, justify="left")
        self.info.pack(anchor="w", **pad)

        ttk.Label(root, text=self.t["mode"]).pack(anchor="w", padx=12, pady=(8, 0))
        self.mode = tk.StringVar(value="repair")
        ttk.Radiobutton(root, text=self.t["m_repair"], variable=self.mode, value="repair",
                        command=self.update_mode).pack(anchor="w", padx=24)
        self.swap = tk.BooleanVar(value=False)
        self.stretch = tk.BooleanVar(value=False)
        self.cb_swap = ttk.Checkbutton(root, text=self.t["swap"], variable=self.swap)
        self.cb_swap.pack(anchor="w", padx=48)
        self.cb_stretch = ttk.Checkbutton(root, text=self.t["stretch"], variable=self.stretch)
        self.cb_stretch.pack(anchor="w", padx=48)

        ttk.Radiobutton(root, text=self.t["m_extract"], variable=self.mode, value="extract",
                        command=self.update_mode).pack(anchor="w", padx=24, pady=(6, 0))
        krow = ttk.Frame(root)
        krow.pack(fill="x", padx=48, pady=2)
        self.lbl_keep = ttk.Label(krow, text=self.t["keep"])
        self.lbl_keep.pack(side="left")
        self.keep = tk.StringVar(value="")
        self.combo = ttk.Combobox(krow, textvariable=self.keep, state="readonly", width=40, values=[])
        self.combo.pack(side="left", padx=8)
        self.save_others = tk.BooleanVar(value=True)
        self.cb_others = ttk.Checkbutton(root, text=self.t["save_others"], variable=self.save_others)
        self.cb_others.pack(anchor="w", padx=48)

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
        if preset:
            self.schedule_probe()
        self.root.after(100, self.poll)

    # ---- helpers
    def update_mode(self):
        repair = self.mode.get() == "repair"
        st_r = "normal" if repair else "disabled"
        st_x = "disabled" if repair else "normal"
        self.cb_swap.configure(state=st_r)
        self.cb_stretch.configure(state=st_r)
        self.cb_others.configure(state=st_x)
        self.combo.configure(state="disabled" if repair else "readonly")

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

    def open_folder(self):
        if not self.out_dir:
            return
        try:
            if os.name == "nt":
                os.startfile(self.out_dir)  # noqa
            else:
                subprocess.Popen(["xdg-open", self.out_dir])
        except Exception:
            pass

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
        items = []
        for s in streams:
            items.append(self.t["track_item"].format(
                i=s["index"] + 1, codec=s["codec"],
                title=(" '%s'" % s["title"]) if s["title"] else "",
                note=self.t["empty"] if s["mb"] < 0.01 else ""))
        self.combo.configure(values=items)
        if items:
            self.keep.set(items[0])
        full = [s for s in streams if s["mb"] >= 0.01]
        if len(full) >= 2:
            self.mode.set("extract")
            hint = self.t["hint_extract"]
        else:
            self.mode.set("repair")
            hint = self.t["hint_repair"]
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
        keep = 0
        if self.mode.get() == "extract":
            vals = list(self.combo.cget("values"))
            cur = self.keep.get()
            keep = vals.index(cur) if cur in vals else 0
        self.out_dir = os.path.dirname(os.path.abspath(video))
        self.lines = []
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self.btn.configure(state="disabled", text=self.t["working"])
        self.openbtn.configure(state="disabled")
        self.bar["value"] = 0
        args = (self.mode.get(), video, self.ffmpeg, self.swap.get(), self.stretch.get(), keep,
                self.save_others.get())
        threading.Thread(target=self.worker, args=args, daemon=True).start()

    def worker(self, mode, video, ffmpeg, swap, stretch, keep, save_others):
        log = lambda s: self.q.put(("log", s))
        prog = lambda f: self.q.put(("progress", f))
        try:
            if mode == "extract":
                core.extract_tracks(video, ffmpeg=ffmpeg, keep=keep, save_others=save_others,
                                    log=log, progress=prog, lang=self.lang)
            else:
                core.process(video, ffmpeg=ffmpeg, swap=swap, match_video=stretch,
                             log=log, progress=prog, lang=self.lang)
            self.q.put(("done", video))
        except core.SplitError as e:
            self.q.put(("error", (video, str(e))))
        except Exception as e:  # unexpected
            import traceback
            self.q.put(("error", (video, "%s\n%s" % (e, traceback.format_exc()))))

    def save_report(self, video):
        p = os.path.splitext(video)[0] + "_report.txt"
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write("ShadowPlay Track Splitter %s\n\n" % APP_VERSION)
                f.write("\n".join(self.lines))
            self.add_log(self.t["report"].format(p=p))
        except OSError:
            pass

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
    root = tk.Tk()
    preset = sys.argv[1] if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]) else None
    App(root, preset)
    root.mainloop()


if __name__ == "__main__":
    main()
