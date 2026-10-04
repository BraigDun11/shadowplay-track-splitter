# -*- coding: utf-8 -*-
"""
Self-test on synthetic data: builds a fake 'repaired' video whose single audio stream
interleaves a stereo track (PC) and a dual-mono track (mic) in ~1 s chunks, including a
lost mic chunk and a short mic chunk, then checks that core.process() restores both
tracks bit-exactly (and fills the lost parts with silence).

Run:  python tests/test_synthetic.py        (needs ffmpeg)
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core  # noqa: E402


def ff(*args):
    exe = core.find_ffmpeg()
    assert exe, "ffmpeg not found"
    r = subprocess.run([exe, "-v", "error", "-y", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def packets(path):
    d = open(path, "rb").read()
    return [d[o:o + l] for o, l in core.parse_adts(d)]


def main():
    tmp = tempfile.mkdtemp(prefix="tracksplit_")
    A, Bf, mix, video = [os.path.join(tmp, x) for x in ("A.aac", "B_full.aac", "mix.aac", "video.mp4")]
    ff("-f", "lavfi", "-i", "sine=f=300:d=120,volume=0.3", "-f", "lavfi", "-i", "sine=f=777:d=120,volume=0.3",
       "-filter_complex", "[0][1]join=inputs=2:channel_layout=stereo[a]", "-map", "[a]",
       "-ar", "48000", "-c:a", "aac", "-b:a", "128k", "-f", "adts", A)
    ff("-f", "lavfi", "-i", "anoisesrc=d=200:c=pink:a=0.2", "-af", "pan=stereo|c0=c0|c1=c0", "-ac", "2",
       "-ar", "48000", "-c:a", "aac", "-aac_ms", "1", "-b:a", "128k", "-f", "adts", Bf)
    pa, pb = packets(A), packets(Bf)
    pb = pb[1000:]                       # skip encoder start-up
    out = bytearray()
    ia = ib = chunk = 0
    while ia < len(pa) - 100 and ib < len(pb) - 100:
        for p in pa[ia:ia + 47]:
            out += p
        ia += 47
        chunk += 1
        if chunk == 30:                  # a whole mic chunk lost
            ib += 47
        elif chunk == 60:                # a short mic chunk: 18 packets lost
            for p in pb[ib:ib + 29]:
                out += p
            ib += 29 + 18
        else:
            for p in pb[ib:ib + 47]:
                out += p
            ib += 47
    open(mix, "wb").write(out)
    ff("-f", "lavfi", "-i", "testsrc=d=300:r=30:s=320x240", "-i", mix, "-map", "0:v", "-map", "1:a",
       "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "copy", "-bsf:a", "aac_adtstoasc", video)

    res = core.process(video, log=print, lang="en")

    # convert result tracks back to ADTS packets and compare
    def to_adts(m4a):
        p = m4a.replace(".m4a", "_chk.aac")
        ff("-i", m4a, "-c", "copy", "-f", "adts", p)
        return packets(p)

    pc, mic = to_adts(res["pc"]), to_adts(res["mic"])
    sa, sb = set(pa), set(pb)
    assert pc == pa[:len(pc)], "PC track is not bit-exact"
    assert all(p in sb for p in pc) is False
    foreign = sum(1 for p in mic if p in sa)
    silence = sum(1 for p in mic if p not in sb)
    print("PC packets: %d (bit-exact), mic: %d, foreign in mic: %d, silence packets: %d"
          % (len(pc), len(mic), foreign, silence))
    assert foreign == 0
    assert 60 <= silence <= 70, silence   # 47 + 18 = 65 expected
    assert abs(len(pc) - len(mic)) <= 1

    # --- normal video with two separate tracks: extraction mode
    two = os.path.join(tmp, "two.mp4")
    ff("-f", "lavfi", "-i", "testsrc=d=60:r=30:s=320x240", "-i", A, "-i", Bf, "-t", "60",
       "-map", "0:v", "-map", "1:a", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "copy",
       "-metadata:s:a:0", "handler_name=PC", "-metadata:s:a:1", "handler_name=Mic", two)
    info = core.probe_audio(core.find_ffmpeg(), two)
    assert [s["title"] for s in info] == ["PC", "Mic"], info
    assert all(s["mb"] > 0.1 for s in info), info
    res2 = core.extract_tracks(two, keep=0, save_others=True, lang="en")
    assert res2["video"].endswith("_video_PC.mp4") and len(res2["audio"]) == 1, res2
    assert res2["audio"][0].endswith("_audio_Mic.m4a"), res2
    assert len(core.probe_audio(core.find_ffmpeg(), res2["video"])) == 1
    print("EXTRACT OK")
    print("OK")


if __name__ == "__main__":
    main()
