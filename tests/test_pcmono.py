"""PC sound is mono too (old games): schedule must still be found from the level of s alone."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import core

rng = np.random.default_rng(3)
n = 400 * 94 // 2 * 2
P, Lm = 94, 46
truth = np.zeros(n, int)
s = np.zeros(n)
m = np.zeros(n)
for k in range(0, n, P):
    truth[k:k + P - Lm] = 1
for i in range(n):
    s[i] = rng.normal(0.29, 0.03) if truth[i] else rng.normal(0.44, 0.015)
    m[i] = 200.0
est = core.find_schedule(s, m)
assert est == (P, Lm, True), est
lab, _ = core.segment_labels(s, m, P, Lm, mono_pc=True)
acc = float((lab == truth).mean())
print("accuracy", acc)
assert acc > 0.97
print("OK")
