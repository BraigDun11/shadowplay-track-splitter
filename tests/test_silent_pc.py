"""Silent PC chunks (digital silence, s ~ 0.34) must not hide the schedule from estimate_period."""
import sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import core

rng = np.random.default_rng(1)
n = 94 * 200
s = np.zeros(n)
m = np.zeros(n)
for k in range(200):
    b = k * 94
    mic = slice(b, b + 46)
    pc = slice(b + 46, b + 94)
    s[mic] = rng.normal(0.45, 0.01, 46)
    m[mic] = rng.uniform(5, 300, 46)
    if k % 5 < 3 and not (60 <= k < 80):
        s[pc] = 30 + rng.uniform(0, 50, 48)
        m[pc] = rng.uniform(200, 900, 48)
    else:                                   # silent PC chunk
        s[pc] = rng.normal(0.34, 0.005, 48)
        m[pc] = 0
print("plain:", core.estimate_period(s), "with m:", core.estimate_period(s, m))
r = core.estimate_period(s, m)
assert r == (94, 46), r
lab, _ = core.segment_labels(s, m, *r)
runs = core.label_runs(lab)
bad = [x for x in runs if abs((x[1] - x[0]) - {1: 48, 0: 46}[x[2]]) > 3]
print("irregular runs:", len(bad))
assert len(bad) <= 2
print("OK")
