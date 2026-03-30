# gateway/core/commands.py
"""Befehlshandler für alle /commands (shell, gui, memory, etc.)."""

import os
import re
import sys
import json
import asyncio
import subprocess
import platform
import shutil
import tempfile
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config import config
from gateway.core.memory import chat_memory
from gateway.utils.model_helpers import _extract_ollama_text

logger = logging.getLogger(__name__)

# Globale Konstante für API-Key (wird bei Bedarf gesetzt)
# API_KEY_REQUIRED = config.get("api_key", "sysop")
def get_api_key_required():
    return config.get("api_key", "sysop")

def get_default_model():
    return config.get("ollama.default_model", "llama2:latest")


def _find_program(program_name: str) -> Optional[str]:
    """
    Findet ein Programm auf dem System (Windows, Linux, macOS, Android).
    
    Args:
        program_name: Name des Programms
        
    Returns:
        Pfad zum Programm oder None
    """
    system = platform.system().lower()
    program_name_lower = program_name.lower()
    
    # 1. Zuerst mit shutil.which (PATH-Suche)
    found = shutil.which(program_name)
    if found:
        return found
    
    # 2. Bekannte Alternativen/Alternativnamen
    alternatives = {
        "chrome": ["chrome", "google-chrome", "google-chrome-stable", "chromium"],
        "firefox": ["firefox", "firefox.exe"],
        "edge": ["edge", "microsoft-edge", "msedge"],
        "opera": ["opera", "opera.exe"],
        "browser": ["chrome", "firefox", "edge", "opera", "brave", "vivaldi"],
        "notepad": ["notepad", "notepad.exe", "gedit", "nano", "vim", "vi"],
        "editor": ["code", "notepad++", "sublime_text", "gedit", "vim", "nano"],
        "code": ["code", "codium", "vscode", "visual-studio-code"],
        "vscode": ["code", "codium", "vscode"],
        "cmd": ["cmd", "cmd.exe"],
        "terminal": ["gnome-terminal", "konsole", "xterm", "termux", "cmd.exe"],
        "powershell": ["powershell", "pwsh", "powershell.exe"],
        "explorer": ["explorer", "explorer.exe", "nautilus", "dolphin", "thunar"],
        "calculator": ["calc", "gnome-calculator", "kcalc"],
    }
    
    if program_name_lower in alternatives:
        for alt in alternatives[program_name_lower]:
            found = shutil.which(alt)
            if found:
                logger.info(f"🔧 Programm '{program_name}' gefunden als '{alt}' → {found}")
                return found
    
    # 3. Windows: Suche in Program Files
    if system == "windows":
        program_files = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local"),
        ]
        
        exe_names = [f"{program_name}.exe", program_name]
        if program_name_lower in alternatives:
            exe_names.extend([f"{alt}.exe" for alt in alternatives[program_name_lower]])
        
        for pf in program_files:
            if not pf:
                continue
            pf_path = Path(pf)
            if not pf_path.exists():
                continue
            
            for exe_name in set(exe_names):
                for exe_path in pf_path.rglob(exe_name):
                    if exe_path.is_file():
                        logger.info(f"🔧 Programm '{program_name}' gefunden: {exe_path}")
                        return str(exe_path)
    
    # 4. Linux/macOS
    elif system in ["linux", "darwin"]:
        search_paths = ["/usr/bin", "/usr/local/bin", "/opt", "/snap/bin"]
        
        if system == "darwin":
            search_paths.append("/opt/homebrew/bin")
            search_paths.append("/usr/local/opt")
        
        for search_path in search_paths:
            search_dir = Path(search_path)
            if not search_dir.exists():
                continue
            
            for exe_path in search_dir.rglob(program_name):
                if exe_path.is_file() and os.access(exe_path, os.X_OK):
                    logger.info(f"🔧 Programm '{program_name}' gefunden: {exe_path}")
                    return str(exe_path)
            
            if program_name_lower in alternatives:
                for alt in alternatives[program_name_lower]:
                    for exe_path in search_dir.rglob(alt):
                        if exe_path.is_file() and os.access(exe_path, os.X_OK):
                            logger.info(f"🔧 Programm '{program_name}' gefunden als '{alt}': {exe_path}")
                            return str(exe_path)
    
    logger.warning(f"⚠️ Programm '{program_name}' nicht gefunden auf {system}")
    return None


def _log_gui_action(action: str, target: str, result: dict) -> None:
    """
    Dokumentiert GUI-Aktionen in MEMORY.md.
    
    Args:
        action: Die ausgeführte Aktion
        target: Das Ziel der Aktion
        result: Ergebnis der Aktion
    """
    try:
        memory_path = Path("MEMORY.md")
        if not memory_path.exists():
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if memory_path.stat().st_size > 10_000_000:  # 10MB Limit
            logger.warning("MEMORY.md zu groß, keine neuen Einträge")
            return
        
        content = memory_path.read_text(encoding="utf-8")
        
        entry = f"""
## GUI-Aktion [{timestamp}]
- **Aktion**: {action}
- **Ziel**: {target}
- **Erfolg**: {'Ja' if result.get('success') else 'Nein'}
- **Details**: {result.get('message', result.get('error', 'N/A'))}
"""
        memory_path.write_text(content + entry, encoding="utf-8")
        logger.info(f"GUI-Aktion dokumentiert: {action} -> {target}")
        
    except Exception as e:
        logger.error(f"Fehler beim Dokumentieren der GUI-Aktion: {e}")


async def _analyze_with_vision(screenshot_base64: str, prompt: str) -> str:
    """
    Analysiert Screenshot mit Vision-Modell.
    
    Args:
        screenshot_base64: Base64-kodierter Screenshot
        prompt: Analyse-Prompt
        
    Returns:
        Analyse-Ergebnis
    """
    try:
        from gateway.ollama_client import ollama_client
        from gateway.core.router import _pick_preferred_available, _pick_best_model
        from gateway.utils.model_helpers import _as_model_pref_list
        
        if isinstance(screenshot_base64, str):
            if "," in screenshot_base64 and screenshot_base64.startswith("data:"):
                screenshot_base64 = screenshot_base64.split(",", 1)[1]
        
        models_info = ollama_client.list_models()
        available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
        
        preferred_vision = _as_model_pref_list(config.get("ollama.preferred_vision_models")) or ["qwen3-vl:8b"]
        vision_model = _pick_preferred_available(available, preferred_vision)
        
        if not vision_model:
            vision_hints = ["vl", "vision", "llava", "moondream", "minicpm-v", "qwen2.5vl"]
            vision_model = _pick_best_model(available, hints=vision_hints)
        
        if not vision_model:
            return "❌ Kein Vision-Modell verfügbar."
        
        logger.info(f"🔍 Verwende Vision-Modell: {vision_model}")
        
        response = await asyncio.to_thread(
            ollama_client.chat,
            model=vision_model,
            messages=[{"role": "user", "content": prompt, "images": [screenshot_base64]}]
        )
        
        result = _extract_ollama_text(response)
        return result if result else "Keine Analyse erhalten"
        
    except Exception as e:
        logger.error(f"Vision-Analyse Fehler: {e}")
        return f"Analyse fehlgeschlagen: {str(e)}"


async def handle_command(message: str, token: str) -> Dict[str, Any]:
    """
    Behandelt Befehle wie /shell, /memory, /gui, etc.
    
    Args:
        message: Die Befehl-Nachricht (beginnt mit /)
        token: API-Key für Authentifizierung
        
    Returns:
        Dict mit Antwort und Status
    """
    cmd_parts = message[1:].split()
    if not cmd_parts:
        return {"status": "error", "reply": "❌ Kein Befehl angegeben."}
    
    command = cmd_parts[0].lower()
    args = cmd_parts[1:] if len(cmd_parts) > 1 else []
    subcmd = args[0].lower() if args else ""
    
    logger.info(f"Verarbeite Befehl: {command} mit Args: {args}")
    
    # ===== GOTO BEFEHL =====
    if command == "goto":
        if not args:
            return {
                "status": "error",
                "reply": "❌ Bitte URL angeben: `/goto <url>`\nBeispiel: `/goto google.com`"
            }
        
        url = ' '.join(args).strip().strip('"\'')
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        browser = "chrome"
        if len(args) > 1 and args[0].lower() in ["chrome", "firefox", "edge", "opera"]:
            browser = args[0].lower()
            url = ' '.join(args[1:]).strip()
        
        logger.info(f"🌐 GUI Goto: {url} mit {browser}")
        
        try:
            open_result = await handle_command(f"/gui open {browser}", token)
            
            if isinstance(open_result, dict) and open_result.get("status") == "error":
                return {
                    "status": "error",
                    "reply": f"❌ Browser '{browser}' konnte nicht gestartet werden: {open_result.get('reply', 'Unbekannter Fehler')}"
                }
            
            await asyncio.sleep(1.0)
            await handle_command("/gui hotkey ctrl l", token)
            await asyncio.sleep(0.3)
            await handle_command(f'/gui type "{url}"', token)
            await asyncio.sleep(0.2)
            await handle_command("/gui press enter", token)
            
            return {
                "status": "success",
                "reply": f"✅ Navigiere zu {url} mit {browser}",
                "url": url,
                "browser": browser,
                "tool_used": "gui-goto"
            }
        except Exception as e:
            logger.error(f"GUI Goto Fehler: {e}")
            return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}
    
    # ===== SHELL BEFEHLE =====
    if command in ["shell", "cmd", "bash", "powershell"]:
        if not args:
            return {
                "status": "success",
                "reply": "❌ Bitte einen Befehl angeben, z.B. `/shell dir | findstr py`"
            }
        
        try:
            full_command = ' '.join(args)
            logger.info(f"🖥️ GABI SHELL: {full_command}")
            
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
            
            if result.returncode == 0:
                output = result.stdout
                
                # Prüfe auf Datei-Erstellung NUR wenn ein echter Dateiname nach > kommt
                # und nicht nur "nul"
                if '>' in full_command:
                    file_match = re.search(r'>\s*([^\s&|]+)', full_command)
                    if file_match:
                        filename = file_match.group(1).strip()
                        # Ignoriere "nul" und andere Systemgeräte
                        if filename not in ['nul', 'NUL', 'null', '/dev/null'] and os.path.exists(filename):
                            try:
                                with open(filename, 'r', encoding='utf-8') as f:
                                    file_content = f.read()
                                return {
                                    "status": "success",
                                    "reply": f"✅ Datei '{filename}' erstellt.\n\n**Inhalt:**\n```\n{file_content}\n```",
                                    "command": full_command
                                }
                            except Exception as e:
                                return {
                                    "status": "success",
                                    "reply": f"✅ Datei '{filename}' wurde erstellt.",
                                    "command": full_command
                                }
                
                if output:
                    replacements = {
                        'â€”': '—', 'â€“': '–', 'â‚¬': '€',
                        'Ã¤': 'ä', 'Ã¶': 'ö', 'Ã¼': 'ü',
                        'ÃŸ': 'ß', 'Ã„': 'Ä', 'Ã–': 'Ö',
                        'Ãœ': 'Ü', 'â€™': "'", 'â€œ': '"',
                        'â€': '"', 'Â': '',
                    }
                    for wrong, correct in replacements.items():
                        output = output.replace(wrong, correct)
                    
                    return {
                        "status": "success",
                        "reply": f"```\n{output}\n```",
                        "command": full_command
                    }
                else:
                    return {
                        "status": "success",
                        "reply": "✅ Befehl erfolgreich ausgeführt (keine Konsolenausgabe).",
                        "command": full_command
                    }
            else:
                return {
                    "status": "success",
                    "reply": f"❌ Fehler (Code {result.returncode}):\n```\n{result.stderr}\n```",
                    "command": full_command
                }
        except subprocess.TimeoutExpired:
            return {"status": "success", "reply": f"❌ Timeout nach 30 Sekunden: `{full_command}`"}
        except Exception as e:
            logger.error(f"Shell-Fehler: {e}")
            return {"status": "success", "reply": f"❌ Fehler: {str(e)}"}
    
    # ===== GUI CONTROLLER BEFEHLE =====
    if command == "gui":
        if not args:
            return {
                "status": "success",
                "reply": "🖥️ **GUI-Controller Befehle:**\n\n" +
                        "`/gui open <programm>` - Programm öffnen\n" +
                        "`/gui goto <url>` - URL im Browser öffnen\n" +
                        "`/gui click <x> <y>` - An Position klicken\n" +
                        "`/gui type <text>` - Text eingeben\n" +
                        "`/gui press <taste>` - Taste drücken\n" +
                        "`/gui screenshot` - Screenshot machen\n" +
                        "`/gui windows` - Liste aller Fenster"
            }
        
        try:
            from gateway.integrations.gui_controller import get_gui_controller
            gui = get_gui_controller()
            
            if subcmd == "open":
                if len(args) < 2:
                    return {"status": "error", "reply": "❌ Bitte Programmname angeben: `/gui open chrome`"}
                program = args[1]
                program_path = _find_program(program)
                if program_path:
                    result = gui.open_program(program_path)
                else:
                    result = gui.win_search_and_open(program)
                
                if result.get("success"):
                    return {"status": "success", "reply": f"✅ {result.get('message', 'Programm gestartet')}"}
                else:
                    return {"status": "error", "reply": f"❌ Fehler: {result.get('error', 'Unbekannter Fehler')}"}
            
            elif subcmd == "goto":
                if len(args) < 2:
                    return {"status": "error", "reply": "❌ Bitte URL angeben: `/gui goto <url>`"}
                
                url = args[1].strip().strip('"\'')
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                
                await handle_command("/gui open chrome", token)
                await asyncio.sleep(1.0)
                await handle_command("/gui hotkey ctrl l", token)
                await asyncio.sleep(0.3)
                await handle_command(f'/gui type "{url}"', token)
                await asyncio.sleep(0.2)
                await handle_command("/gui press enter", token)
                
                return {"status": "success", "reply": f"✅ Navigiere zu {url}"}
            
            elif subcmd == "click":
                if len(args) < 3:
                    return {"status": "error", "reply": "❌ Bitte X und Y angeben: `/gui click 500 300`"}
                try:
                    x, y = int(args[1]), int(args[2])
                    result = gui.safe_click(x, y)
                    if result.get("success"):
                        return {"status": "success", "reply": f"✅ Geklickt bei ({x}, {y})"}
                    else:
                        return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
                except ValueError:
                    return {"status": "error", "reply": "❌ Ungültige Koordinaten"}
            
            elif subcmd == "type":
                if len(args) < 2:
                    return {"status": "error", "reply": "❌ Bitte Text angeben: `/gui type Hallo Welt`"}
                text = ' '.join(args[1:])
                result = gui.type_text(text)
                if result.get("success"):
                    return {"status": "success", "reply": f"✅ Text eingegeben: '{text}'"}
                else:
                    return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
            
            elif subcmd == "press":
                if len(args) < 2:
                    return {"status": "error", "reply": "❌ Bitte Taste angeben: `/gui press enter`"}
                key = args[1]
                result = gui.press_key(key)
                if result.get("success"):
                    return {"status": "success", "reply": f"✅ Taste gedrückt: {key}"}
                else:
                    return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
            
            elif subcmd == "hotkey":
                if len(args) < 2:
                    return {"status": "error", "reply": "❌ Bitte Tasten angeben: `/gui hotkey ctrl l`"}
                keys = args[1:]
                result = gui.hotkey(*keys)
                if result.get("success"):
                    return {"status": "success", "reply": f"✅ Hotkey ausgeführt: {'+'.join(keys)}"}
                else:
                    return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
            
            elif subcmd == "screenshot":
                target_dir = "screenshots/gui"
                os.makedirs(target_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"gui_{timestamp}.png"
                full_path = os.path.join(os.getcwd(), target_dir, filename)
                result = gui.screen_capture(full_path)
                
                if result.get("success"):
                    web_path = f"{target_dir}/{filename}"
                    _log_gui_action("screenshot", web_path, result)
                    return {
                        "status": "success",
                        "reply": f"✅ Screenshot gespeichert: `{web_path}`",
                        "path": web_path
                    }
                else:
                    return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
            
            elif subcmd == "windows":
                result = gui.get_window_titles()
                if result.get("success"):
                    windows = result.get("windows", [])
                    if windows:
                        reply = f"🖥️ **{len(windows)} Fenster gefunden:**\n\n"
                        for w in windows[:20]:
                            reply += f"• {w.get('title')}\n"
                        return {"status": "success", "reply": reply}
                    else:
                        return {"status": "success", "reply": "🖥️ Keine Fenster gefunden."}
                else:
                    return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
            
            else:
                return {"status": "error", "reply": f"❌ Unbekannter GUI-Befehl: `{subcmd}`"}
                
        except Exception as e:
            logger.error(f"GUI-Befehl Fehler: {e}")
            return {"status": "error", "reply": f"❌ GUI-Fehler: {str(e)}"}
    
    # ===== CHAT-MANAGEMENT =====
    if command in ["new", "reset"]:
        archive = command == "new"
        result = chat_memory.reset_chat(archive_current=archive)
        return {
            "status": "success",
            "reply": f"✅ Chat wurde zurückgesetzt{ ' und archiviert' if archive else ''}."
        }
    
    if command in ["archives", "history", "verlauf"]:
        archives = chat_memory.list_chat_archives()
        if not archives:
            return {"status": "success", "reply": "📂 **Keine Chat-Archive vorhanden**"}
        
        reply = "📚 **Verfügbare Chat-Archive:**\n\n"
        for i, arch in enumerate(archives[:10], 1):
            date = datetime.fromisoformat(arch["date"]).strftime("%d.%m.%Y %H:%M")
            reply += f"**{i}.** `{arch['id']}`\n"
            reply += f"   📅 {date} | 💬 {arch['messages']} Nachrichten\n\n"
        reply += "\nLade ein Archiv mit: `/load <id>`"
        return {"status": "success", "reply": reply}
    
    if command == "load":
        if not args:
            return {"status": "error", "reply": "❌ Bitte eine Archiv-ID angeben"}
        archive_id = args[0]
        archive = chat_memory.load_chat_archive(archive_id)
        if not archive:
            if not archive_id.startswith('chat_'):
                archive = chat_memory.load_chat_archive(f"chat_{archive_id}")
            if not archive:
                return {"status": "error", "reply": f"❌ Archiv '{archive_id}' nicht gefunden."}
        
        chat_memory.reset_chat(archive_current=True)
        chat_memory.conversation_history = archive.get("messages", [])
        chat_memory.user_interests = archive.get("user_interests", {})
        chat_memory.user_preferences = archive.get("preferences", chat_memory.user_preferences)
        
        return {"status": "success", "reply": f"✅ Archiv '{archive_id}' geladen."}
    
    # ===== MEMORY & NOTES =====
    if command in ["merken", "remember", "note"]:
        note_text = " ".join(args).strip()
        if not note_text:
            return {"status": "success", "reply": "🧠 Nutzung: `/merken <inhalt>`"}
        
        entry, created = chat_memory.remember_note(note_text, source="command")
        if not entry:
            return {"status": "error", "reply": "❌ Konnte den Inhalt nicht merken."}
        
        action = "Gemerkt" if created else "Schon gemerkt"
        ts = datetime.fromisoformat(entry["timestamp"]).strftime("%d.%m.%Y %H:%M:%S")
        return {
            "status": "success",
            "reply": f"✅ {action}: {entry['text']}\n🕒 {ts}",
            "tool_used": "Memory · /merken"
        }
    
    if command in ["gemerkt", "merkliste", "notes"]:
        limit = int(args[0]) if args and args[0].isdigit() else 20
        notes = chat_memory.get_remembered_notes(limit=limit)
        if not notes:
            return {"status": "success", "reply": "📭 Noch nichts gemerkt. Nutze `/merken <inhalt>`."}
        
        lines = ["🧠 **Gemerkte Einträge:**", ""]
        for idx, note in enumerate(notes, 1):
            note_time = note.get("timestamp", "")[:16].replace("T", " ")
            lines.append(f"**{idx}.** {note.get('text', '')}")
            lines.append(f"   🕒 {note_time}")
        return {"status": "success", "reply": "\n".join(lines)}
    
    if command == "memory":
        memory = chat_memory.memory_content[-1500:] if len(chat_memory.memory_content) > 1500 else chat_memory.memory_content
        return {"status": "success", "reply": f"📚 **Letzte Erinnerungen:**\n```\n{memory}\n```"}
    
    # ===== MODEL =====
    if command == "model":
        try:
            from gateway.ollama_client import ollama_client
            
            if not args:
                current = ollama_client.default_model
                return {"status": "success", "reply": f"🤖 Aktuelles Modell: `{current}`"}
            
            sub = args[0].lower()
            if sub in ["liste", "list", "ls"]:
                models_info = ollama_client.list_models()
                models = [m.get("name") for m in models_info.get("models", [])]
                current = ollama_client.default_model
                lines = [f"{'✅' if m == current else '•'} `{m}`" for m in models]
                return {"status": "success", "reply": "📚 **Verfügbare Modelle:**\n\n" + "\n".join(lines)}
            
            target_model = " ".join(args).strip()
            models_info = ollama_client.list_models()
            available = [m.get("name") for m in models_info.get("models", [])]
            if target_model not in available:
                return {"status": "error", "reply": f"❌ Modell `{target_model}` nicht gefunden."}
            
            config.set("ollama.default_model", target_model)
            ollama_client.default_model = target_model
            
            return {"status": "success", "reply": f"✅ Modell gewechselt zu `{target_model}`"}
        except Exception as e:
            return {"status": "error", "reply": f"❌ Model-Fehler: {e}"}
    
    # ===== STATUS =====
    if command == "status":
        return {"status": "success", "reply": chat_memory.heartbeat_content}
    
    # ===== EXPLORE =====
    if command == "explore":
        if args and args[0] == "now":
            asyncio.create_task(chat_memory._explore_system())
            return {"status": "success", "reply": "🔍 GABI beginnt jetzt mit der System-Exploration..."}
        else:
            inactive = int((datetime.now() - chat_memory.last_activity).total_seconds() / 60)
            return {
                "status": "success",
                "reply": f"⏳ Letzte Aktivität: vor {inactive} Minuten\n\nAuto-Exploration startet nach 10 Minuten Inaktivität.\n`/explore now` für sofortige Exploration."
            }
    
    # ===== SLEEP =====
    if command in ["sleep", "ruhe", "maintenance"]:
        summary = chat_memory.run_sleep_phase(reason="manual-command")
        return {
            "status": "success",
            "reply": f"🌙 Schlafphase abgeschlossen.\n- Notizen: {summary.get('notes_before')} -> {summary.get('notes_after')}\n- Memory kompaktiert: {'ja' if summary.get('memory_compacted') else 'nein'}"
        }
    
    # ===== VISION =====
    if command == "vision":
        try:
            from gateway.integrations.gabi_vision import get_gabi_vision
            vision = get_gabi_vision()
            if not vision:
                return {"status": "error", "reply": "❌ Vision-Modul nicht verfügbar"}
            
            if not args:
                webcam_result = vision.capture_webcam()
                if not webcam_result.get("success"):
                    return {"status": "error", "reply": f"❌ Webcam-Fehler: {webcam_result.get('error')}"}
                image_path = webcam_result.get("path")
                prompt = "Beschreibe was du auf diesem Bild siehst."
            else:
                image_path = " ".join(args)
                if not os.path.exists(image_path):
                    return {"status": "error", "reply": f"❌ Datei nicht gefunden: {image_path}"}
                prompt = "Beschreibe was du auf diesem Bild siehst."
            
            if len(args) > 1 and args[0].lower() in ["-p", "--prompt"]:
                prompt = " ".join(args[1:])
            
            with open(image_path, "rb") as f:
                img_base64 = __import__('base64').b64encode(f.read()).decode("utf-8")
            
            from gateway.ollama_client import ollama_client
            from gateway.core.router import _pick_preferred_available, _pick_best_model
            from gateway.utils.model_helpers import _as_model_pref_list
            
            models_info = ollama_client.list_models()
            available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
            preferred_vision = _as_model_pref_list(config.get("ollama.preferred_vision_models")) or ["qwen3-vl:8b"]
            vision_model = _pick_preferred_available(available, preferred_vision)
            
            if not vision_model:
                vision_hints = ["vl", "vision", "llava", "moondream", "minicpm-v", "qwen2.5vl"]
                vision_model = _pick_best_model(available, hints=vision_hints)
            
            if not vision_model:
                return {"status": "error", "reply": "❌ Kein Vision-Modell verfügbar."}
            
            response = await asyncio.to_thread(
                ollama_client.chat,
                model=vision_model,
                messages=[{"role": "user", "content": prompt, "images": [img_base64]}]
            )
            analysis = _extract_ollama_text(response) or "Keine Analyse erhalten"
            
            return {
                "status": "success",
                "reply": f"🔍 **Bildanalyse:**\n{analysis}",
                "image_path": image_path,
                "model_used": vision_model
            }
        except Exception as e:
            logger.error(f"Vision-Fehler: {e}")
            return {"status": "error", "reply": f"❌ Vision-Fehler: {e}"}
    
    # ===== HELP =====
    if command == "help":
        help_text = """
**🔧 VERFÜGBARE BEFEHLE:**

**📁 CHAT-MANAGEMENT:**
`/new` - Neuen Chat starten (aktuellen archivieren)
`/reset` - Chat zurücksetzen
`/archives` - Alle Chat-Archive anzeigen
`/load <id>` - Bestimmtes Archiv laden

**🧠 MEMORY:**
`/merken <inhalt>` - Etwas dauerhaft speichern
`/gemerkt` - Gemerkte Einträge abrufen
`/memory` - Letzte Erinnerungen anzeigen

**💻 SHELL:**
`/shell <befehl>` - Shell-Befehl ausführen

**🖥️ GUI:**
`/gui open <programm>` - Programm öffnen
`/gui goto <url>` - URL im Browser öffnen
`/gui click <x> <y>` - Mausklick
`/gui type <text>` - Texteingabe
`/gui screenshot` - Screenshot machen
`/gui windows` - Fensterliste

**🤖 MODEL:**
`/model` - Aktuelles Modell anzeigen
`/model liste` - Modelle anzeigen
`/model <name>` - Modell wechseln

**🔍 AUTO-EXPLORATION:**
`/explore` - Status anzeigen
`/explore now` - Sofortige Exploration
`/sleep` - Schlafphase ausführen

**📷 VISION:**
`/vision` - Webcam-Foto analysieren
`/vision <pfad>` - Bild analysieren

**📊 SYSTEM:**
`/status` - System-Status anzeigen
`/help` - Diese Hilfe
"""
        return {"status": "success", "reply": help_text}
    
    # ===== GMAIL =====
    if command == "gmail":
        if not args:
            return {
                "status": "success",
                "reply": "📧 **Gmail Befehle:**\n\n" +
                        "`/gmail list` - Alle E-Mails anzeigen\n" +
                        "`/gmail get <id>` - Bestimmte E-Mail anzeigen\n" +
                        "`/gmail reply <id> <text>` - Auf eine E-Mail antworten\n" +
                        "`/gmail help` - Diese Hilfe"
            }
        subcmd = args[0].lower()
        
        try:
            from gateway.integrations.gmail_client import get_gmail_client
            client = get_gmail_client()
            
            if subcmd == "list":
                messages = client.list_messages(max_results=10)
                if not messages:
                    return {"status": "success", "reply": "📭 Keine E-Mails gefunden."}
                
                reply = "📬 **Ihre letzten 10 E-Mails:**\n\n"
                for i, msg in enumerate(messages, 1):
                    reply += f"**{i}.** {msg.get('subject', 'kein Betreff')}\n"
                    reply += f"   📅 {msg.get('date', 'unbekannt')}\n"
                    reply += f"   👤 {msg.get('from', 'unbekannt')}\n"
                    reply += f"   🆔 `{msg.get('id', 'unbekannt')}`\n\n"
                return {"status": "success", "reply": reply}
                
            elif subcmd == "get" and len(args) > 1:
                msg_id = args[1]
                message = client.get_message(msg_id)
                body = client.get_message_body(message)
                headers = message.get('payload', {}).get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'kein Betreff')
                from_addr = next((h['value'] for h in headers if h['name'] == 'From'), 'unbekannt')
                
                reply = f"📧 **{subject}**\n\n"
                reply += f"**Von:** {from_addr}\n"
                reply += f"**Inhalt:**\n{body[:2000]}"
                return {"status": "success", "reply": reply}
                
            else:
                return {"status": "error", "reply": "❌ Unbekannter Gmail-Befehl. Verwende `/gmail help`."}
                
        except Exception as e:
            logger.error(f"Gmail Fehler: {e}")
            return {"status": "error", "reply": f"❌ Gmail-Fehler: {str(e)}"}
    

    # ===== TELEGRAM =====
    if command == "telegram":
        if not args:
            return {
                "status": "success",
                "reply": "📱 **Telegram Befehle:**\n\n" +
                        "`/telegram status` - Bot-Status anzeigen\n" +
                        "`/telegram users` - Aktive Benutzer anzeigen\n" +
                        "`/telegram send <nachricht>` - Nachricht an alle senden\n" +
                        "`/telegram send --to <chat_id> <nachricht>` - Nachricht an Ziel senden\n" +
                        "`/telegram help` - Diese Hilfe"
            }
        
        subcmd = args[0].lower()
        
        try:
            # ===== FIX: Verwende synchrone Version! =====
            from gateway.integrations.telegram_bot import get_telegram_bot_sync
            bot = get_telegram_bot_sync()
            
            if subcmd == "status":
                # Telegram-Status abrufen
                enabled = config.get("telegram.enabled", False)
                bot_token_set = bool(bot.bot_token and bot.bot_token != "YOUR_TELEGRAM_BOT_TOKEN")
                bot_running = bot.application is not None and bot._running
                active_sessions = len(bot._user_sessions) if hasattr(bot, '_user_sessions') else 0
                
                status_text = f"""
    📱 **Telegram Bot Status:**

    **Konfiguriert:** {'✅ Ja' if enabled else '❌ Nein'}
    **Bot Token:** {'✅ Gesetzt' if bot_token_set else '❌ Fehlt'}
    **Bot läuft:** {'✅ Ja' if bot_running else '❌ Nein'}
    **Aktive Benutzer:** {active_sessions}

    **Befehle:**
    • `/telegram users` - Alle aktiven Benutzer anzeigen
    • `/telegram send Hallo` - Nachricht an ALLE senden
    • `/telegram send --to 123456789 Hallo` - Direkt an eine Chat-ID
    """
                return {"status": "success", "reply": status_text}
            
            elif subcmd == "users":
                if not bot._user_sessions:
                    return {
                        "status": "success",
                        "reply": "📭 **Keine aktiven Telegram-Benutzer**\n\nBenutzer müssen dem Bot zuerst eine Nachricht schreiben."
                    }
                
                reply = "👥 **Aktive Telegram-Benutzer:**\n\n"
                for i, (user_id, session) in enumerate(bot._user_sessions.items(), 1):
                    msg_count = len(session) // 2
                    reply += f"**{i}.** Benutzer ID: `{user_id}`\n"
                    reply += f"   💬 {msg_count} Unterhaltungen\n"
                    if session:
                        last_msg = session[-1].get('content', '')[:50]
                        reply += f"   📝 Letzte: {last_msg}...\n"
                    reply += "\n"
                
                return {"status": "success", "reply": reply}
            
            elif subcmd in ["send", "broadcast"]:
                # Parse Nachricht
                message_start = 1
                explicit_targets = []
                
                if len(args) > 2 and args[1] in ["--to", "-t"]:
                    explicit_targets = [args[2]]
                    message_start = 3
                
                message = ' '.join(args[message_start:])
                if not message:
                    return {"status": "error", "reply": "❌ Bitte Nachricht angeben."}
                
                def escape_telegram_markdown(text: str) -> str:
                    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
                    for char in special_chars:
                        text = text.replace(char, f'\\{char}')
                    return text
                
                if explicit_targets:
                    sent = 0
                    for target in explicit_targets:
                        try:
                            try:
                                chat_id = int(target)
                            except ValueError:
                                chat_id = target
                            
                            escaped_message = escape_telegram_markdown(message)
                            # ===== WICHTIG: send_message ist async, muss awaited werden =====
                            await bot.send_message(chat_id, escaped_message, parse_mode='Markdown')
                            sent += 1
                        except Exception as e:
                            logger.error(f"Telegram send error to {target}: {e}")
                    
                    return {"status": "success", "reply": f"✅ Nachricht an {sent} Ziel(e) gesendet"}
                else:
                    if bot._user_sessions:
                        sent = 0
                        escaped_message = escape_telegram_markdown(message)
                        for user_id in bot._user_sessions.keys():
                            try:
                                await bot.send_message(user_id, escaped_message, parse_mode='Markdown')
                                sent += 1
                            except Exception as e:
                                logger.error(f"Telegram send error to {user_id}: {e}")
                        
                        return {"status": "success", "reply": f"✅ Nachricht an {sent} Benutzer gesendet"}
                    else:
                        from config import config
                        default_chat_id = config.get("telegram.chat_id", None)
                        
                        if default_chat_id:
                            try:
                                try:
                                    chat_id = int(default_chat_id)
                                except ValueError:
                                    chat_id = default_chat_id
                                
                                escaped_message = escape_telegram_markdown(message)
                                await bot.send_message(chat_id, escaped_message, parse_mode='Markdown')
                                return {"status": "success", "reply": f"✅ Nachricht an Default-Empfänger gesendet"}
                            except Exception as e:
                                logger.error(f"Telegram send error to default chat {default_chat_id}: {e}")
                                return {"status": "error", "reply": f"❌ Fehler beim Senden an Default-Empfänger: {e}"}
                        else:
                            return {"status": "error", "reply": "❌ Keine aktiven Benutzer und keine Default-Chat-ID in config.yaml"}
            
            elif subcmd == "help":
                return {
                    "status": "success",
                    "reply": """📱 **Telegram Bot Hilfe:**

    **Als Admin kannst du:**
    • `/telegram status` - Bot-Status und Konfiguration prüfen
    • `/telegram users` - Alle aktiven Benutzer anzeigen
    • `/telegram send Hallo` - Nachricht an ALLE aktiven Benutzer senden
    • `/telegram send --to 123456789 Hallo` - Direkt an eine Chat-ID senden

    **Wichtig:**
    • Der Bot muss laufen (Status prüfen)
    • Benutzer müssen dem Bot zuerst schreiben, um in der Liste zu erscheinen
    • Nachrichten werden im Markdown-Format unterstützt

    **Benutzer-Befehle (im Bot):**
    • /start - Bot starten
    • /help - Hilfe anzeigen
    • /clear - Verlauf löschen
    • /model - Aktuelles Modell
    • /model liste - Modelle anzeigen
    • /model <name> - Modell wechseln"""
                }
            
            else:
                return {"status": "error", "reply": f"❌ Unbekannter Telegram-Befehl: {subcmd}"}
                
        except Exception as e:
            logger.error(f"Telegram command error: {e}")
            return {"status": "error", "reply": f"❌ Telegram-Fehler: {str(e)}"}
    
    
    # ===== SPRACHBEFEHL =====
    # PyAudio optional importieren
    try:
        import pyaudio
        PYAUDIO_AVAILABLE = True
    except ImportError:
        PYAUDIO_AVAILABLE = False
        logger.warning("PyAudio not installed. Voice recording disabled.")

    # Später in handle_command():

    if command == "listen":
        """Startet die Sprachaufnahme und transkribiert"""
        
        if not PYAUDIO_AVAILABLE:
            return {
                "status": "error",
                "reply": "❌ PyAudio nicht installiert.\n\nInstalliere mit:\n`pip install pyaudio`\n\nAlternativ: Nutze den Mikrofon-Button im Dashboard."
            }
        
        try:
            # Prüfe ob Whisper verfügbar ist
            from gateway.api.whisper import get_whisper
            whisper = get_whisper()
            if not whisper or not whisper.is_available():
                return {
                    "status": "error",
                    "reply": "❌ Whisper-Server nicht verfügbar.\n\nStarte Whisper mit:\n`server.exe -m model.bin --port 9090`"
                }
            
            # Aufnahmeparameter
            CHUNK = 1024
            FORMAT = pyaudio.paInt16
            CHANNELS = 1
            RATE = 16000
            RECORD_SECONDS = 8
            
            # PyAudio initialisieren
            p = pyaudio.PyAudio()
            
            # Stream öffnen
            stream = p.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            input=True,
                            frames_per_buffer=CHUNK)
            
            logger.info("🎤 Recording started...")
            
            # Aufnahme in Hintergrund-Thread
            frames = []
            
            def record():
                for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
                    try:
                        data = stream.read(CHUNK, exception_on_overflow=False)
                        frames.append(data)
                    except Exception as e:
                        logger.debug(f"Recording error: {e}")
                        break
            
            # Starte Aufnahme in Thread
            import threading
            record_thread = threading.Thread(target=record)
            record_thread.start()
            
            # Speichere Aufnahme-Status in einer globalen Variable für /stop
            # (Hier müsstest du eine globale Variable wie _active_recording = {...} verwenden)
            
            return {
                "status": "info",
                "reply": f"🎤 **Sprachaufnahme gestartet!**\n\nSpreche jetzt in dein Mikrofon.\nDie Aufnahme endet automatisch nach {RECORD_SECONDS} Sekunden.\n\nZum vorzeitigen Stoppen: `/stop`"
            }
            
        except Exception as e:
            logger.error(f"Listen error: {e}")
            return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}

    if command == "stop":
        """Stoppt die Sprachaufnahme und transkribiert"""
        # Hier müsste die globale Aufnahme-Variable geprüft werden
        return {
            "status": "info",
            "reply": "⏹️ Sprachaufnahme wird beendet und transkribiert..."
        }

    # ===== STOP BEFEHL =====
    if command == "stop":
        """Stoppt die Sprachaufnahme"""
        # Hier müsstest du eine globale Variable für die Aufnahme verwalten
        return {
            "status": "success",
            "reply": "⏹️ Sprachaufnahme gestoppt."
        }
    
    
    
    
    
    # ===== UNBEKANNTER BEFEHL =====
    return {
        "status": "error",
        "reply": f"❌ Unbekannter Befehl: `{command}`\n\nVerwende `/help` für alle verfügbaren Befehle."
    }