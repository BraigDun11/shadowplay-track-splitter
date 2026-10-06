# -*- coding: utf-8 -*-
"""Regression: while the game plays in mono, PC chunks look like mic chunks.
The schedule must keep its phase (no PC<->mic swap) until real stereo returns."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core

P, L = 94, 46
rng = np.random.default_rng(1)
n = P * 400
s = np.zeros(n); m = np.zeros(n); truth = np.zeros(n, dtype=np.int8)   # 1 = PC
for i in range(n):
    pc = (i % P) >= L
    truth[i] = pc
    mono_game = 100 * P <= i < 250 * P          # game goes mono, mic silent
    if pc:
        s[i] = 0.28 if mono_game else rng.uniform(20, 200)
        m[i] = rng.uniform(300, 900)
    else:
        s[i] = 0.34 if mono_game else 0.45
        m[i] = 1.4 if mono_game else rng.uniform(10, 500)
lab, _ = core.segment_labels(s, m, P, L)
fp = core.mic_fingerprint(s, lab)
if fp is not None:
    lab, _ = core.segment_labels(s, m, P, L, fp=fp)
acc = float((lab == truth).mean())
print("accuracy %.3f" % acc)
assert acc > 0.98, acc
print("OK")
