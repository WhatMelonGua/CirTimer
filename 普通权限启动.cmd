@echo off
rem 以普通权限启动超能苹果钟：交给资源管理器启动，
rem 即使当前是管理员终端，新进程也是普通权限。
start "" explorer.exe "%~dp0CirClock.pyw"
exit /b 0
