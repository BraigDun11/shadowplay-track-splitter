# -*- coding: utf-8 -*-
"""Regression: chunks are not exactly equally long (PC chunks 48..53 packets, cycle 94 or 95).
The segmentation must follow the real borders instead of a fixed period."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core

rng = np.random.default_rng(7)
truth = []
for _ in range(700):
    pc = 48 + int(rng.choice([0, 0, 0, 0, 1, 2, 3, 5]))
    cyc = 94 + int(rng.choice([0, 0, 0, 0, 1]))
    truth += [1] * pc + [0] * (cyc - pc)
truth = np.array(truth, dtype=np.int8)
n = len(truth)
s = np.where(truth == 1, rng.uniform(20, 200, n), rng.choice([0.28, 0.45], n))
s[rng.random(n) < 0.01] = 1.7                       # noise blips in the mic chunks
m = np.where(truth == 1, rng.uniform(300, 900, n), rng.uniform(10, 500, n))
lab, _ = core.segment_labels(s, m, 94, 46)
wrong = int((lab != truth).sum())
print("wrong packets: %d (%.2f%%)" % (wrong, 100 * wrong / n))
assert wrong / n < 0.01, wrong
print("OK")
