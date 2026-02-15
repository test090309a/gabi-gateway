@echo off
cd M:\projekte_2026\claude-code\made-with-claude\gateway
git add MEMORY.md SOUL.md HEARTBEAT.md
git commit -m "Automatisches Backup %date% %time%"
git push
echo Backup erstellt!
pause