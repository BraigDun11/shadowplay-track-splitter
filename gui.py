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

APP_VERSION = "1.0"

UI = {
    "en": {
        "title": "ShadowPlay Track Splitter",
        "intro": "Splits the PC-sound and microphone tracks that got mixed into one audio stream "
                 "after repairing a damaged recording (e.g. with untrunc).",
        "file": "Repaired video:",
        "browse": "Browse...",
        "swap": "Swap tracks (if PC and mic came out the other way round)",
        "stretch": "Stretch video to match audio length (fixes growing lag)",
        "start": "Split tracks",
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
    },
    "ru": {
        "title": "ShadowPlay Track Splitter",
        "intro": "Разделяет звук с ПК и микрофон, которые после восстановления повреждённой записи "
                 "(например, программой untrunc) смешались в один аудиопоток.",
        "file": "Восстановленное видео:",
        "browse": "Выбрать...",
        "swap": "Поменять дорожки местами (если ПК и микрофон оказались наоборот)",
        "stretch": "Растянуть видео под длину звука (если звук всё сильнее отстаёт)",
        "start": "Разделить дорожки",
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

        root.title("%s %s" % (self.t["title"], APP_VERSION))
        root.geometry("720x560")
        root.minsize(620, 460)
        pad = {"padx": 12, "pady": 6}

        ttk.Label(root, text=self.t["intro"], wraplength=680, justify="left").pack(anchor="w", **pad)

        row = ttk.Frame(root)
        row.pack(fill="x", **pad)
        ttk.Label(row, text=self.t["file"]).pack(anchor="w")
        self.path = tk.StringVar(value=preset or "")
        ttk.Entry(row, textvariable=self.path).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=self.t["browse"], command=self.browse).pack(side="left", padx=(8, 0))

        self.swap = tk.BooleanVar(value=False)
        self.stretch = tk.BooleanVar(value=False)
        ttk.Checkbutton(root, text=self.t["swap"], variable=self.swap).pack(anchor="w", padx=12)
        ttk.Checkbutton(root, text=self.t["stretch"], variable=self.stretch).pack(anchor="w", padx=12)

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
        self.text = tk.Text(lf, height=12, wrap="word", state="disabled", font=("Consolas", 9))
        sb = ttk.Scrollbar(lf, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        self.root.after(100, self.poll)

    # ---- helpers
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

    # ---- run
    def start(self):
        video = self.path.get().strip().strip('"')
        if not video or not os.path.isfile(video):
            messagebox.showinfo(self.t["title"], self.t["pick_first"])
            return
        if not self.ffmpeg:
            messagebox.showerror(self.t["error"], self.t["no_ffmpeg"])
            return
        self.out_dir = os.path.dirname(os.path.abspath(video))
        self.lines = []
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self.btn.configure(state="disabled", text=self.t["working"])
        self.openbtn.configure(state="disabled")
        self.bar["value"] = 0
        args = (video, self.ffmpeg, self.swap.get(), self.stretch.get())
        threading.Thread(target=self.worker, args=args, daemon=True).start()

    def worker(self, video, ffmpeg, swap, stretch):
        try:
            core.process(video, ffmpeg=ffmpeg, swap=swap, match_video=stretch,
                         log=lambda s: self.q.put(("log", s)),
                         progress=lambda f: self.q.put(("progress", f)),
                         lang=self.lang)
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
