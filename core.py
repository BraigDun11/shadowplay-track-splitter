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
import os
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
        "no_sched": "Could not detect the chunk schedule. This recording is probably structured differently. "
                    "A diagnostic file was saved: {path}",
        "sched": "    schedule: period {p} packets (mono chunk {lm}, stereo chunk {ls})",
        "s4": "4/5 Splitting. Schedule shifts found: {n}",
        "shift_at": "      around {t}",
        "agree": "    agreement with signal: stereo {a:.1f}%, mono {b:.1f}%",
        "low_agree": "    WARNING: low agreement - result may contain mixed-up pieces.",
        "filled": "    silence inserted to keep sync: PC {a:.1f} s, mic {b:.1f} s",
        "dur": "    track length: PC {a:.2f} min, mic {b:.2f} min",
        "vdur": "    video length (picture only): {v:.2f} min",
        "stretch": "    stretching video by x{s:.4f} to match audio",
        "hint_stretch": "    HINT: audio is {d:.1f} min longer than video. If sound lags behind the picture more and "
                        "more towards the end, enable 'Stretch video to match audio'.",
        "s5": "5/5 Building final video with two audio tracks...",
        "e_mux": "Could not build the video, but tracks were saved: {a} and {b}",
        "done": "DONE: {out}",
        "done2": "Tracks separately: {a} and {b}",
    },
    "ru": {
        "no_ffmpeg": "Не найден ffmpeg. Положите ffmpeg.exe рядом с программой, добавьте его в PATH или выберите вручную.",
        "s1": "1/5 Достаю аудио из видео (без перекодирования)...",
        "e_extract": "Не получилось достать аудио (возможно, оно не AAC):\n{err}",
        "s2": "2/5 Разбираю аудиопакеты...",
        "packets": "    пакетов: {n} (~{min:.1f} мин), {sr} Гц",
        "s3": "3/5 Анализирую звук (для длинных записей несколько минут)...",
        "mismatch": "    ВНИМАНИЕ: число кадров звука ({a}) и пакетов ({b}) не совпало",
        "no_sched": "Не удалось определить расписание кусков. Скорее всего, запись устроена иначе. "
                    "Диагностический файл сохранён: {path}",
        "sched": "    расписание: период {p} пакетов (моно-кусок {lm}, стерео-кусок {ls})",
        "s4": "4/5 Разделяю. Сдвигов расписания найдено: {n}",
        "shift_at": "      около {t}",
        "agree": "    согласие с признаками: стерео {a:.1f}%, моно {b:.1f}%",
        "low_agree": "    ВНИМАНИЕ: согласие низкое - в дорожках могут быть перепутанные кусочки.",
        "filled": "    вставлено тишины для сохранения синхронизации: ПК {a:.1f} с, микрофон {b:.1f} с",
        "dur": "    длина дорожек: ПК {a:.2f} мин, микрофон {b:.2f} мин",
        "vdur": "    длина видео (только картинка): {v:.2f} мин",
        "stretch": "    растягиваю видео в {s:.4f} раза, чтобы совпало со звуком",
        "hint_stretch": "    ПОДСКАЗКА: звук длиннее видео на {d:.1f} мин. Если звук всё сильнее отстаёт от "
                        "картинки к концу, включите «Растянуть видео под длину звука».",
        "s5": "5/5 Собираю итоговое видео с двумя дорожками...",
        "e_mux": "Не удалось собрать видео, но дорожки сохранены: {a} и {b}",
        "done": "ГОТОВО: {out}",
        "done2": "Дорожки отдельно: {a} и {b}",
    },
}


class SplitError(Exception):
    pass


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


