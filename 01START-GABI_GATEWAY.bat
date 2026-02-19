@echo off
TITLE GABIgateway System Starter

echo ========================================
echo   STEUERZENTRALE: GABIgateway
echo ========================================

:: 1. Whisper.cpp Server starten (Port 9090)
echo Starte Whisper.cpp Core...
start "Whisper Engine" cmd /k ^
"M:\whisper\whisper.cpp\build\bin\Release\server.exe -m M:\whisper\whisper.cpp\models\ggml-large-v3.bin --port 9090 --host 127.0.0.1 -l de"

:: 1a. ComfyUI Server starten (z.B. http://127.0.0.1:8188)
echo Starte ComfyUI...
start "ComfyUI" cmd /k "cd /d M:\ComfyUI_windows_portable && run_nvidia_gpu.bat"

:: 1b. Ollama Server starten
echo Starte Ollama...
:: Beispiel: ollama serve (Pfad ggf. anpassen)
start "Ollama Server" cmd /k "ollama serve"

:: 2. Python-Backend starten (z.B. Uvicorn auf Port 8000)
echo Starte GABI Gateway Backend...
cd /d M:\projekte_2026\claude-code\made-with-claude\gateway
start "GABI Gateway Server" cmd /k ^
"uvicorn main:app --reload --host 0.0.0.0 --port 8000"

echo Warte auf Initialisierung, Browser Start in 20 Sek...
timeout /t 20

:: 3. Browser öffnen
echo Öffne Dashboard...
start http://127.0.0.1:8000/

echo.
echo GABI Gateway ist nun einsatzbereit!
echo.
rem pause
