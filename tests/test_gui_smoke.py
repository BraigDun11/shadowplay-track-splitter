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
# the "ready" screen and the settings page must draw without errors (checkboxes, toggles, language)
app.video, app.state, app.ffmpeg = "x.mp4", "ready", "ffmpeg"
app.streams = [{"index": 0, "codec": "aac", "title": "", "mb": 5}]
app.render()
for name in ("fitsnd", "stretch", "audio_only"):
    app.toggle_fit(name) if name != "audio_only" else app.toggle(name)
app.settings_open = True
app.render()
app.toggle_lang()
app.render()
root.update()
root.destroy()
print("GUI OK")
