# -*- coding: utf-8 -*-
"""
ShadowPlay Track Splitter - core logic (no GUI).

Problem: after repairing a damaged NVIDIA ShadowPlay recording (e.g. with untrunc),
two audio tracks (PC sound + microphone) end up interleaved in ONE audio stream:
~1 second of PC, ~1 second of mic, PC, mic ... and the second stream is empty.
The audio is ~2x longer than the video.

This module finds the chunk schedule, rebuilds the two tracks bit-exactly from the
original AAC packets (no re-encoding) and muxes them back into the video.
"""
import collections
import errno
import json
import os
import threading
import time
import shutil
import re
import subprocess
import sys
import tempfile

import numpy as np

FRAME = 1024  # samples per AAC packet
SF_TABLE = [96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050,
            16000, 12000, 11025, 8000, 7350]

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ----------------------------------------------------------------- messages
MSG = {
    "en": {
        "no_ffmpeg": "ffmpeg was not found. Put ffmpeg.exe next to this program, add it to PATH, or choose it manually.",
        "s1": "1/5 Extracting audio (no re-encoding)...",
        "e_extract": "Could not extract audio (is it AAC?):\n{err}",
        "s2": "2/5 Parsing audio packets...",
        "packets": "    packets: {n} (~{min:.1f} min), {sr} Hz",
        "s3": "3/5 Analysing audio (a few minutes for long recordings)...",
        "mismatch": "    WARNING: decoded frames ({a}) and packets ({b}) differ",
        "no_sched": "No mixed audio tracks were found in this file. If it is a normal video that already has "
                    "separate tracks, use the 'Extract tracks' mode instead. Otherwise the recording may be too short "
                    "or structured differently. A diagnostic file was saved: {path}",
        "sched": "    schedule: period {p} packets (mono chunk {lm}, stereo chunk {ls})",
        "s4": "4/5 Splitting. Schedule shifts found: {n}",
        "shift_at": "      around {t} (time in the finished video)",
        "agree": "    agreement with signal: stereo {a:.1f}%, mono {b:.1f}%",
        "low_agree": "    WARNING: low agreement - result may contain mixed-up pieces.",
        "dur": "    track length: PC {a:.2f} min, mic {b:.2f} min",
        "vdur": "    video length (picture only): {v:.2f} min",
        "stretch": "    stretching video by x{s:.4f} to match audio",
        "fit": "    {n} track: tempo changed by x{r:.4f} to match the video length (re-encoded)",
        "ev_head": "    Places worth listening to ({n}; time in the finished video):",
        "ev_shift": "the chunk schedule shifted (a chunk of {n} packets instead of {nom}): a click, a cut or swapped bits are possible",
        "ev_vgap": "the video has a hole here: {g:.1f} s of picture missing",
        "vgaps": "    The video itself has {n} hole(s) in its timeline (missing frames, {tot:.1f} min in total) - these are the places where it lags behind the sound:",
        "vgap": "      at {t} (video time): {g:.1f} s of picture missing",
        "vgaps0": "    The video timeline has no holes ({n} frames, {f:.1f} fps = {e:.1f} min). The missing picture time is not marked in the file, so its position cannot be found.",
        "hint_stretch": "    HINT: audio is {d:.1f} min longer than video. If sound lags behind the picture more and "
                        "more towards the end, enable 'Stretch video to match audio'.",
        "s5": "5/5 Building final video with two audio tracks...",
        "e_mux": "Could not build the video, but tracks were saved: {a} and {b}",
        "done": "DONE: {out}",
        "done2": "Tracks separately: {a} and {b}",
        "moov": "This file is damaged: it has no index ('moov atom not found'), so it cannot be read at all.\n"
                "First repair the video (for example with untrunc and a healthy reference recording) "
                "and open the REPAIRED file here.",
        "x1": "Reading audio tracks...",
        "x_found": "    audio tracks: {n}",
        "x_track": "      track {i}: {codec}{title}, {size:.1f} MB",
        "x_none": "No audio tracks found in this file.",
        "x_one": "This video has only one audio track - there is nothing to separate.",
        "x_bad": "Invalid track number.",
        "x_video": "Saving video with track {i}...",
        "x_video_none": "Saving video without sound...",
        "x_report": "A report was saved: {p}",
        "x_audio": "Saving track {i} as an audio file...",
        "x_done": "DONE: {out}",
        "x_done2": "Audio files: {files}",
        "done3": "Audio files: {files}",
        "nospace": "Not enough free space on the disk where the results are saved. Free up space or choose another folder in the settings (the gear in the corner) and start again.",
        "x_done_audio": "DONE (audio only, no video needed): {files}",
    },
    "ru": {
        "no_ffmpeg": "Не найден ffmpeg. Положите ffmpeg.exe рядом с программой, добавьте его в PATH или выберите вручную.",
        "s1": "1/5 Достаю аудио из видео (без перекодирования)...",
        "e_extract": "Не получилось достать аудио (возможно, оно не AAC):\n{err}",
        "s2": "2/5 Разбираю аудиопакеты...",
        "packets": "    пакетов: {n} (~{min:.1f} мин), {sr} Гц",
        "s3": "3/5 Анализирую звук (для длинных записей несколько минут)...",
        "mismatch": "    ВНИМАНИЕ: число кадров звука ({a}) и пакетов ({b}) не совпало",
        "no_sched": "Смешанных аудиодорожек в этом файле не найдено. Если это обычное видео, где дорожки уже "
                    "раздельные, используйте режим «Достать дорожки». Иначе запись может быть слишком короткой "
                    "или устроена иначе. Диагностический файл сохранён: {path}",
        "sched": "    расписание: период {p} пакетов (моно-кусок {lm}, стерео-кусок {ls})",
        "s4": "4/5 Разделяю. Сдвигов расписания найдено: {n}",
        "shift_at": "      около {t} (время в готовом видео)",
        "agree": "    согласие с признаками: стерео {a:.1f}%, моно {b:.1f}%",
        "low_agree": "    ВНИМАНИЕ: согласие низкое - в дорожках могут быть перепутанные кусочки.",
        "dur": "    длина дорожек: ПК {a:.2f} мин, микрофон {b:.2f} мин",
        "vdur": "    длина видео (только картинка): {v:.2f} мин",
        "stretch": "    растягиваю видео в {s:.4f} раза, чтобы совпало со звуком",
        "fit": "    дорожка {n}: темп изменён в {r:.4f} раза, чтобы совпало с длиной видео (перекодирование)",
        "ev_head": "    Места, которые стоит прослушать ({n}; время в готовом видео):",
        "ev_shift": "расписание кусков сдвинулось (кусок из {n} пакетов вместо {nom}): возможны щелчок, обрыв или перепутанные кусочки",
        "ev_vgap": "в видео здесь дыра: не хватает {g:.1f} с картинки",
        "vgaps": "    В самом видео есть дыры во временной шкале: {n} шт. (не хватает кадров, всего {tot:.1f} мин). Именно в этих местах картинка отстаёт от звука:",
        "vgap": "      около {t} (время видео): не хватает {g:.1f} с картинки",
        "vgaps0": "    Дыр во временной шкале видео нет ({n} кадров, {f:.1f} кадр/с = {e:.1f} мин). Недостающее время картинки в файле не отмечено, поэтому найти место нельзя.",
        "hint_stretch": "    ПОДСКАЗКА: звук длиннее видео на {d:.1f} мин. Если звук всё сильнее отстаёт от "
                        "картинки к концу, включите «Растянуть видео под длину звука».",
        "s5": "5/5 Собираю итоговое видео с двумя дорожками...",
        "e_mux": "Не удалось собрать видео, но дорожки сохранены: {a} и {b}",
        "done": "ГОТОВО: {out}",
        "done2": "Дорожки отдельно: {a} и {b}",
        "moov": "Этот файл повреждён: у него нет индекса («moov atom not found»), поэтому его вообще нельзя прочитать.\n"
                "Сначала восстановите видео (например, программой untrunc и целым эталонным видео), "
                "а здесь откройте уже ВОССТАНОВЛЕННЫЙ файл.",
        "x1": "Читаю аудиодорожки...",
        "x_found": "    аудиодорожек: {n}",
        "x_track": "      дорожка {i}: {codec}{title}, {size:.1f} МБ",
        "x_none": "В этом файле нет аудиодорожек.",
        "x_one": "В этом видео одна аудиодорожка - разделять нечего.",
        "x_bad": "Неверный номер дорожки.",
        "x_video": "Сохраняю видео с дорожкой {i}...",
        "x_video_none": "Сохраняю видео без звука...",
        "x_report": "Отчёт сохранён: {p}",
        "x_audio": "Сохраняю дорожку {i} отдельным аудиофайлом...",
        "x_done": "ГОТОВО: {out}",
        "x_done2": "Аудиофайлы: {files}",
        "done3": "Аудиофайлы: {files}",
        "nospace": "Не хватило места на диске, куда сохраняются результаты. Освободите место или выберите другую папку в настройках (шестерёнка в углу) и запустите снова.",
        "x_done_audio": "ГОТОВО (только аудио, видео не нужно): {files}",
    },
}


