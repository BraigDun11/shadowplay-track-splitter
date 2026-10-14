"""Tracks are plain concatenations of their own chunks: nothing is inserted, nothing is shifted,
and a track that delivered two chunks in a row does not make the other one 'lose' anything."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import core


def build(pc_double_at=20):
    runs, pos = [], 0
    for k in range(40):
        ln = 96 if k == pc_double_at else 48       # two PC chunks in a row (mic delivered nothing between)
        runs.append((pos, pos + ln, 1)); pos += ln
        runs.append((pos, pos + 46, 0)); pos += 46
    n = pos
    data = bytes(i % 251 for i in range(n))
    frames = [(i, 1) for i in range(n)]
    st, mo = core.build_tracks(data, frames, runs, n)
    return runs, data, st, mo


runs, data, st, mo = build()
exp_pc = b"".join(data[b:e - 1] for b, e, t in runs if t == 1)          # PC runs lose their last (smeared) packet
exp_mic = b"".join(data[max(b - 1, 0):e] for b, e, t in runs if t == 0)
assert bytes(st) == exp_pc and bytes(mo) == exp_mic
print("lengths", len(st), len(mo))
print("OK")
