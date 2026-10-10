"""Stop button: the job stops, no half-written files remain."""
import os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import core

ff = core.find_ffmpeg() or "ffmpeg"
with tempfile.TemporaryDirectory() as d:
    v = os.path.join(d, "v.mp4")
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=d=20:s=160x120",
                    "-f", "lavfi", "-i", "sine=d=20", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", v], check=True)
    out = os.path.join(d, "out")
    os.makedirs(out)
    core.CANCEL.clear()
    n = [0]

    def log(line):
        n[0] += 1
        if n[0] == 2:
            core.CANCEL.set()          # the user pressed Stop after the second message

    try:
        core.process(v, log=log, out_dir=out, save_features=False)
        raise AssertionError("not cancelled")
    except core.Cancelled:
        pass
    core.CANCEL.clear()
    left = os.listdir(out)
    print("left:", left)
    assert left == [], left
    n[0] = 0
    try:
        core.extract_tracks(v, log=lambda s: (core.CANCEL.set()), out_dir=out)
        raise AssertionError("not cancelled")
    except core.Cancelled:
        pass
    core.CANCEL.clear()
    assert os.listdir(out) == [], os.listdir(out)
print("OK")
