@echo off
rem Builds ShadowPlayTrackSplitter.exe locally (needs Python 3 on PATH).
pip install numpy pyinstaller
pyinstaller --onefile --noconsole --name ShadowPlayTrackSplitter gui.py
echo.
echo Done: dist\ShadowPlayTrackSplitter.exe
pause
