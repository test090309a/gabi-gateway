# shell_utils.py
"""Gemeinsame Shell-Funktionen für HTTP-API und Telegram Bot"""
import subprocess
import sys
import os
import re
import logging

logger = logging.getLogger(__name__)

async def execute_shell_command(full_command: str) -> dict:
    """Führt Shell-Befehle aus und gibt formatiertes Ergebnis zurück"""
    try:
        logger.info(f"🖥️ SHELL EXEC: {full_command}")
        
        # Für Windows: UTF-8 Codepage setzen
        if sys.platform == "win32":
            full_command = f'chcp 65001 >nul && {full_command}'
        
        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            shell=True,
            timeout=30,
            encoding='utf-8',
            errors='replace'
        )
        
        output = result.stdout
        error = result.stderr
        
        # Windows-Encoding-Fehler bereinigen
        replacements = {
            'â€”': '—', 'â€“': '–', 'â‚¬': '€',
            'Ã¤': 'ä', 'Ã¶': 'ö', 'Ã¼': 'ü',
            'ÃŸ': 'ß', 'Ã„': 'Ä', 'Ã–': 'Ö',
            'Ãœ': 'Ü', 'â€™': "'", 'â€œ': '"',
            'â€': '"', 'Â': '',
        }
        for wrong, correct in replacements.items():
            if output:
                output = output.replace(wrong, correct)
            if error:
                error = error.replace(wrong, correct)
        
        # JSON-Erkennung und Formatierung
        if output and output.strip().startswith(('{', '[')):
            try:
                import json
                json_data = json.loads(output)
                output = json.dumps(json_data, indent=2, ensure_ascii=False)
            except:
                pass
        
        return {
            "success": result.returncode == 0,
            "stdout": output,
            "stderr": error,
            "returncode": result.returncode,
            "command": full_command
        }
        
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "❌ Timeout: Der Befehl wurde nach 30 Sekunden abgebrochen.",
            "returncode": -1,
            "command": full_command
        }
    except Exception as e:
        logger.error(f"Shell-Fehler: {e}")
        return {
            "success": False,
            "stdout": "",
            "stderr": f"❌ Fehler: {str(e)}",
            "returncode": -1,
            "command": full_command
        }

def format_shell_output(result: dict, for_telegram: bool = False) -> str:
    """Formatiert die Shell-Ausgabe für Chat oder Telegram"""
    if result["success"]:
        output = result["stdout"]
        
        # Prüfe auf Datei-Umlenkung (>)
        if '>' in result["command"] and not output:
            file_match = re.search(r'>\s*([^\s&|]+)', result["command"])
            if file_match:
                filename = file_match.group(1).strip()
                if filename.lower() != 'nul' and os.path.exists(filename):
                    try:
                        with open(filename, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                        return f"✅ Datei '{filename}' erstellt:\n```\n{file_content}\n```"
                    except:
                        return f"✅ Datei '{filename}' wurde erstellt"
        
        if output:
            # Für Telegram: kürzen wenn nötig
            if for_telegram and len(output) > 4000:
                output = output[:4000] + "\n\n... (Ausgabe gekürzt)"
            return f"```\n{output}\n```"
        else:
            return "✅ Befehl erfolgreich ausgeführt"
    else:
        error = result["stderr"] if result["stderr"] else f"Exit-Code: {result['returncode']}"
        return f"❌ Fehler:\n```\n{error}\n```"