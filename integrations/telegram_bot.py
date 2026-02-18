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

    def _escape_markdown(self, text: str) -> str:
        """Escape problematic Markdown characters for Telegram."""
        if not text:
            return text
        # Escape special Markdown characters
        # Telegram Markdown v1: * _ ` [ ] ( ) ~ > # + - = | { } . !
        special_chars = ['_', '*', '`', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        escaped = text
        # Only escape if not already escaped (basic check)
        for char in special_chars:
            if char in escaped:
                # Escape only if it looks like it could break markdown
                escaped = escaped.replace(char, '\\' + char)
        # Fix common issues with code blocks that span multiple lines with backticks
        # Replace triple backticks with escaped version if inside code-like content
        return escaped

    def _escape_markdown(self, text: str) -> str:
        """Escape problematic markdown characters for Telegram."""
        if not text:
            return text
        # Telegram Markdown V2 special characters: _ * [ ] ( ) ~ ` > # + - = | { } . !
        # We need to escape characters that are not meant to be markdown
        import re
        # Escape underscores in words but preserve markdown links
        text = re.sub(r'(?<!\[)(?<!\])(_)(?!\[|\])', r'\_', text)
        # Escape asterisks that aren't in code blocks
        text = re.sub(r'(?<![`*])\*([^*]+)\*(?![`*])', r'\\\*\1\\*', text)
        # Escape backticks that aren't in code blocks
        text = re.sub(r'(?<!`)`(?!`)', r'\\`', text)
        # Escape brackets that aren't for links
        text = re.sub(r'(?<!\]\()\[([^\]]+)\](?!\()', r'\\[\1\\]', text)
        # Remove or escape problematic code block markers
        # If response contains unbalanced code blocks, remove them
        code_block_count = text.count('```')
        if code_block_count % 2 != 0:
            text = text.replace('```', '')
        return text

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
            
            if result.returncode == 0:
                output = result.stdout
                
                # ===== VERBESSERTE PRÜFUNG AUF DATEI-UMLEITUNG =====
                # Nur prüfen wenn:
                # 1. Der Befehl enthält '>'
                # 2. Es ist NICHT der Befehl 'dir' (der auch '>' in der Ausgabe haben könnte)
                # 3. Der Befehl ist erfolgreich und hat keine Ausgabe
                if '>' in full_command and not full_command.strip().startswith('dir') and not output:
                    import re
                    # Finde Dateinamen nach '>' (aber nicht in Anführungszeichen)
                    file_match = re.search(r'>\s*([^\s&|]+)', full_command)
                    if file_match:
                        filename = file_match.group(1).strip()
                        # Ignoriere 'nul' als Dateinamen (das ist ein Windows-Device)
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
                    
                    # Begrenze Ausgabe auf 4000 Zeichen (Telegram-Limit)
                    if len(output) > 4000:
                        output = output[:4000] + "\n\n... (Ausgabe gekürzt)"
                    
                    return f"```\n{output}\n```"
                else:
                    return "✅ Befehl erfolgreich ausgeführt (keine Ausgabe)"
            else:
                error_msg = result.stderr if result.stderr else f"Exit-Code: {result.returncode}"
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
        
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []

        messages = self._user_sessions[user_id]
        
        # User-Nachricht mit Timestamp speichern
        messages.append({
            "role": "user", 
            "content": user_message,
            "timestamp": timestamp
        })

        try:
            # System-Prompt aus Memory (falls verfügbar)
            system_prompt = ""
            try:
                from gateway.http_api import chat_memory
                system_prompt = chat_memory.get_system_prompt()
            except:
                system_prompt = "Du bist GABI, ein hilfreicher Assistent."
            
            # Nachrichten für Ollama vorbereiten
            ollama_messages = [{"role": "system", "content": system_prompt}]
            
            # Letzten Verlauf hinzufügen (max 10 Nachrichten)
            for msg in messages[-10:]:
                ollama_messages.append({"role": msg["role"], "content": msg["content"]})
            
            response = ollama_client.chat(model=self.current_model, messages=ollama_messages)
            assistant_message = response.get("message", {}).get("content", "")
            
            # ===== PRÜFE OB DIE ANTWORT EINEN SHELL-BEFEHL ENTHÄLT =====
            match = re.search(r"/(shell|python)\s+(.+)", assistant_message)
            
            if match:
                cmd_type = match.group(1)
                cmd_body = match.group(2).strip()
                
                if cmd_type == "python":
                    full_cmd = f"python {cmd_body}"
                else:
                    full_cmd = cmd_body
                
                # Führe Befehl aus
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                cmd_result = await self._execute_shell_command(full_cmd)

                final_reply = f"{assistant_message}\n\n**Ausführung:**\n{cmd_result}"
            else:
                final_reply = assistant_message

            # Bot-Antwort mit Timestamp speichern
            messages.append({
                "role": "assistant",
                "content": final_reply,
                "timestamp": datetime.now().isoformat()
            })

            # Escape problematic markdown entities before sending
            safe_reply = self._escape_markdown(final_reply)
            await update.message.reply_text(safe_reply, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Ollama error: {e}")
            error_msg = str(e)
            # Spezifischere Fehlermeldung für Verbindungsprobleme
            if "connection" in error_msg.lower() or "winerror" in error_msg.lower() or " refused" in error_msg.lower():
                await update.message.reply_text(
                    "⚠️ **Ollama nicht erreichbar**\n\n"
                    "Der Ollama-Server ist nicht verfügbar oder nicht gestartet.\n"
                    "Bitte starte Ollama und versuche es erneut.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(f"❌ Fehler: {error_msg}")
            messages.pop()  # User-Nachricht wieder entfernen bei Fehler


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
            telegram_bot.application.add_handler(CommandHandler("shell", telegram_bot.shell_command))  # NEU
            telegram_bot.application.add_handler(CommandHandler("model", telegram_bot.model_command))
            telegram_bot.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_bot.handle_message)
            )
    return telegram_bot
