@echo off
rem Quit a running CirClock instance without hunting for the tray icon.
rem Works even when the window is hidden and the tray icon is buried.
"%~dp0envs\.venv\Scripts\python.exe" "%~dp0CirClock.pyw" --quit
exit /b 0
