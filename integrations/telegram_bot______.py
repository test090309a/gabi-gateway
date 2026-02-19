"""Telegram bot integration."""
import logging
import asyncio
import subprocess
import sys
import os
import re
from datetime import datetime

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

from gateway.config import config
from gateway.ollama_client import ollama_client

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot that forwards messages to Ollama."""

    def __init__(self):
        self.bot_token = config.get("telegram.bot_token")
        self.application = None
        self._user_sessions = {}
        self.current_model = config.get("ollama.default_model", ollama_client.default_model)

        # ===== WICHTIG: PFADE FÜR TOOLS =====
        import os
        from pathlib import Path
        self.base_dir = Path(__file__).parent.parent  # gateway-Verzeichnis
        self.tools_dir = self.base_dir / "tools"
        self.web_search_path = self.tools_dir / "web_search.py"

    def _escape_markdown(self, text: str) -> str:
        """Escape problematic markdown characters for Telegram."""
        if not text:
            return text
        
        # VERSUCHE: Normales Escaping
        try:
            special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
            escaped = text
            for char in special_chars:
                escaped = escaped.replace(char, '\\' + char)
            
            # Code-Blöcke wiederherstellen
            escaped = escaped.replace('\\`\\`\\`', '```')
            
            # Test: Wenn's klappt, nimm escaped version
            return escaped
            
        except Exception:
            # FALLBACK: Wenn irgendwas schiefgeht, sende OHNE Markdown
            logger.warning("Markdown-Fehler, sende als Klartext")
            return text.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Hallo! Ich bin ein Ollama-Gateway-Bot. "
            "Schreibe mir etwas und ich werde es an Ollama weiterleiten.\n\n"
            "**Shell-Befehle:**\n"
            "`/shell <befehl>` - Führe Shell-Befehle aus\n"
            "Beispiele:\n"
            "• `/shell dir` - Verzeichnis anzeigen\n"
            "• `/shell echo test > datei.txt` - Datei erstellen\n"
            "• `/shell type datei.txt` - Datei anzeigen\n"
            "• `/shell ipconfig | findstr IPv4` - Netzwerk-Info\n\n"
            "**Model-Befehle:**\n"
            "`/model` - Aktuelles Modell\n"
            "`/model liste` - Verfügbare Modelle\n"
            "`/model <name>` - Modell wechseln",
            parse_mode='Markdown'
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Zeigt alle verfügbaren Befehle im Telegram an"""
        help_text = """
**🔧 VERFÜGBARE BEFEHLE**

**Allgemein**
`/start` - Bot starten
`/help` - Hilfe anzeigen
`/clear` - Verlauf löschen

**Modelle**
`/model` - Aktuelles Modell anzeigen
`/model liste` - Verfügbare Modelle anzeigen
`/model <name>` - Modell wechseln

**Shell**
`/shell <befehl>` - Befehl ausführen

**Beispiele**
`/shell dir`
`/shell ipconfig | findstr IPv4`
`/shell echo hallo > test.txt && type test.txt`
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def model_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /model list/current/switch in Telegram."""
        try:
            args = context.args or []
            if not args:
                await update.message.reply_text(f"🤖 Aktuelles Modell: `{self.current_model}`", parse_mode='Markdown')
                return

            sub = args[0].lower()
            models_info = ollama_client.list_models()
            available = [m.get("name") for m in models_info.get("models", [])]

            if sub in ["liste", "list", "ls"]:
                if not available:
                    await update.message.reply_text("❌ Keine Modelle gefunden.")
                    return
                lines = [f"{'✅' if m == self.current_model else '•'} `{m}`" for m in available]
                await update.message.reply_text("📚 **Verfügbare Modelle:**\n\n" + "\n".join(lines), parse_mode='Markdown')
                return

            target = " ".join(args).strip()
            if target not in available:
                await update.message.reply_text("❌ Modell nicht gefunden. Nutze `/model liste`.", parse_mode='Markdown')
                return

            self.current_model = target
            ollama_client.default_model = target
            config.set("ollama.default_model", target)
            await update.message.reply_text(f"✅ Modell gewechselt zu `{target}`", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Model command error: {e}")
            await update.message.reply_text(f"❌ Fehler bei /model: {e}")

    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self._user_sessions.pop(user_id, None)
        await update.message.reply_text("Gesprächsverlauf gelöscht.")

    # ===== NEUE METHODE: SHELL-BEFEHLE AUSFÜHREN =====
    async def _execute_shell_command(self, full_command: str) -> str:
        """Führt Shell-Befehle aus (gleiche Logik wie in http_api.py)"""
        try:
            logger.info(f"🖥️ TELEGRAM SHELL: {full_command}")
            
            # ===== PFAD-KORREKTUR FÜR WEB_SEARCH.PY =====
            if "web_search.py" in full_command:
                import sys
                from pathlib import Path
                
                # Verwende den gleichen Python-Interpreter wie das Gateway
                python_exe = sys.executable
                logger.info(f"🐍 Verwende Python: {python_exe}")
                
                # Absoluter Pfad zur web_search.py
                base_dir = Path(__file__).parent.parent  # gateway-Verzeichnis
                web_search_path = base_dir / "tools" / "web_search.py"
                
                # Extrahiere den Suchbegriff
                import re
                match = re.search(r'"(.+)"', full_command)
                if match:
                    query = match.group(1)
                    # Baue den Befehl mit vollem Pfad neu
                    full_command = f'chcp 65001 >nul && "{python_exe}" "{web_search_path}" "{query}"'
                    logger.info(f"📁 Korrigierter Befehl: {full_command}")
            
            # Für Windows: UTF-8 Codepage setzen (falls nicht schon geschehen)
            elif sys.platform == "win32" and not full_command.startswith('chcp'):
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
            
            # WICHTIG: output und error DEFINIEREN
            output = result.stdout
            error = result.stderr
            
            # Logge für Debugging
            if error:
                logger.error(f"❌ STDERR: {error}")
            if output:
                logger.info(f"✅ STDOUT: {output[:500]}")
            
            # ===== SPEZIALBEHANDLUNG FÜR WEB_SEARCH.PY JSON =====
            if "web_search.py" in full_command and output and output.strip().startswith('{'):
                try:
                    import json
                    data = json.loads(output)
                    if data.get("ok") and data.get("results"):
                        # Formatiere die Ergebnisse schön
                        results = data["results"][:5]  # Maximal 5 Ergebnisse
                        formatted = f"🔍 **Suchergebnisse:**\n\n"
                        for i, r in enumerate(results, 1):
                            formatted += f"**{i}.** [{r['title']}]({r['url']})\n"
                            if r.get('snippet'):
                                formatted += f"   {r['snippet'][:200]}...\n"
                            formatted += "\n"
                        if data.get("count", 0) > 5:
                            formatted += f"*... und {data['count'] - 5} weitere Ergebnisse*\n"
                        return formatted
                except Exception as e:
                    logger.error(f"JSON Parse Fehler: {e}")
                    # Fallback zur normalen Ausgabe
            
            if result.returncode == 0:
                output = result.stdout
                
                # ===== VERBESSERTE PRÜFUNG AUF DATEI-UMLEITUNG =====
                if '>' in full_command and not full_command.strip().startswith('dir') and not output:
                    import re
                    file_match = re.search(r'>\s*([^\s&|]+)', full_command)
                    if file_match:
                        filename = file_match.group(1).strip()
                        if filename.lower() != 'nul' and os.path.exists(filename):
                            try:
                                with open(filename, 'r', encoding='utf-8') as f:
                                    file_content = f.read()
                                return f"✅ Datei '{filename}' erstellt:\n```\n{file_content}\n```"
                            except:
                                return f"✅ Datei '{filename}' wurde erstellt"
                
                # Normale Ausgabe
                if output:
                    # Windows-Encoding-Fehler bereinigen
                    replacements = {
                        'â€”': '—', 'â€“': '–', 'â‚¬': '€',
                        'Ã¤': 'ä', 'Ã¶': 'ö', 'Ã¼': 'ü',
                        'ÃŸ': 'ß', 'Ã„': 'Ä', 'Ã–': 'Ö',
                        'Ãœ': 'Ü', 'â€™': "'", 'â€œ': '"',
                        'â€': '"', 'Â': '',
                    }
                    for wrong, correct in replacements.items():
                        output = output.replace(wrong, correct)
                    
                    # Telegram-Limit beachten
                    if len(output) > 4000:
                        output = output[:4000] + "\n\n... (Ausgabe gekürzt)"
                    
                    return f"```\n{output}\n```"
                else:
                    return "✅ Befehl erfolgreich ausgeführt (keine Ausgabe)"
            else:
                error_msg = error if error else f"Exit-Code: {result.returncode}"
                return f"❌ Fehler:\n```\n{error_msg}\n```"
                
        except subprocess.TimeoutExpired:
            return "❌ Timeout: Der Befehl wurde nach 30 Sekunden abgebrochen."
        except Exception as e:
            logger.error(f"Shell-Fehler: {e}")
            return f"❌ Fehler: {str(e)}"

    # ===== NEUE METHODE: SHELL COMMAND HANDLER =====
    async def shell_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Behandelt den /shell Befehl"""
        if not context.args:
            await update.message.reply_text(
                "❌ **Shell-Befehl benötigt**\n\n"
                "**Beispiele:**\n"
                "`/shell dir` - Verzeichnis anzeigen\n"
                "`/shell echo Hallo > test.txt` - Datei erstellen\n"
                "`/shell type test.txt` - Datei anzeigen\n"
                "`/shell (echo Zeile1 & echo Zeile2) > datei.txt` - Mehrzeilige Datei\n"
                "`/shell ipconfig | findstr IPv4` - Netzwerk-Info\n"
                "`/shell powershell \"$a=0;$b=1;1..10 | foreach {$a;$c=$a+$b;$a=$b;$b=$c}\"` - Fibonacci",
                parse_mode='Markdown'
            )
            return
        
        full_command = ' '.join(context.args)
        
        # Zeige an, dass der Befehl ausgeführt wird
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # Führe Befehl aus
        result = await self._execute_shell_command(full_command)
        
        # In Verlauf speichern
        user_id = update.effective_user.id
        timestamp = datetime.now().isoformat()
        
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []
        
        self._user_sessions[user_id].append({
            "role": "user",
            "content": f"/shell {full_command}",
            "timestamp": timestamp
        })
        self._user_sessions[user_id].append({
            "role": "assistant",
            "content": result,
            "timestamp": datetime.now().isoformat()
        })
        
        await update.message.reply_text(result, parse_mode='Markdown')

    # ===== VERBESSERTE HANDLE_MESSAGE MIT AUTO-EXECUTION =====
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_message = update.message.text
        timestamp = datetime.now().isoformat()
        
        # ===== NEU: PRÜFE OB ES EIN SLASH-BEFEHL IST =====
        if user_message.startswith('/'):
            logger.info(f"⚡ Telegram Slash-Befehl erkannt: {user_message}")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            
            # Leite an die HTTP API weiter
            try:
                # Erstelle einen HTTP-Request an den lokalen /chat Endpoint
                import httpx
                
                # Token aus Config holen
                from gateway.config import config
                api_key = config.get("api_key")
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://localhost:8000/chat",  # Dein lokaler API-Endpoint
                        json={"message": user_message},
                        headers={"token": api_key},
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        reply = result.get("reply", result.get("response", "Keine Antwort"))
                    else:
                        reply = f"❌ Fehler {response.status_code}: {response.text}"
                        
            except Exception as e:
                logger.error(f"Fehler bei Slash-Befehl: {e}")
                reply = f"❌ Fehler bei Ausführung: {str(e)}"
            
            # Antwort speichern und senden
            if user_id not in self._user_sessions:
                self._user_sessions[user_id] = []
                
            self._user_sessions[user_id].append({
                "role": "user",
                "content": user_message,
                "timestamp": timestamp
            })
            self._user_sessions[user_id].append({
                "role": "assistant",
                "content": reply,
                "timestamp": datetime.now().isoformat()
            })
            
            safe_reply = self._escape_markdown(reply)
            await update.message.reply_text(safe_reply, parse_mode='Markdown')
            return

        # ===== STOP-BEFEHL SPEZIALBEHANDLUNG =====
        if user_message.lower() in ['/stop', '/cancel', '/abbrechen']:
            await self.stop_command(update, context)
            return


        
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []

        messages = self._user_sessions[user_id]
        
        messages.append({
            "role": "user", 
            "content": user_message,
            "timestamp": timestamp
        })

        try:
            # ===== SUCH-TRIGGER DEFINIEREN =====
            search_triggers = [
                "suche nach", "such nach", "finde heraus", "recherchiere",
                "google mal", "such mal", "was ist", "wer ist", "informationen über",
                "infos zu", "news zu", "artikel über", "erzähl mir von",
                "suche im internet", "such im internet", "internet suche"
            ]
            
            # ===== PRÜFE OB ES EINE SUCHE IST =====
            is_search = any(trigger in user_message.lower() for trigger in search_triggers)
            
            if is_search:
                # Suchbegriff extrahieren
                search_term = user_message
                for trigger in search_triggers:
                    if trigger in user_message.lower():
                        search_term = user_message.lower().split(trigger)[-1].strip()
                        break
                
                logger.info(f"🔍 Telegram-Suche erkannt: '{search_term}'")
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                
                # Führe WEB-SUCHE aus
                safe_term = search_term.replace('"', "'")
                cmd = f'python tools/web_search.py "{safe_term}"'
                cmd_result = await self._execute_shell_command(cmd)
                
                final_reply = f"🔍 **Suchergebnisse für '{search_term}':**\n\n{cmd_result}"
                
            elif user_message.startswith('/shell '):
                # Expliziter Shell-Befehl
                cmd = user_message[7:].strip()
                logger.info(f"⚡ Telegram Shell-Befehl: {cmd}")
                cmd_result = await self._execute_shell_command(cmd)
                final_reply = f"**Shell-Ausführung:**\n{cmd_result}"
                
            else:
                # ===== NORMALE CHAT-NACHRICHT - an Ollama senden =====
                system_prompt = ""
                try:
                    from gateway.http_api import chat_memory
                    system_prompt = chat_memory.get_system_prompt()
                except:
                    system_prompt = "Du bist GABI, ein hilfreicher Assistent."
                
                # Telegram-spezifischer Prompt
                telegram_prompt = system_prompt + """

    WICHTIG FÜR TELEGRAM:
    - Antworte KURZ und PRÄZISE (maximal 2000 Zeichen)
    - Keine langen Erklärungen
    - Bei Fragen zu aktuellen Ereignissen: Weise darauf hin, dass du eine Internet-Suche empfehlen kannst
    - Beispiel: "Für aktuelle Informationen empfehle ich: suche im internet nach [Thema]"
    """
                
                ollama_messages = [{"role": "system", "content": telegram_prompt}]
                
                for msg in messages[-10:]:
                    ollama_messages.append({"role": msg["role"], "content": msg["content"]})
                
                response = ollama_client.chat(model=self.current_model, messages=ollama_messages)
                assistant_message = response.get("message", {}).get("content", "")
                final_reply = assistant_message

            # Bot-Antwort speichern
            messages.append({
                "role": "assistant",
                "content": final_reply,
                "timestamp": datetime.now().isoformat()
            })

            # Telegram-Limit beachten
            if len(final_reply) > 4000:
                final_reply = final_reply[:3500] + "\n\n... (Antwort gekürzt für Telegram)"

            safe_reply = self._escape_markdown(final_reply)
            await update.message.reply_text(safe_reply, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Ollama error: {e}")
            error_msg = str(e)
            if "connection" in error_msg.lower() or "winerror" in error_msg.lower() or " refused" in error_msg.lower():
                await update.message.reply_text(
                    "⚠️ **Ollama nicht erreichbar**\n\n"
                    "Der Ollama-Server ist nicht verfügbar oder nicht gestartet.\n"
                    "Bitte starte Ollama und versuche es erneut.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(f"❌ Fehler: {error_msg}")
            messages.pop()

###################################################################################################
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Behandelt den /stop Befehl - stoppt laufende Ollama Generierungen"""
        await update.message.reply_text("⏹️ Stoppe laufende Anfragen...")
        
        try:
            import httpx
            from gateway.config import config
            
            api_key = config.get("api_key")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/api/chat/stop",
                    json={},  # Leeres Payload, stoppt alle
                    headers={"token": api_key},
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    stopped = result.get("stopped_models", [])
                    await update.message.reply_text(
                        f"✅ Gestoppt: {len(stopped)} Modelle",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(
                        f"❌ Fehler {response.status_code}",
                        parse_mode='Markdown'
                    )
        except Exception as e:
            logger.error(f"Stop-Fehler: {e}")
            await update.message.reply_text(f"❌ Fehler: {str(e)}")

telegram_bot = None


def get_telegram_bot() -> TelegramBot:
    global telegram_bot
    if telegram_bot is None:
        telegram_bot = TelegramBot()
        if telegram_bot.bot_token:
            telegram_bot.application = Application.builder().token(telegram_bot.bot_token).build()
            telegram_bot.application.add_handler(CommandHandler("start", telegram_bot.start_command))
            telegram_bot.application.add_handler(CommandHandler("help", telegram_bot.help_command))
            telegram_bot.application.add_handler(CommandHandler("clear", telegram_bot.clear_command))
            telegram_bot.application.add_handler(CommandHandler("shell", telegram_bot.shell_command))
            telegram_bot.application.add_handler(CommandHandler("model", telegram_bot.model_command))
            telegram_bot.application.add_handler(CommandHandler("stop", telegram_bot.stop_command))
            telegram_bot.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_bot.handle_message)
            )
    return telegram_bot
