@echo off
rem Builds ShadowPlayTrackSplitter.exe locally (needs Python 3 on PATH).
pip install numpy tkinterdnd2 pyinstaller
pyinstaller --onefile --noconsole --collect-all tkinterdnd2 --name ShadowPlayTrackSplitter gui.py
echo.
echo Done: dist\ShadowPlayTrackSplitter.exe
pause
