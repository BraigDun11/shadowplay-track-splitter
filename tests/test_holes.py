"""Holes: short ones are closed (no silence, sound stays continuous), long ones are padded."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import core

P, Lm = 94, 46


def build(missing_mic_chunks):
    """Alternating PC(48)/mic(46) runs where `missing_mic_chunks` mic chunks are lost in a row."""
    runs, pos, k = [], 0, 0
    while k < 40:
        runs.append((pos, pos + 48, 1)); pos += 48
        if k == 20 and missing_mic_chunks:
            # the PC chunks run together because the mic chunks between them are gone
            for _ in range(missing_mic_chunks):
                runs.append((pos, pos + 48, 1)); pos += 48
        else:
            runs.append((pos, pos + 46, 0)); pos += 46
        k += 1
    # merge neighbouring runs of the same label (as label_runs would)
    merged = []
    for b, e, t in runs:
        if merged and merged[-1][2] == t:
            merged[-1] = (merged[-1][0], e, t)
        else:
            merged.append((b, e, t))
    n = pos
    data = bytes(range(256)) * (n // 256 + 1)
    frames = [(i, 1) for i in range(n)]
    return core.build_tracks(data, frames, merged, n, P, Lm, b"\xff")


_, _, filled = build(1)
print("one lost chunk:", filled)
assert filled[0] == 0 and filled[1] == 0
_, mono, filled = build(5)
print("five lost chunks:", filled)
assert filled[0] > 100          # long hole: the microphone is padded
print("OK")
