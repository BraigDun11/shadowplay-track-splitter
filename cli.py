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
    a = ap.parse_args()
    lang = a.lang or core.detect_lang()
    try:
        core.process(a.video, a.ffmpeg, a.stream, a.swap, a.match_video, a.video_scale,
                     a.save_features, print, None, lang)
    except core.SplitError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
