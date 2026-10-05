@echo off
rem Builds ShadowPlayTrackSplitter.exe locally (needs Python 3 on PATH).
pip install numpy tkinterdnd2 pyinstaller
pyinstaller --onefile --noconsole --icon assets\icon.ico --add-data "assets;assets" --collect-all tkinterdnd2 --name ShadowPlayTrackSplitter gui.py
echo.
echo Done: dist\ShadowPlayTrackSplitter.exe
pause
