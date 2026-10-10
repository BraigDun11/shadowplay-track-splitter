"""Holes in the video timeline must be found (frames missing after a repair)."""
import os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import core

ff = core.find_ffmpeg() or "ffmpeg"
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "gap.mp4")
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=d=60:r=30:s=160x120", "-vf",
                    "select='not(between(t,20,26))*not(between(t,40,41))'", "-fps_mode", "passthrough",
                    "-c:v", "libx264", "-preset", "ultrafast", p], check=True)
    res = core.video_gaps(ff, p)
    print(res)
    assert res is not None
    n, fps, gaps = res
    assert len(gaps) == 2 and abs(gaps[0][1] - 6.0) < 0.1 and abs(gaps[1][1] - 1.0) < 0.1
print("OK")
