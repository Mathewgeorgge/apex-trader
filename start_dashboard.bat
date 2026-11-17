@echo off
title Zerodha Algo Trader Dashboard
cd /d "%~dp0"
echo ========================================================
echo Starting Zerodha Algo Trader Web Dashboard...
echo ========================================================
echo Opening http://localhost:8080 in your browser...
start http://localhost:8080
if exist "C:\Users\simtadigital\AppData\Local\Programs\Python\Python312\python.exe" (
    "C:\Users\simtadigital\AppData\Local\Programs\Python\Python312\python.exe" dashboard.py
) else (
    python dashboard.py
)
pause
