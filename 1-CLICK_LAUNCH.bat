@echo off
cd /d "%~dp0"
if exist "C:\Users\simtadigital\AppData\Local\Programs\Python\Python312\pythonw.exe" (
    start "" "C:\Users\simtadigital\AppData\Local\Programs\Python\Python312\pythonw.exe" app.pyw
) else (
    start "" pythonw app.pyw
)
