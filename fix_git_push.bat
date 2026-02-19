@echo off
echo 🔧 GABI Git Push Fix
echo ====================
echo.

cd /d M:\projekte_2026\claude-code\made-with-claude\gateway

echo 1. Aktuellen Branch anzeigen:
git branch
echo.

echo 2. Falls noetig: Branch umbenennen...
git branch -m main master 2>nul
git branch -m master main 2>nul
echo.

echo 3. Remote URL prüfen:
git remote -v
echo.

echo 4. Falls kein Remote: Bitte URL eingeben
git remote get-url origin >nul 2>&1
if %errorlevel% neq 0 (
    set /p remote_url="GitHub Repository URL: "
    git remote add origin %remote_url%
)
echo.

echo 5. Ersten Push durchfuehren:
git push -u origin main
git push -u origin master
echo.

echo 6. Konfiguration für auto_git_backup.py:
echo.
echo In auto_git_backup.py Zeile 175 anpassen:
echo Ändere "main" zu "master" oder umgekehrt
echo.

pause