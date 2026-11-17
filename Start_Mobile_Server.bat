@echo off
title ApexTrader Mobile Server
cd /d "%~dp0"
echo ========================================================
echo   ApexTrader Mobile Network Server
echo ========================================================
echo.
echo Make sure your phone is connected to the same Wi-Fi.
echo Open this link in Chrome or Safari on your phone:
echo.
echo   http://192.168.3.77:8080/index.html
echo.
echo Press Ctrl+C in this window to stop the server anytime.
echo ========================================================
echo.
python -m http.server 8080
pause
