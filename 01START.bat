@echo off
TITLE GABIgateway System Starter

echo ========================================
echo   STEUERZENTRALE: GABIgateway
echo ========================================

:: 1. Whisper.cpp Server starten (Port 9090)
echo Starte Whisper.cpp Core...
start "Whisper Engine" cmd /k "M:\whisper\whisper.cpp\build\bin\Release\server.exe -m M:\whisper\whisper.cpp\models\ggml-large-v3.bin --port 9090 --host 127.0.0.1 -l de"

:: 2. Dein Python-Backend starten (Flask/Uvicorn auf Port 8000)
echo Starte GABIgateway Backend...
cd /d M:\projekte_2026\claude-code\made-with-claude\gateway
:: Nutze 'start /b' um es im Hintergrund dieses Fensters zu lassen oder ohne /b für ein extra Fenster
start "GABIgateway Server" cmd /k "uvicorn main:app --reload --host 0.0.0.0 --port 8000"

echo Warte auf Initialisierung (10 Sek)...
timeout /t 10

:: 3. Browser öffnen
echo Öffne Studio-Interface...
start http://127.0.0.1:8000/

echo.
echo GABIgateway ist nun einsatzbereit!
echo.
rem jn pause