class SplitError(Exception):
    pass


class Cancelled(Exception):
    """The user pressed Stop."""


CANCEL = threading.Event()


def check_cancel():
    if CANCEL.is_set():
        raise Cancelled()


def detect_lang():
    """'ru' if the user interface language is Russian, otherwise 'en'."""
    try:
        if os.name == "nt":
            import ctypes
            return "ru" if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x19 else "en"
        import locale
        return "ru" if (locale.getlocale()[0] or "").lower().startswith("ru") else "en"
    except Exception:
        return "en"


def documents_dir():
    """The user's Documents folder (handles OneDrive-redirected folders on Windows)."""
    if os.name == "nt":
        try:
            import ctypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort),
                            ("d", ctypes.c_ubyte * 8)]

            guid = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            buf = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(buf)) == 0:
                path = buf.value
                ctypes.windll.ole32.CoTaskMemFree(buf)
                if path and os.path.isdir(path):
                    return path
        except Exception:
            pass
    d = os.path.join(os.path.expanduser("~"), "Documents")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def reports_dir():
    """Folder for reports and diagnostic files: Documents/ShadowPlay Track Splitter/Reports."""
    d = os.path.join(documents_dir(), "ShadowPlay Track Splitter", "Reports")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = tempfile.gettempdir()
    return d


def out_base(video, out_dir=None):
    """Path prefix for the result files: <out_dir>/<video name> (next to the video if no folder is given)."""
    name = os.path.splitext(os.path.basename(video))[0]
    d = out_dir or os.path.dirname(os.path.abspath(video))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def ff_error(M, r, key="e_extract"):
    """SplitError for a failed ffmpeg call; a full disk gets its own clear message."""
    err = r.stderr or ""
    if "No space left" in err or "not enough space" in err.lower():
        return SplitError(M["nospace"])
    return SplitError(M[key].format(err=err))


def unique_suffix(patterns, **kw):
    """Smallest suffix '', '1', '2', ... for which none of the files named by `patterns` exists.
    Each pattern is a format string with {n}, e.g. '{base}_fixed{n}.mp4'."""
    i = 0
    while True:
        suf = "" if i == 0 else str(i)
        if not any(os.path.exists(p.format(n=suf, **kw)) for p in patterns):
            return suf
        i += 1