# ----------------------------------------------------------------- ffmpeg
def _candidates(extra=None):
    here = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
    names = ["ffmpeg.exe", "ffmpeg"] if os.name == "nt" else ["ffmpeg"]
    out = []
    if extra:
        out.append(extra)
    for n in names:
        out.append(os.path.join(here, n))
    out.append("ffmpeg")
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


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW, **kw)


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
def estimate_period(s):
    """Find the schedule period and the length of the mono (microphone) chunk.
    The microphone track has L == R exactly, so s == 0 on its chunks."""
    mono = s < 0.5
    d = np.diff(np.r_[0, mono.astype(np.int8), 0])
    st = np.where(d == 1)[0]
    en = np.where(d == -1)[0]
    ln = en - st
    cand = ln[(ln >= 35) & (ln <= 60)]
    if len(cand) < 20:
        return None
    lm = collections.Counter(cand.tolist()).most_common(1)[0][0]
    sp = np.diff(st[ln == lm])
    sp = sp[(sp > 60) & (sp < 140)]
    if len(sp) < 20:
        return None
    return collections.Counter(sp.tolist()).most_common(1)[0][0], lm


def lattice_labels(s, m, P, Lm, switch_cost=150.0, progress=None):
    """Label of every packet: 1 = stereo (PC), 0 = mono (mic).
    Chunks follow a strict schedule of period P; rare phase shifts are allowed
    but expensive, so random noise does not trigger them."""
    n = len(s)
    e = np.zeros(n)
    low = s < 0.5
    e[s > 1.0] = 1.0
    e[low & (m >= 30)] = -1.0
    e[low & (m >= 5) & (m < 30)] = -0.4
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
    return (~mono_lab).astype(np.int8), phases


def label_runs(lab):
    d = np.diff(np.r_[2, lab, 2])
    b = np.where(d != 0)[0]
    return [(int(b[k]), int(b[k + 1]), int(lab[b[k]])) for k in range(len(b) - 1)]


