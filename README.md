# ShadowPlay Track Splitter

**EN** | [RU ниже](#ru)

Splits the **PC-sound and microphone tracks** that get mixed into one audio stream after you repair a
damaged NVIDIA ShadowPlay recording (for example with [untrunc](https://github.com/anthwlock/untrunc)).

## The problem

You record with ShadowPlay with *separate audio tracks* (game + mic). The recording gets corrupted
(crash, power loss). After repair the picture is fine, but:

- the audio is **about twice as long** as the video;
- it plays ~1 second of PC sound, ~1 second of microphone, PC, mic ... on **one** track;
- the second audio track is empty.

The same problem is reported in untrunc issues
([#273](https://github.com/anthwlock/untrunc/issues/273), [#219](https://github.com/anthwlock/untrunc/issues/219),
[#78](https://github.com/anthwlock/untrunc/issues/78)).

## What this tool does

It finds the strict ~1-second schedule of the interleaved chunks and **rebuilds the two tracks from the
original AAC packets - no re-encoding, no quality loss, no AI**. Where the repair lost audio, it inserts silence
so the tracks stay in sync. The result is the video with two audio tracks plus both tracks as separate `.m4a` files.

## Use (Windows)

1. Download `ShadowPlayTrackSplitter.exe` from [Releases](../../releases).
2. You need [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) (essentials build). Put `ffmpeg.exe` next to the
   program, or add it to PATH, or pick it in the window.
3. Run the program, choose the repaired video, press **Split tracks**.
4. You get, next to the video: `*_fixed.mp4` (two audio tracks), `*_track1_PC.m4a`, `*_track2_MIC.m4a`
   and `*_report.txt`.

Options:

- **Swap tracks** - if PC and mic came out the other way round.
- **Stretch video to match audio length** - repair tools sometimes give the picture wrong timestamps, so the
  video is shorter than the sound and the lag grows towards the end. This option rescales video timestamps
  (no re-encoding). Use it when the log says the audio is much longer than the video.

Command line: `python cli.py video.mp4 [--swap] [--match-video] [--save-features]`.

## How it works (short)

The microphone track has identical left and right channels, the PC track does not. That gives a reliable
fingerprint of each packet. The chunks follow a fixed schedule (in our recordings 47 + 47 packets of 1024
samples), so the tool fits a periodic schedule to the fingerprints (rare phase shifts allowed) instead of
guessing every border separately. A lost chunk shows up as a break in the schedule and is filled with silence.

## Status and limits - please read

- Developed and verified on **one real recording** (about 1 hour 4 minutes per track) and on synthetic tests
  (`tests/test_synthetic.py`, bit-exact). Other recordings may be structured differently.
- Works with **AAC** audio and relies on "mic = identical left/right channels, PC = real stereo".
- If something is wrong, open an issue and attach `*_report.txt`; run with `--save-features` to also produce a
  small `*_features.npz` that lets the schedule be analysed without your video.
- The exe is not code-signed; Windows SmartScreen or an antivirus may warn about it. You can run
  `python gui.py` from source instead (needs Python 3 and `pip install numpy`).

## Build

`build_exe.bat` (needs Python), or let GitHub Actions do it (`.github/workflows/build.yml`).

License: MIT. Author: [BraigDun11](https://github.com/BraigDun11). Developed together with Claude (Anthropic's AI assistant).

---

<a name="ru"></a>
## RU

Разделяет **звук с ПК и микрофон**, которые смешались в один аудиопоток после восстановления повреждённой
записи NVIDIA ShadowPlay (например, программой untrunc).

**Проблема.** Вы пишете ShadowPlay с раздельными дорожками (игра + микрофон). Запись повреждается. После
восстановления картинка есть, но звук вдвое длиннее видео, на одной дорожке по очереди играют ~1 секунда
ПК, ~1 секунда микрофон, а вторая дорожка пустая.

**Что делает программа.** Находит строгое расписание кусков по ~1 секунде и **пересобирает две дорожки из
исходных AAC-пакетов: без перекодирования, без потери качества, без нейросетей**. Там, где при восстановлении
пропал звук, вставляет тишину, чтобы дорожки не разъехались.

**Как пользоваться (Windows).**
1. Скачайте `ShadowPlayTrackSplitter.exe` в разделе [Releases](../../releases).
2. Нужен [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) (сборка essentials): положите `ffmpeg.exe` рядом с
   программой, добавьте в PATH или выберите кнопкой в окне.
3. Запустите, выберите восстановленное видео, нажмите **«Разделить дорожки»**.
4. Рядом с видео появятся `*_fixed.mp4` (две дорожки), `*_track1_PC.m4a`, `*_track2_MIC.m4a`, `*_report.txt`.

Если ПК и микрофон оказались наоборот, включите **«Поменять дорожки местами»**. Если звук всё сильнее
отстаёт от картинки к концу, включите **«Растянуть видео под длину звука»**.

**Автор:** BraigDun11, разработано вместе с Claude (ИИ-ассистент Anthropic).

**Статус.** Проверено на одной реальной записи и на синтетических тестах. На других записях расписание может
быть иным: если что-то не так, создайте issue и приложите `*_report.txt` (и `*_features.npz`, если запускали
с `--save-features`).