def save_report(video, lines, version=""):
    """Write the text report into the reports folder; returns its path (or None)."""
    name = os.path.splitext(os.path.basename(video))[0]
    d = reports_dir()
    suf = unique_suffix(["{d}/{name}_report{n}.txt"], d=d, name=name)
    path = os.path.join(d, "%s_report%s.txt" % (name, suf))
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("ShadowPlay Track Splitter %s\n" % version)
            f.write("%s\n\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            f.write("\n".join(lines))
        return path
    except OSError:
        return None


def default_out_dir():
    """Where repaired videos go by default: Documents/ShadowPlay Track Splitter/Fixed."""
    return os.path.join(documents_dir(), "ShadowPlay Track Splitter", "Fixed")


def settings_path():
    return os.path.join(documents_dir(), "ShadowPlay Track Splitter", "settings.json")


def load_settings():
    try:
        with open(settings_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(d):
    try:
        os.makedirs(os.path.dirname(settings_path()), exist_ok=True)
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        return True
    except OSError:
        return False


def free_bytes(path):
    """Free space of the disk that holds `path` (the folder may not exist yet)."""
    p = os.path.abspath(path)
    while p and not os.path.exists(p):
        up = os.path.dirname(p)
        if up == p:
            break
        p = up
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return None


MB = 1024 * 1024


def needed_space(video, streams, mode, stream=0, keep=-1, save_tracks=(), save_audio=False, audio_only=False):
    """Rough number of bytes the job needs in the output folder (a bit more than is really used).
    mode 'repair': new video + two tracks (+ temporary copies) ; 'extract': new video + saved audio files."""
    try:
        total = os.path.getsize(video)
    except OSError:
        return 0
    audio = {s["index"]: s.get("mb", 0.0) * MB for s in streams}
    if mode == "repair" and audio_only:
        a = audio.get(stream) or total * 0.5
        need = a * 3
    elif mode == "repair":
        a = audio.get(stream) or total * 0.5
        need = (total - a) + a * (3 + (1 if save_audio else 0))
    else:
        a_all = sum(audio.values())
        video_part = max(total - a_all, 0)
        kept = audio.get(keep, 0) if keep >= 0 else 0
        need = video_part + kept + sum(audio.get(i, 0) for i in save_tracks)
    return int(need * 1.05 + 100 * MB)


# ----------------------------------------------------------------- ffmpeg
FFMPEG_URLS = [
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
]


def ffmpeg_dir():
    """Where the program keeps the ffmpeg it downloaded itself: Documents/ShadowPlay Track Splitter/ffmpeg."""
    return os.path.join(documents_dir(), "ShadowPlay Track Splitter", "ffmpeg")


def download_ffmpeg(progress=None, urls=None, cancelled=None):
    """Download a Windows ffmpeg build and unpack ffmpeg.exe (and ffprobe.exe) into ffmpeg_dir().
    Returns the path of ffmpeg.exe or raises OSError/ValueError (all addresses failed)."""
    import urllib.request
    import zipfile
    if os.name != "nt":
        raise OSError("automatic download is only available on Windows")
    dest = ffmpeg_dir()
    os.makedirs(dest, exist_ok=True)
    last = None
    for url in (urls or FFMPEG_URLS):
        tmp = os.path.join(dest, "download.zip.part")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ShadowPlayTrackSplitter"})
            with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    if cancelled and cancelled():
                        raise OSError("cancelled")
                    chunk = r.read(1 << 18)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if progress and total:
                        progress(min(0.95, 0.95 * got / total))
            found = {}
            with zipfile.ZipFile(tmp) as z:
                for name in z.namelist():
                    base = name.replace("\\", "/").split("/")
                    if len(base) >= 2 and base[-2] == "bin" and base[-1] in ("ffmpeg.exe", "ffprobe.exe"):
                        out = os.path.join(dest, base[-1])
                        with z.open(name) as src, open(out + ".part", "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        found[base[-1]] = out
            if "ffmpeg.exe" not in found:
                raise ValueError("ffmpeg.exe not found in the archive")
            for n_, out in found.items():
                os.replace(out + ".part", out)
            if progress:
                progress(1.0)
            return found["ffmpeg.exe"]
        except Exception as ex:
            last = ex
        finally:
            for f_ in (tmp, ):
                try:
                    os.remove(f_)
                except OSError:
                    pass
    raise OSError(str(last))


FFMPEG_LATEST_URL = "https://www.gyan.dev/ffmpeg/builds/release-version"


def ffmpeg_version(path):
    """Version of an ffmpeg executable as a tuple, e.g. (7, 1, 1); None if it cannot be told."""
    try:
        r = subprocess.run([path, "-version"], capture_output=True, text=True, creationflags=NO_WINDOW)
        m_ = re.match(r"ffmpeg version n?(\d+(?:\.\d+){0,2})", r.stdout or "")
        return tuple(int(x) for x in m_.group(1).split(".")) if m_ else None
    except Exception:
        return None


def latest_ffmpeg_version(timeout=8):
    """Newest release version of ffmpeg for Windows as a tuple (gyan.dev); None when offline."""
    import urllib.request
    try:
        req = urllib.request.Request(FFMPEG_LATEST_URL, headers={"User-Agent": "ShadowPlayTrackSplitter"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read(64).decode("ascii", "ignore").strip()
        m_ = re.match(r"(\d+(?:\.\d+){0,2})", txt)
        return tuple(int(x) for x in m_.group(1).split(".")) if m_ else None
    except Exception:
        return None


def is_own_ffmpeg(path):
    """True for the copy the program downloaded itself (only that one is ever updated automatically)."""
    try:
        return os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(os.path.abspath(ffmpeg_dir())))
    except Exception:
        return False


def _candidates(extra=None):
    here = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
    names = ["ffmpeg.exe", "ffmpeg"] if os.name == "nt" else ["ffmpeg"]
    out = []
    if extra:
        out.append(extra)
    for n in names:
        out.append(os.path.join(here, n))
    out.append("ffmpeg")
    for n in names:
        out.append(os.path.join(ffmpeg_dir(), n))
    if os.name == "nt":
        out += [r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
                r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
                r"C:\ffmpeg\bin\ffmpeg.exe"]
    return out


def find_ffmpeg(extra=None):
    for c in _candidates(extra):
        try:
            r = subprocess.run([c, "-version"], capture_output=True, creationflags=NO_WINDOW)
            if r.returncode == 0:
                return c
        except OSError:
            pass
    return None


def video_gaps(ffmpeg, video):
    """Holes in the video's own timeline (frames missing after a repair): returns
    (frames, fps, [(time, hole_seconds), ...]) or None when ffprobe is not available."""
    d = os.path.dirname(ffmpeg) if os.path.dirname(ffmpeg) else ""
    cands = [os.path.join(d, "ffprobe.exe"), os.path.join(d, "ffprobe"), "ffprobe"]
    for c in cands:
        try:
            r = _run([c, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                      "-of", "csv=p=0", video], text=True)
        except OSError:
            continue
        if r.returncode != 0:
            continue
        ts = []
        for line in (r.stdout or "").split():
            try:
                ts.append(float(line.strip(",")))
            except ValueError:
                pass
        if len(ts) < 50:
            return None
        t = np.sort(np.array(ts))
        dt = np.diff(t)
        med = float(np.median(dt))
        if med <= 0:
            return None
        big = np.where(dt > max(3 * med, 0.2))[0]
        return len(t), 1.0 / med, [(float(t[i]), float(dt[i] - med)) for i in big]
    return None


def _run(cmd, **kw):
    """Like subprocess.run(capture_output=True), but ffmpeg is stopped when the user presses Stop."""
    check_cancel()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NO_WINDOW, **kw)
    while True:
        try:
            out, err = p.communicate(timeout=0.25)
            break
        except subprocess.TimeoutExpired:
            if CANCEL.is_set():
                p.kill()
                p.communicate()
                raise Cancelled()
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


# ------------------------------------------------------------------- ADTS
def parse_adts(data):
    """List of (offset, length) of every AAC packet in an ADTS stream."""
    frames = []
    pos, n = 0, len(data)
    while pos + 7 <= n:
        if data[pos] == 0xFF and (data[pos + 1] & 0xF0) == 0xF0:
            ln = ((data[pos + 3] & 0x03) << 11) | (data[pos + 4] << 3) | (data[pos + 5] >> 5)
            if ln >= 7 and pos + ln <= n:
                frames.append((pos, ln))
                pos += ln
                continue
        pos += 1
    return frames


# --------------------------------------------------------------- features
def frame_features(stream, channels, total_frames=None, progress=None):
    """Per AAC packet: loudness (m) and L-R difference (s)."""
    s_list, m_list = [], []
    bpf = FRAME * channels * 2
    block = bpf * 4096
    leftover = b""
    done = 0
    while True:
        chunk = stream.read(block)
        if not chunk:
            break
        buf = leftover + chunk
        usable = (len(buf) // bpf) * bpf
        leftover = buf[usable:]
        if usable == 0:
            continue
        x = np.frombuffer(buf[:usable], dtype=np.int16).astype(np.float32)
        x = x.reshape(-1, FRAME, channels)
        L = x[:, :, 0]
        R = x[:, :, 1] if channels >= 2 else L
        m_list.append(np.sqrt((((L + R) / 2) ** 2).mean(axis=1)))
        s_list.append(np.sqrt((((L - R) / 2) ** 2).mean(axis=1)))
        done += usable // bpf
        if progress and total_frames:
            progress(min(1.0, done / total_frames))
    return np.concatenate(s_list), np.concatenate(m_list)


# ------------------------------------------------------- chunk schedule
def _period_from(mono, need):
    d = np.diff(np.r_[0, mono.astype(np.int8), 0])
    st = np.where(d == 1)[0]
    en = np.where(d == -1)[0]
    ln = en - st
    cand = ln[(ln >= 35) & (ln <= 60)]
    if len(cand) < need:
        return None
    lm = collections.Counter(cand.tolist()).most_common(1)[0][0]
    sp = np.diff(st[ln == lm])
    sp = sp[(sp > 60) & (sp < 140)]
    if len(sp) < need:
        return None
    return collections.Counter(sp.tolist()).most_common(1)[0][0], lm


# What each packet "says" about the track it belongs to (s: L-R difference, m: loudness).
# PC sound is normally real stereo (s large); the microphone is dual-mono (s about 0.44, plus its
# own noise floor); digital silence has s about 0.34 and says nothing.
MONO_PC = 0.05
SPARSE_STEREO = 0.15    # below this share of stereo packets the sound levels of PC and microphone must be used as evidence         
PC_MONO_S = 0.36        # mono PC sound has s of about 0.3 ...
MIC_S = 0.41            # ... the microphone about 0.44
PRIOR_W = 0.15          # weight of the coarse labelling when the signal is weak
STEREO_RICH = 0.30      # share of stereo packets (of all) from which the PC sound counts as 'mostly stereo'


def find_schedule(s, m):
    """(period, mic chunk length, mono_pc) of the interleaving, or None if the sound is not interleaved.
    The microphone chunks are dual-mono; digital silence of the PC looks mono as well and is ignored."""
    stereo = float(np.mean(s > 1.0)) >= MONO_PC
    if stereo:
        r = _period_from(s < 0.5, 20) or _period_from((s < 0.5) & (m >= 1), 12)
        if r:
            return r[0], r[1], float(np.mean(s > 1.0)) < SPARSE_STEREO
    q = ((s >= 0.40) & (s < 0.5)).astype(np.int8)                  # microphone-like packet
    sm = (np.convolve(q, np.ones(5), "same") >= 3).astype(np.int8)  # remove isolated outliers
    r = _period_from(sm, 20)
    return (r[0], r[1], True) if r else None


# NOTE on the name `mono_pc`: it is True whenever the PC sound has too few stereo packets to tell PC from the
# microphone by stereo alone (almost always mono PC sound, or less than SPARSE_STEREO of stereo packets); the
# sound levels (s, m) are then used as evidence as well.
def lattice_labels(s, m, P, Lm, mono_pc=False, switch_cost=150.0, progress=None):
    """Coarse labelling: chunks follow a strict schedule of period P, rare phase shifts are allowed but
    expensive.  Robust where the signal is weak (quiet or mono-sounding passages), but the real chunk
    lengths jitter by a packet or two, so its borders drift: segment_labels() refines them."""
    n = len(s)
    e = np.zeros(n)
    low = s < 0.5
    e[s > 1.0] = 1.0
    if float(np.mean(s > 1.0)) < 0.05:
        e[low & (m >= 30)] = -1.0
        e[low & (m >= 5) & (m < 30)] = -0.4
    if mono_pc:
        e[(s < PC_MONO_S) & (m > 2)] = 0.7
        e[(s >= MIC_S) & (s < 0.5)] = -0.4
    phi = np.arange(P)
    T = ((np.arange(P)[:, None] - phi[None, :]) % P) < Lm
    SG = np.where(T, -1.0, 1.0)
    sc = np.zeros(P)
    stay = np.zeros((n, P), dtype=bool)
    g = np.zeros(n, dtype=np.int16)
    step = max(1, n // 50)
    for i in range(n):
        gi = int(np.argmax(sc))
        alt = sc[gi] - switch_cost
        st_ = sc >= alt
        stay[i] = st_
        g[i] = gi
        sc = np.where(st_, sc, alt) + SG[i % P] * e[i]
        if progress and i % step == 0:
            progress(i / n)
    cur = int(np.argmax(sc))
    phases = np.zeros(n, dtype=np.int16)
    for i in range(n - 1, -1, -1):
        phases[i] = cur
        if not stay[i, cur]:
            cur = int(g[i])
    mono_lab = ((np.arange(n) - phases) % P) < Lm
    return (~mono_lab).astype(np.int8)


def segment_labels(s, m, P, Lm, mono_pc=False, prior=None, lmin=8, progress=None):
    """Label of every packet: 1 = stereo (PC), 0 = mono (mic), plus the list of chunks.

    The recording is cut into alternating chunks (PC, mic, PC, ...).  A chunk normally has the
    nominal length (P - Lm packets for PC, Lm for the mic) but may be a few packets longer or
    shorter, or span two chunks when the other track delivered nothing in between.  Dynamic
    programming picks the cut that agrees best with the signal; every deviation from the nominal
    length costs `lam` per packet (`jump` extra for each additional chunk).  Where the signal says
    nothing (silence) the nominal rhythm simply goes on."""
    n = len(s)
    nom = {1: P - Lm, 0: Lm}
    lam, jump = (1.0, 20.0) if mono_pc else (0.5, 10.0)
    stereo_rich = float(np.mean(s > 1.0)) >= STEREO_RICH
    e = np.zeros(n)
    e[s > 1.0] = 1.0                                   # stereo: PC
    if float(np.mean(s > 1.0)) < 0.05:                 # (almost) no stereo: the microphone's own sound counts
        low = s < 0.5
        e[low & (m >= 30)] = -1.0
        e[low & (m >= 5) & (m < 30)] = -0.4
    if mono_pc:
        e[(s < PC_MONO_S) & (m > 2)] = 0.7             # mono PC sound: low s ...
        e[(s >= MIC_S) & (s < 0.5)] = -0.4             # ... microphone: higher s
    elif float(np.mean(s > 1.0)) >= STEREO_RICH:
        # weak extra vote in quiet passages (only if the PC sound is stereo most of the time, otherwise
        # the levels of s of PC and microphone overlap and would mislead): the microphone's dual-mono packets have s of about 0.44
        # (with some noise: m >= 3), a quiet mono-sounding PC passage clearly lower.  Digital silence
        # has a similar s and says nothing, hence the m conditions.
        quiet = (s < 0.5) & (m >= 3)
        if int(quiet.sum()) >= 2000:
            fp = float(np.median(s[quiet]))            # typical s of the microphone (about 0.44)
            mic_like = ((s >= fp - 0.03) & (m > 20)) | ((s >= fp - 0.01) & (m >= 3))
            low = s < 0.5
            e[low] -= 0.1 * np.where(mic_like, 1.0, np.where(s <= fp - 0.12, -1.0, 0.0))[low]
    if prior is not None and not stereo_rich:
        # little stereo sound to go by: stay close to the coarse labelling, only its borders may move
        e = e + PRIOR_W * (2.0 * prior - 1.0)
    cs = np.r_[0.0, np.cumsum(e)]
    lmax = 3 * max(nom.values()) + 10
    Ls = np.arange(lmin, lmax + 1)
    pen = {}
    for t in (0, 1):
        p = np.full(len(Ls), np.inf)
        for k in (1, 2, 3):
            p = np.minimum(p, lam * np.abs(Ls - k * nom[t]) + jump * (k - 1))
        pen[t] = p
    sg = {1: 1.0, 0: -1.0}
    f = {0: np.full(n + 1, -np.inf), 1: np.full(n + 1, -np.inf)}
    arg = {0: np.zeros(n + 1, dtype=np.int16), 1: np.zeros(n + 1, dtype=np.int16)}
    step = max(1, n // 50)
    for i in range(1, n + 1):
        for t in (0, 1):
            best, bl = -np.inf, 0
            if i <= lmax:                      # the first run may start at 0 with any length
                best, bl = sg[t] * cs[i], i
            ok = Ls <= i
            if ok.any():
                L = Ls[ok]
                cand = f[1 - t][i - L] + sg[t] * (cs[i] - cs[i - L]) - pen[t][ok]
                j = int(np.argmax(cand))
                if cand[j] > best:
                    best, bl = float(cand[j]), int(L[j])
            f[t][i] = best
            arg[t][i] = bl
        if progress and i % step == 0:
            progress(i / n)
    t = 1 if f[1][n] >= f[0][n] else 0
    lab = np.zeros(n, dtype=np.int8)
    i = n
    runs = []
    while i > 0:
        L = int(arg[t][i])
        lab[i - L:i] = t
        runs.append((i - L, i, t))
        i -= L
        t = 1 - t
    runs.reverse()
    return lab, runs


def odd_chunks(runs, P, Lm, tol=3):
    """Chunks whose length is neither one nominal chunk nor two or three of them in a row
    (those are ordinary: the other track simply delivered nothing in between)."""
    nom = {1: P - Lm, 0: Lm}
    out = []
    for b, e, t in runs[1:-1]:
        if min(abs((e - b) - k * nom[t]) for k in (1, 2, 3)) > tol:
            out.append((b, e - b, t))
    return out


def label_runs(lab):
    d = np.diff(np.r_[2, lab, 2])
    b = np.where(d != 0)[0]
    return [(int(b[k]), int(b[k + 1]), int(lab[b[k]])) for k in range(len(b) - 1)]


def build_tracks(data, frames, runs, n):
    """Cut the interleaved packet stream into two tracks (bit-exact).

    Each track is simply its own chunks one after another: nothing is inserted, nothing is shifted.
    (When one track delivers two chunks in a row, the other one is not lost - it is only late.)"""
    stereo, mono = bytearray(), bytearray()
    for b, e, t in runs:
        # The decoder smears each PC -> mic switch over 1 packet: the stereo run looks 1 packet
        # longer and the mono run 1 packet shorter. Restore the true packet borders.
        if t == 1:
            pb, pe = b, (n if e >= n else min(e, n) - 1)
        else:
            pb, pe = max(b - 1, 0), e
        if pe > pb:
            chunk = data[frames[pb][0]: frames[pe - 1][0] + frames[pe - 1][1]]
            (stereo if t == 1 else mono).extend(chunk)
    return stereo, mono


# ----------------------------------------------------- normal videos: tracks
AUDIO_EXT = {"aac": ".m4a", "mp3": ".mp3", "opus": ".opus", "vorbis": ".ogg", "flac": ".flac",
             "ac3": ".ac3", "eac3": ".eac3", "alac": ".m4a"}


def probe_audio(ffmpeg, video, lang="en", sizes=True):
    """List of audio streams: [{'index', 'codec', 'title', 'mb'}] (index counts audio streams from 0)."""
    M = MSG.get(lang, MSG["en"])
    r = _run([ffmpeg, "-hide_banner", "-i", video], text=True)
    err = r.stderr or ""
    if "moov atom not found" in err:
        raise SplitError(M["moov"])
    streams = []
    cur = None
    for line in err.splitlines():
        m_ = re.search(r"Stream #0:\d+.*?: (\w+): (\w+)", line)
        if m_:
            cur = None
            if m_.group(1) == "Audio":
                cur = {"index": len(streams), "codec": m_.group(2), "title": "", "mb": 0.0}
                streams.append(cur)
            continue
        if cur is not None:
            t_ = re.match(r"\s+(title|handler_name)\s*:\s*(.+)$", line)
            if t_:
                val = t_.group(2).strip()
                generic = re.search(r"(?i)(handler|handle$|core media|sound media|audio media)", val)
                if t_.group(1) == "title" or not generic:
                    cur["title"] = val
    for s in (streams if sizes else []):
        rr = _run([ffmpeg, "-hide_banner", "-i", video, "-map", "0:a:%d" % s["index"],
                   "-c", "copy", "-f", "null", "-"], text=True)
        mm = re.findall(r"audio:(\d+)\s*(?:KiB|kB|KB)", rr.stderr or "")
        s["mb"] = int(mm[-1]) / 1024.0 if mm else 0.0
    return streams


def _label(s):
    lab = re.sub(r"[^\w\-]+", "_", s["title"], flags=re.UNICODE).strip("_") if s["title"] else ""
    return lab or "track%d" % (s["index"] + 1)


def extract_tracks(video, ffmpeg=None, keep=0, save_others=True, save_kept=False,
                   log=print, progress=None, lang="en", save_tracks=None, out_dir=None):
    """Normal video with one or more audio tracks.
    keep >= 0: the video keeps track `keep` (0-based); keep == -1: the video gets no sound.
    save_others: save the tracks NOT kept in the video as separate audio files.
    save_kept: also save the kept track as an audio file.
    save_tracks: list of 0-based track numbers to save as audio files; overrides save_others/save_kept.
    out_dir: folder for the results (default: next to the video).  No re-encoding."""
    M = MSG.get(lang, MSG["en"])

    def say(key, **kw):
        check_cancel()
        log(M[key].format(**kw))

    ff = find_ffmpeg(ffmpeg)
    if not ff:
        raise SplitError(M["no_ffmpeg"])
    say("x1")
    streams = probe_audio(ff, video, lang)
    if not streams:
        raise SplitError(M["x_none"])
    say("x_found", n=len(streams))
    for s in streams:
        say("x_track", i=s["index"] + 1, codec=s["codec"],
            title=(" '%s'" % s["title"]) if s["title"] else "", size=s["mb"])
    if not (-1 <= keep < len(streams)):
        raise SplitError(M["x_bad"])
    base = out_base(video, out_dir)
    if save_tracks is not None:
        to_save = [s for s in streams if s["index"] in save_tracks]
    else:
        to_save = [s for s in streams if (s["index"] != keep and save_others) or (s["index"] == keep and save_kept)]
    vlabel = _label(streams[keep]) if keep >= 0 else "noaudio"
    # one track, kept and saved as audio: a video copy would be pointless -> audio only
    audio_only = keep >= 0 and len(streams) == 1 and any(s["index"] == keep for s in to_save)
    patterns = ([] if audio_only else ["{base}_video_{vl}{n}.mp4"]) + \
               ["{base}_audio_%s{n}%s" % (_label(s), AUDIO_EXT.get(s["codec"], ".mka")) for s in to_save]
    suf = unique_suffix(patterns, base=base, vl=vlabel)
    out = "%s_video_%s%s.mp4" % (base, vlabel, suf)
    files = []
    ok = False
    try:
        if audio_only:
            out = None
        else:
            if keep >= 0:
                say("x_video", i=keep + 1)
                maps = ["-map", "0:v", "-map", "0:a:%d" % keep]
            else:
                say("x_video_none")
                maps = ["-map", "0:v"]
            r = _run([ff, "-y", "-v", "error", "-i", video] + maps + ["-c", "copy", out], text=True)
            if r.returncode != 0:
                raise ff_error(M, r)
        if progress:
            progress(0.5 if to_save else 1.0)
        for n_, s in enumerate(to_save):
            fn = "%s_audio_%s%s%s" % (base, _label(s), suf, AUDIO_EXT.get(s["codec"], ".mka"))
            say("x_audio", i=s["index"] + 1)
            files.append(fn)
            r = _run([ff, "-y", "-v", "error", "-i", video, "-map", "0:a:%d" % s["index"],
                      "-vn", "-c", "copy", fn], text=True)
            if r.returncode != 0:
                raise ff_error(M, r)
            if progress:
                progress(0.5 + 0.5 * (n_ + 1) / len(to_save))
        if out:
            say("x_done", out=out)
            if files:
                say("x_done2", files=", ".join(files))
        else:
            say("x_done_audio", files=", ".join(files))
        ok = True
        return {"video": out, "audio": files}
    finally:
        if not ok:                                   # never leave half-written results behind
            for f in ([out] if out else []) + files:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except OSError:
                    pass


# ------------------------------------------------------------------ main
def process(video, ffmpeg=None, stream=0, swap=False, match_video=False, video_scale=1.0,
            save_features=True, log=print, progress=None, lang="en", save_audio_files=True,
            audio_which="both", out_dir=None, audio_only=False, fit_audio=False):
    """Split the interleaved audio of `video`. Returns a dict with output paths."""
    M = MSG.get(lang, MSG["en"])

    def say(key, **kw):
        check_cancel()
        log(M[key].format(**kw))

    def prog(a, b):
        # report progress as a fraction of the whole job
        if progress:
            def _p(f):
                check_cancel()
                progress(a + (b - a) * f)
            return _p
        return None

    ff = find_ffmpeg(ffmpeg)
    if not ff:
        raise SplitError(M["no_ffmpeg"])
    base = out_base(video, out_dir)
    fd, raw = tempfile.mkstemp(prefix="_raw_", suffix=".aac", dir=os.path.dirname(base))
    os.close(fd)
    outputs = {}
    fa = fb = out = ma = mb = None
    ok = False
    try:
        say("s1")
        r = _run([ff, "-y", "-v", "error", "-i", video, "-map", "0:a:%d" % stream,
                  "-c:a", "copy", "-f", "adts", raw], text=True)
        if r.returncode != 0 or not os.path.exists(raw):
            if "moov atom not found" in (r.stderr or ""):
                raise SplitError(M["moov"])
            raise ff_error(M, r)
        if progress:
            progress(0.05)

        say("s2")
        with open(raw, "rb") as f:
            data = f.read()
        frames = parse_adts(data)
        if not frames:
            raise SplitError(M["e_extract"].format(err="no AAC packets"))
        h = frames[0][0]
        cfg = ((data[h + 2] & 1) << 2) | (data[h + 3] >> 6)
        ch = 1 if cfg == 1 else 2
        sr = SF_TABLE[(data[h + 2] >> 2) & 15]
        say("packets", n=len(frames), min=len(frames) * FRAME / sr / 60, sr=sr)

        say("s3")
        p = subprocess.Popen([ff, "-v", "error", "-i", raw, "-f", "s16le", "-ac", str(ch), "-"],
                             stdout=subprocess.PIPE, creationflags=NO_WINDOW)
        s, m = frame_features(p.stdout, ch, len(frames), prog(0.05, 0.45))
        p.wait()
        if abs(len(s) - len(frames)) > 2:
            say("mismatch", a=len(s), b=len(frames))
        n = min(len(s), len(frames))
        s, m = s[:n], m[:n]
        rd_, bn_ = reports_dir(), os.path.basename(base)
        fsuf = unique_suffix(["{d}/{b}_features{n}.npz"], d=rd_, b=bn_)      # never overwrite an earlier run
        feat = os.path.join(rd_, "%s_features%s.npz" % (bn_, fsuf))
        if save_features:   # small diagnostic file; lets the schedule be analysed without the video
            np.savez_compressed(feat, s=s.astype(np.float16), m=m.astype(np.float16),
                                L=np.array([ln for _, ln in frames], dtype=np.uint16),
                                H=np.array([list(bytes(data[o + 7:o + 11]).ljust(4, b"\0")) for o, _ in frames], dtype=np.uint8))

        def stamp_m(sec):
            return "%d:%06.3f" % (int(sec) // 60, sec - 60 * (int(sec) // 60))

        def stamp_s(sec):
            sec = int(sec)
            return "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)

        def stamp(k):
            sec = k * FRAME / sr / 2           # position in the finished tracks (the mixed stream is twice as long)
            return "%d:%02d:%06.3f" % (int(sec) // 3600, int(sec) % 3600 // 60, sec % 60)

        est = find_schedule(s, m)
        if est is None:
            raise SplitError(M["no_sched"].format(path=feat if save_features else "-"))
        P, Lm, mono_pc = est
        say("sched", p=P, lm=Lm, ls=P - Lm)
        coarse = lattice_labels(s, m, P, Lm, mono_pc=mono_pc, progress=prog(0.45, 0.6))
        lab, runs = segment_labels(s, m, P, Lm, mono_pc=mono_pc, prior=coarse, progress=prog(0.6, 0.75))

        nomlen = {1: P - Lm, 0: Lm}
        odd = odd_chunks(runs, P, Lm)
        say("s4", n=len(odd))
        for b_, _, _ in odd[:15]:
            say("shift_at", t=stamp(b_))
        a_st = 100 * float((lab[s > 1.0] == 1).mean()) if (s > 1.0).any() else 100.0
        mono_sel = ((s >= 0.41) & (s < 0.5) & (m >= 30)) if mono_pc else ((s < 0.5) & (m >= 30))
        a_mo = 100 * float((lab[mono_sel] == 0).mean()) if mono_sel.any() else 100.0
        say("agree", a=a_st, b=a_mo)
        # mono agreement is naturally lower when the PC sound itself is mono for a while, so it
        # only counts when it is really poor
        if (a_st < 90 or a_mo < 40) and not mono_pc:
            say("low_agree")

        stereo, mono = build_tracks(data, frames, runs, n)
        if swap:
            stereo, mono = mono, stereo
        suf = unique_suffix(["{base}_fixed{n}.mp4", "{base}_track1_PC{n}.m4a", "{base}_track2_MIC{n}.m4a"],
                            base=base)
        fa, fb = "%s_track1_PC%s.aac" % (base, suf), "%s_track2_MIC%s.aac" % (base, suf)
        with open(fa, "wb") as f:
            f.write(stereo)
        with open(fb, "wb") as f:
            f.write(mono)
        dur_a = len(parse_adts(bytes(stereo))) * FRAME / sr
        dur_b = len(parse_adts(bytes(mono))) * FRAME / sr
        say("dur", a=dur_a / 60, b=dur_b / 60)
        if progress:
            progress(0.8)

        if audio_only:                                # no video file: just the two audio tracks
            ma, mb = fa.replace(".aac", ".m4a"), fb.replace(".aac", ".m4a")
            want = {fa: audio_which in ("both", "pc"), fb: audio_which in ("both", "mic")}
            for f in (fa, fb):
                if want[f]:
                    r = _run([ff, "-y", "-v", "error", "-i", f, "-c", "copy", "-bsf:a", "aac_adtstoasc",
                              f.replace(".aac", ".m4a")], text=True)
                    if r.returncode != 0:
                        raise SplitError(M["nospace"] if "No space left" in (r.stderr or "")
                                         else M["e_mux"].format(a=fa, b=fb))
                os.remove(f)
            ma = ma if want[fa] else None
            mb = mb if want[fb] else None
            if progress:
                progress(1.0)
            say("done3", files=", ".join(x for x in (ma, mb) if x))
            ok = True
            return {"video": None, "pc": ma, "mic": mb, "listen": [], "audio_min": max(dur_a, dur_b) / 60,
                    "video_min": None}

        scale = video_scale
        vr = _run([ff, "-i", video, "-map", "0:v:0", "-c", "copy", "-f", "null", "-"], text=True)
        mt = re.findall(r"time=(\d+):(\d+):([\d.]+)", vr.stderr)
        vdur = None
        if mt:
            hh, mm, ss = mt[-1]
            vdur = int(hh) * 3600 + int(mm) * 60 + float(ss)
            say("vdur", v=vdur / 60)
        if match_video and vdur:
            scale = max(dur_a, dur_b) / vdur
            say("stretch", s=scale)
        elif vdur and max(dur_a, dur_b) - vdur > 0.02 * vdur:
            say("hint_stretch", d=(max(dur_a, dur_b) - vdur) / 60)
        if fit_audio and vdur and not match_video:
            # the other way round: the SOUND is sped up / slowed down (re-encoded, pitch stays) to the video length
            for which in ("a", "b"):
                src = fa if which == "a" else fb
                ratio = (dur_a if which == "a" else dur_b) / vdur
                if abs(ratio - 1.0) < 0.0005 or not 0.1 <= ratio <= 10.0:
                    continue
                tmp = src + ".fit"
                chain, rest = [], ratio                    # one atempo filter handles 0.5 ... 2 only
                while rest < 0.5 or rest > 2.0:
                    step = 0.5 if rest < 0.5 else 2.0
                    chain.append("atempo=%.1f" % step)
                    rest /= step
                chain.append("atempo=%.6f" % rest)
                r = _run([ff, "-y", "-v", "error", "-i", src, "-af", ",".join(chain), "-c:a", "aac",
                          "-b:a", "192k", "-f", "adts", tmp], text=True)
                if r.returncode != 0:
                    if "No space left" in (r.stderr or ""):
                        raise SplitError(M["nospace"])
                    raise SplitError(M["e_mux"].format(a=fa, b=fb))
                os.replace(tmp, src)
                say("fit", n="PC" if which == "a" else "Mic", r=ratio)

        vg = video_gaps(ff, video)
        if vg:
            nfr, fps, gaps = vg
            if gaps:
                say("vgaps", n=len(gaps), tot=sum(g for _, g in gaps) / 60.0)
                for tt, g in sorted(gaps, key=lambda x: -x[1])[:15]:
                    say("vgap", t=stamp_s(tt), g=g)
            else:
                say("vgaps0", n=nfr, f=fps, e=nfr / fps / 60.0)

        listen = []                                   # (seconds in the finished video, text)
        for b_, ln_, t_ in odd:
            listen.append((b_ * FRAME / sr / 2, M["ev_shift"].format(n=ln_, nom=nomlen[t_])))
        if vg and vg[2]:
            for tt, g in vg[2][:30]:
                listen.append((tt, M["ev_vgap"].format(g=g)))

        say("s5")
        out = "%s_fixed%s.mp4" % (base, suf)
        cmd = [ff, "-y", "-v", "error"]
        if scale != 1.0:
            cmd += ["-itsscale", "%.6f" % scale]
        cmd += ["-i", video, "-i", fa, "-i", fb, "-map", "0:v:0", "-map", "1:a", "-map", "2:a",
                "-c", "copy", "-bsf:a", "aac_adtstoasc",
                "-metadata:s:a:0", "title=PC", "-metadata:s:a:1", "title=Mic",
                "-metadata:s:a:0", "handler_name=PC", "-metadata:s:a:1", "handler_name=Mic", out]
        r = _run(cmd, text=True)
        if r.returncode != 0:
            log(r.stderr)
            if "No space left" in (r.stderr or ""):
                raise SplitError(M["nospace"])
            raise SplitError(M["e_mux"].format(a=fa, b=fb))
        ma, mb = fa.replace(".aac", ".m4a"), fb.replace(".aac", ".m4a")
        want = {fa: audio_which in ("both", "pc"), fb: audio_which in ("both", "mic")}
        for f in (fa, fb):
            if save_audio_files and want[f]:
                _run([ff, "-y", "-v", "error", "-i", f, "-c", "copy", "-bsf:a", "aac_adtstoasc",
                      f.replace(".aac", ".m4a")])
            os.remove(f)
        if progress:
            progress(1.0)
        say("done", out=out)
        if not save_audio_files:
            ma = mb = None
        else:
            if not want[fa]:
                ma = None
            if not want[fb]:
                mb = None
            say("done3", files=", ".join(x for x in (ma, mb) if x))
        listen.sort()
        say("ev_head", n=len(listen))
        for sec_, txt in listen[:150]:
            log("      %s - %s" % (stamp_m(sec_), txt))
        outputs = {"video": out, "pc": ma, "mic": mb, "listen": listen, "audio_min": max(dur_a, dur_b) / 60,
                   "video_min": (vdur / 60) if vdur else None}
        ok = True
        return outputs
    except OSError as ex:
        if ex.errno == errno.ENOSPC:
            raise SplitError(M["nospace"])
        raise
    finally:
        if not ok and out and os.path.exists(out):    # never leave a half-written video behind
            try:
                os.remove(out)
            except OSError:
                pass
        if not ok:
            for f in (ma, mb):
                if f and os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
        for f in (raw, fa, fb):
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass
