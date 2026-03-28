# gateway/api/shell.py
"""Shell execution API endpoints."""

import asyncio
import subprocess
import logging
import re
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel

from gateway.auth import verify_token
from gateway.config import config
from gateway.core.memory import chat_memory
from gateway.ollama_client import ollama_client
from gateway.utils.model_helpers import _extract_ollama_text

logger = logging.getLogger(__name__)

router = APIRouter()


class ShellRequest(BaseModel):
    """Shell command request model."""
    command: str
    args: Optional[List[str]] = []


class ShellResponse(BaseModel):
    """Shell command response model."""
    status: str
    command_executed: str
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


@router.post("/shell")
async def execute_command(
    request: ShellRequest,
    token: str = Header(None, alias="token"),
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Führt Shell-Befehle aus - transparent und mit voller Pipe-Unterstützung.
    
    Unterstützt:
    - Pipes (|)
    - Redirections (>)
    - Command chaining (&&, ||)
    - Windows und Linux/Unix
    """
    try:
        # Befehl zusammenbauen
        if request.args:
            full_cmd = f"{request.command} {' '.join(request.args)}"
        else:
            full_cmd = request.command
        
        logger.info(f"🖥️ GABI EXEC: {full_cmd}")
        
        # Sicherheitscheck
        if not _is_command_allowed(full_cmd):
            logger.warning(f"🚫 Blocked command: {full_cmd}")
            return {
                "status": "error",
                "command_executed": full_cmd,
                "stdout": "",
                "stderr": "❌ Befehl nicht erlaubt aus Sicherheitsgründen.",
                "returncode": -1
            }
        
        # Plattform-spezifische Anpassungen
        if sys.platform == "win32":
            # Für Windows: UTF-8 Codepage setzen
            full_cmd = f'chcp 65001 >nul 2>&1 && {full_cmd}'
        
        # Befehl ausführen
        result = await asyncio.to_thread(
            subprocess.run,
            full_cmd,
            capture_output=True,
            text=True,
            shell=True,
            timeout=30,
            encoding='utf-8',
            errors='replace',
        )
        
        # Memory aktualisieren
        if 'chat_memory' in globals():
            chat_memory.update_activity()
        
        output = result.stdout
        stderr = result.stderr
        
        # Prüfen auf Datei-Erstellung bei Redirection
        if '>' in full_cmd and result.returncode == 0:
            file_match = re.search(r'>\s*([^\s&|]+)', full_cmd)
            if file_match:
                filename = file_match.group(1).strip()
                if os.path.exists(filename):
                    try:
                        with open(filename, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                        
                        # Bei Dateierstellung: Inhalt anzeigen
                        if file_content:
                            # Begrenze auf 4000 Zeichen
                            if len(file_content) > 4000:
                                file_content = file_content[:4000] + "\n\n... (Datei gekürzt)"
                            
                            return {
                                "status": "success",
                                "command_executed": full_cmd,
                                "stdout": f"✅ Datei '{filename}' erstellt.\n\n**Inhalt:**\n```\n{file_content}\n```",
                                "stderr": result.stderr,
                                "returncode": result.returncode
                            }
                        else:
                            return {
                                "status": "success",
                                "command_executed": full_cmd,
                                "stdout": f"✅ Datei '{filename}' wurde erstellt (leer).",
                                "stderr": result.stderr,
                                "returncode": result.returncode
                            }
                    except Exception as e:
                        return {
                            "status": "success",
                            "command_executed": full_cmd,
                            "stdout": f"✅ Datei '{filename}' wurde erstellt.",
                            "stderr": result.stderr,
                            "returncode": result.returncode
                        }
        
        # JSON verschönern, falls Ausgabe JSON ist
        if output and output.strip().startswith(('{', '[')):
            try:
                import json
                json_data = json.loads(output)
                output = json.dumps(json_data, indent=2, ensure_ascii=False)
            except:
                pass
        
        # Windows Encoding-Fehler korrigieren
        if sys.platform == "win32":
            output = _fix_windows_encoding(output)
            stderr = _fix_windows_encoding(stderr)
        
        # Erfolgreiche Ausführung
        if result.returncode == 0:
            if output:
                return {
                    "status": "success",
                    "command_executed": full_cmd,
                    "stdout": f"```\n{output}\n```" if len(output) < 4000 else f"```\n{output[:4000]}\n\n... (Ausgabe gekürzt)\n```",
                    "stderr": stderr,
                    "returncode": result.returncode
                }
            else:
                return {
                    "status": "success",
                    "command_executed": full_cmd,
                    "stdout": "✅ Befehl erfolgreich ausgeführt (keine Konsolenausgabe).",
                    "stderr": stderr,
                    "returncode": result.returncode
                }
        else:
            return {
                "status": "error",
                "command_executed": full_cmd,
                "stdout": output,
                "stderr": f"❌ Fehler (Code {result.returncode}):\n```\n{stderr}\n```" if stderr else f"❌ Fehler (Code {result.returncode})",
                "returncode": result.returncode
            }
        
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "command_executed": full_cmd if 'full_cmd' in locals() else request.command,
            "stdout": "",
            "stderr": "❌ Timeout: Befehl wurde nach 30 Sekunden abgebrochen.",
            "returncode": -1
        }
    except Exception as e:
        logger.error(f"Shell-Fehler: {e}")
        return {
            "status": "error",
            "command_executed": full_cmd if 'full_cmd' in locals() else request.command,
            "stdout": "",
            "stderr": f"❌ Kritischer Fehler: {str(e)}",
            "returncode": -1
        }


@router.post("/shell/analyze")
async def execute_and_analyze(
    request: ShellRequest,
    token: str = Header(None, alias="token"),
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Führt einen Befehl aus und lässt das Ergebnis von Ollama analysieren.
    """
    try:
        # Befehl ausführen
        full_cmd = f"{request.command} {' '.join(request.args)}" if request.args else request.command
        
        logger.info(f"🔍 GABI EXEC + ANALYZE: {full_cmd}")
        
        # Sicherheitscheck
        if not _is_command_allowed(full_cmd):
            return {
                "status": "error",
                "message": "Befehl nicht erlaubt",
                "command_output": "",
                "analysis": "❌ Dieser Befehl ist aus Sicherheitsgründen nicht erlaubt."
            }
        
        # Befehl ausführen
        result = await asyncio.to_thread(
            subprocess.run,
            full_cmd,
            capture_output=True,
            text=True,
            shell=True,
            timeout=30,
            encoding='utf-8',
            errors='replace',
        )
        
        output = result.stdout if result.stdout else result.stderr
        
        if not output:
            output = "(Keine Ausgabe)"
        
        # Windows Encoding-Fehler korrigieren
        if sys.platform == "win32":
            output = _fix_windows_encoding(output)
        
        # Prompt für Analyse erstellen
        analysis_prompt = f"""
Analysiere die folgende Shell-Ausgabe und gib eine kurze, verständliche Zusammenfassung.

**Befehl:** {full_cmd}

**Ausgabe:**
{output[:3000]}
**Fragen:**
1. Was bedeutet diese Ausgabe?
2. Gibt es Fehler oder Warnungen?
3. Was sollte der Nutzer beachten?

**Analyse (auf Deutsch, prägnant):**
"""
        # Ollama zur Analyse fragen
        try:
            response = await asyncio.to_thread(
                ollama_client.chat,
                model=ollama_client.default_model,
                messages=[{"role": "user", "content": analysis_prompt}],
                options={"temperature": 0.3, "num_predict": 500}
            )
            analysis = _extract_ollama_text(response) or "Keine Analyse möglich."
        except Exception as e:
            logger.error(f"Analyse-Fehler: {e}")
            analysis = f"❌ Analyse fehlgeschlagen: {str(e)}"
        
        # Memory aktualisieren
        if 'chat_memory' in globals():
            chat_memory.update_activity()
        
        return {
            "status": "success",
            "command_output": output[:2000] if len(output) > 2000 else output,
            "analysis": analysis,
            "returncode": result.returncode
        }
        
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "message": "Timeout",
            "command_output": "",
            "analysis": "❌ Der Befehl wurde nach 30 Sekunden abgebrochen."
        }
    except Exception as e:
        logger.error(f"Analyse-Fehler: {e}")
        return {
            "status": "error",
            "message": str(e),
            "command_output": "",
            "analysis": f"❌ Fehler: {str(e)}"
        }


