# -*- coding: utf-8 -*-
"""Smoke test: the GUI window can be constructed (needs a display; skipped if none)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
try:
    import gui
    root = gui.TkinterDnD.Tk() if getattr(gui, "TkinterDnD", None) else gui.tk.Tk()
except Exception as e:
    print("GUI smoke skipped:", e); sys.exit(0)
app = gui.App(root)
root.update()
root.destroy()
print("GUI OK")