def silent_packet(ffmpeg, data, frames, m, sr, ch):
    """One AAC packet of digital silence: taken from the file itself if possible."""
    cnt = collections.Counter()
    for i in np.where(m < 0.5)[0][:5000]:
        if i < len(frames):
            o, l = frames[i]
            cnt[bytes(data[o:o + l])] += 1
    if cnt:
        pk, c = cnt.most_common(1)[0]
        if c >= 3:
            return pk
    r = _run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
              "anullsrc=r=%d:cl=%s" % (sr, "stereo" if ch == 2 else "mono"),
              "-t", "1", "-c:a", "aac", "-f", "adts", "-"])
    d = r.stdout
    fr = parse_adts(d)
    o, l = fr[len(fr) // 2]
    return d[o:o + l]


def build_tracks(data, frames, runs, n, P, Lm, sil):
    """Cut the interleaved packet stream into two tracks (bit-exact)."""
    stereo, mono = bytearray(), bytearray()
    nom = {1: P - Lm, 0: Lm}
    filled = {1: 0, 0: 0}
    for k, (b, e, t) in enumerate(runs):
        # The decoder smears each switch over 1 packet: the stereo run looks 1 packet
        # longer and the mono run 1 packet shorter. Restore the true packet borders.
        if t == 1:
            pb, pe, out, other = b, min(e, n) - 1, stereo, mono
            if e >= n:
                pe = n
        else:
            pb, pe, out, other = max(b - 1, 0), e, mono, stereo
        if pe > pb:
            out += data[frames[pb][0]: frames[pe - 1][0] + frames[pe - 1][1]]
        if 0 < k < len(runs) - 1:
            ln = e - b
            cnt = int(round(ln / nom[t]))
            true_other = (nom[1 - t] - 1) if t == 0 else (nom[1 - t] + 1)
            miss = (cnt - 1) * true_other   # several chunks in a row -> other track lost a chunk
            if cnt <= 1 and ln < nom[t] - 3:  # a too-short chunk -> part of this track lost
                out += sil * (nom[t] - ln)
                filled[t] += nom[t] - ln
            if miss > 0:
                other += sil * miss
                filled[1 - t] += miss
    return stereo, mono, filled


# ------------------------------------------------------------------ main
def process(video, ffmpeg=None, stream=0, swap=False, match_video=False, video_scale=1.0,
            save_features=False, log=print, progress=None, lang="en"):
    """Split the interleaved audio of `video`. Returns a dict with output paths."""
    M = MSG.get(lang, MSG["en"])

    def say(key, **kw):
        log(M[key].format(**kw))

    def prog(a, b):
        # report progress as a fraction of the whole job
        if progress:
            return lambda f: progress(a + (b - a) * f)
        return None

    ff = find_ffmpeg(ffmpeg)
    if not ff:
        raise SplitError(M["no_ffmpeg"])
    base = os.path.splitext(video)[0]
    raw = base + "_raw.aac"
    outputs = {}
    try:
        say("s1")
        r = _run([ff, "-y", "-v", "error", "-i", video, "-map", "0:a:%d" % stream,
                  "-c:a", "copy", "-f", "adts", raw], text=True)
        if r.returncode != 0 or not os.path.exists(raw):
            raise SplitError(M["e_extract"].format(err=r.stderr))
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
        feat = base + "_features.npz"
        if save_features:
            np.savez_compressed(feat, s=s.astype(np.float16), m=m.astype(np.float16))

        def stamp(k):
            sec = int(k * FRAME / sr)
            return "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)

        est = estimate_period(s)
        if est is None:
            np.savez_compressed(feat, s=s.astype(np.float16), m=m.astype(np.float16))
            raise SplitError(M["no_sched"].format(path=feat))
        P, Lm = est
        say("sched", p=P, lm=Lm, ls=P - Lm)
        lab, phases = lattice_labels(s, m, P, Lm, progress=prog(0.45, 0.75))
        runs = label_runs(lab)

        shifts = np.where(np.diff(phases) != 0)[0]
        say("s4", n=len(shifts))
        for i in shifts[:15]:
            say("shift_at", t=stamp(i))
        a_st = 100 * float((lab[s > 1.0] == 1).mean()) if (s > 1.0).any() else 100.0
        a_mo = 100 * float((lab[(s < 0.5) & (m >= 30)] == 0).mean()) if ((s < 0.5) & (m >= 30)).any() else 100.0
        say("agree", a=a_st, b=a_mo)
        if min(a_st, a_mo) < 90:
            say("low_agree")

        sil = silent_packet(ff, data, frames, m, sr, ch)
        stereo, mono, filled = build_tracks(data, frames, runs, n, P, Lm, sil)
        say("filled", a=filled[1] * FRAME / sr, b=filled[0] * FRAME / sr)
        if swap:
            stereo, mono = mono, stereo
        fa, fb = base + "_track1_PC.aac", base + "_track2_MIC.aac"
        with open(fa, "wb") as f:
            f.write(stereo)
        with open(fb, "wb") as f:
            f.write(mono)
        dur_a = len(parse_adts(bytes(stereo))) * FRAME / sr
        dur_b = len(parse_adts(bytes(mono))) * FRAME / sr
        say("dur", a=dur_a / 60, b=dur_b / 60)
        if progress:
            progress(0.8)

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

        say("s5")
        out = base + "_fixed.mp4"
        cmd = [ff, "-y", "-v", "error"]
        if scale != 1.0:
            cmd += ["-itsscale", "%.6f" % scale]
        cmd += ["-i", video, "-i", fa, "-i", fb, "-map", "0:v:0", "-map", "1:a", "-map", "2:a",
                "-c", "copy", "-bsf:a", "aac_adtstoasc",
                "-metadata:s:a:0", "title=PC", "-metadata:s:a:1", "title=Mic", out]
        r = _run(cmd, text=True)
        if r.returncode != 0:
            log(r.stderr)
            raise SplitError(M["e_mux"].format(a=fa, b=fb))
        ma, mb = fa.replace(".aac", ".m4a"), fb.replace(".aac", ".m4a")
        for f in (fa, fb):
            _run([ff, "-y", "-v", "error", "-i", f, "-c", "copy", "-bsf:a", "aac_adtstoasc",
                  f.replace(".aac", ".m4a")])
            os.remove(f)
        if progress:
            progress(1.0)
        say("done", out=out)
        say("done2", a=ma, b=mb)
        outputs = {"video": out, "pc": ma, "mic": mb, "audio_min": max(dur_a, dur_b) / 60,
                   "video_min": (vdur / 60) if vdur else None}
        return outputs
    finally:
        if os.path.exists(raw):
            try:
                os.remove(raw)
            except OSError:
                pass
