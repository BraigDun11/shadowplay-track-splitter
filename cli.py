# -*- coding: utf-8 -*-
"""Command line interface:  python cli.py video.mp4 [--swap] [--match-video]"""
import argparse
import sys

import core


def main():
    ap = argparse.ArgumentParser(description="Split interleaved ShadowPlay audio tracks after video repair")
    ap.add_argument("video")
    ap.add_argument("--stream", type=int, default=0, help="audio stream index holding the data (default 0)")
    ap.add_argument("--swap", action="store_true", help="swap PC / mic tracks")
    ap.add_argument("--match-video", action="store_true", help="stretch video timestamps to audio length")
    ap.add_argument("--video-scale", type=float, default=1.0, help="stretch video by this factor")
    ap.add_argument("--save-features", action="store_true", help="save a diagnostic .npz file")
    ap.add_argument("--ffmpeg", help="path to ffmpeg")
    ap.add_argument("--lang", choices=["en", "ru"], default=None)
    ap.add_argument("--extract", action="store_true",
                    help="normal video with several audio tracks: keep one track in the video "
                         "and save the others as audio files")
    ap.add_argument("--keep", type=int, default=1,
                    help="with --extract: number of the track to keep in the video (1, 2, ...; 0 = video without sound)")
    ap.add_argument("--no-save-others", action="store_true", help="with --extract: do not save other tracks")
    ap.add_argument("--save-kept", action="store_true", help="with --extract: also save the kept track as audio")
    ap.add_argument("--no-save-audio", action="store_true", help="repair mode: do not write separate .m4a files")
    a = ap.parse_args()
    lang = a.lang or core.detect_lang()
    try:
        if a.extract:
            core.extract_tracks(a.video, a.ffmpeg, a.keep - 1, not a.no_save_others, a.save_kept, print, None, lang)
            return
        core.process(a.video, a.ffmpeg, a.stream, a.swap, a.match_video, a.video_scale,
                     True, print, None, lang, not a.no_save_audio)
    except core.SplitError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