@router.get("/shell/allowed")
async def list_allowed_commands(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Listet alle erlaubten Shell-Befehle auf.
    """
    allowed = config.get("shell.allowed_commands", [])
    return {
        "status": "success",
        "allowed_commands": allowed,
        "count": len(allowed)
    }


@router.post("/shell/pipe")
async def execute_pipe(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Führt komplexe Pipes mit temporären Dateien aus.
    
    Beispiel: `/pipe dir > temp.txt && type temp.txt | findstr py`
    """
    full_command = payload.get("command", "")
    
    if not full_command:
        raise HTTPException(status_code=400, detail="Kein Befehl angegeben")
    
    if ">" not in full_command:
        return {
            "status": "error",
            "reply": "❌ Beispiel: `/pipe dir > temp.txt && type temp.txt | findstr py`"
        }
    
    import tempfile
    
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.tmp', delete=False) as tmp:
        tmp_name = tmp.name
    
    try:
        # Ersetze temp.txt mit temporärer Datei
        cmd_with_temp = full_command.replace('temp.txt', tmp_name)
        
        result = await asyncio.to_thread(
            subprocess.run,
            cmd_with_temp,
            capture_output=True,
            text=True,
            shell=True,
            timeout=30,
            encoding='utf-8',
            errors='replace'
        )
        
        # Aufräumen
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        
        output = result.stdout
        if sys.platform == "win32":
            output = _fix_windows_encoding(output)
        
        return {
            "status": "success",
            "reply": f"```\n{output}\n```" if output else "✅ Befehl ausgeführt (keine Ausgabe)"
        }
        
    except subprocess.TimeoutExpired:
        return {"status": "error", "reply": "❌ Timeout nach 30 Sekunden"}
    except Exception as e:
        return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}
    finally:
        # Aufräumen falls noch vorhanden
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except:
                pass


@router.get("/shell/status")
async def shell_status(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Gibt den Shell-Status zurück.
    """
    system_os = sys.platform
    
    return {
        "status": "success",
        "platform": system_os,
        "shell_available": True,
        "allowed_commands_count": len(config.get("shell.allowed_commands", [])),
        "working_directory": os.getcwd(),
        "timestamp": datetime.now().isoformat()
    }


def _is_command_allowed(command: str) -> bool:
    """
    Prüft ob ein Befehl ausgeführt werden darf.
    
    Args:
        command: Der auszuführende Befehl
        
    Returns:
        True wenn erlaubt, False wenn blockiert
    """
    # Gefährliche Befehle immer blockieren
    dangerous_patterns = [
        r'rm\s+-rf\s+/',           # rm -rf /
        r'del\s+/[fsq]\s+[c-z]:',  # del /f /s /q c:
        r'format\s+[c-z]:',        # format c:
        r'mkfs',                   # mkfs
        r':\(\)\{\s*:\|\:&\s*\};:', # fork bomb
        r'wget.*\|.*sh',           # wget ... | sh
        r'curl.*\|.*sh',           # curl ... | sh
    ]
    
    cmd_lower = command.lower()
    
    for pattern in dangerous_patterns:
        if re.search(pattern, cmd_lower):
            logger.warning(f"🚫 Dangerous command blocked: {command}")
            return False
    
    # Erlaubte Befehle aus Config
    allowed = config.get("shell.allowed_commands", [])
    
    # Extrahiere Basis-Befehl (vor Pipe, Redirection, etc.)
    base_cmd = command.split()[0].lower() if command else ""
    
    # Entferne Pfadangaben (z.B. C:\Windows\System32\cmd.exe -> cmd)
    base_cmd = os.path.basename(base_cmd).lower()
    
    # Prüfe ob erlaubt
    if base_cmd in allowed:
        return True
    
    # Spezielle Erlaubnisse für bestimmte Kombinationen
    special_allowed = [
        'echo', 'cd', 'dir', 'ls', 'pwd', 'type', 'cat',
        'find', 'findstr', 'grep', 'sort', 'uniq', 'wc'
    ]
    
    if base_cmd in special_allowed:
        return True
    
    logger.warning(f"🚫 Command not allowed: {command} (base: {base_cmd})")
    return False


def _fix_windows_encoding(text: str) -> str:
    """
    Korrigiert Windows-Encoding-Fehler.
    
    Args:
        text: Text mit möglichen Encoding-Fehlern
        
    Returns:
        Korrigierter Text
    """
    if not text:
        return text
    
    replacements = {
        'â€”': '—', 'â€“': '–', 'â‚¬': '€',
        'Ã¤': 'ä', 'Ã¶': 'ö', 'Ã¼': 'ü',
        'ÃŸ': 'ß', 'Ã„': 'Ä', 'Ã–': 'Ö',
        'Ãœ': 'Ü', 'â€™': "'", 'â€œ': '"',
        'â€': '"', 'Â': '', 'Â®': '®',
        'Â©': '©', 'Â±': '±', 'Â²': '²',
        'Â³': '³', 'Âµ': 'µ', 'Â¶': '¶',
    }
    
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    
    return text


# ===== HELPER FUNCTIONS FOR COMMAND MODULE =====

def get_allowed_commands() -> List[str]:
    """
    Gibt Liste der erlaubten Befehle zurück.
    
    Returns:
        Liste der erlaubten Befehle
    """
    return config.get("shell.allowed_commands", [])


def is_safe_command(command: str) -> bool:
    """
    Prüft ob ein Befehl sicher ist.
    
    Args:
        command: Der Befehl
        
    Returns:
        True wenn sicher, False wenn gefährlich
    """
    return _is_command_allowed(command)


def execute_shell_command(command: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Führt einen Shell-Befehl aus (synchron).
    
    Args:
        command: Der Befehl
        timeout: Timeout in Sekunden
        
    Returns:
        Dict mit stdout, stderr, returncode
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=True,
            timeout=timeout,
            encoding='utf-8',
            errors='replace'
        )
        
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Timeout nach {timeout} Sekunden",
            "returncode": -1
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1
        }


# Export für andere Module
__all__ = [
    "router",
    "execute_command",
    "get_allowed_commands",
    "is_safe_command",
    "execute_shell_command",
]