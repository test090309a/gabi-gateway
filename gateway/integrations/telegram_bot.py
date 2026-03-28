# integrations/telegram_bot.py
"""Telegram Bot integration."""

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from gateway.config import config

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram Bot for chat interactions."""
    
    def __init__(self):
        self.bot_token = config.get("telegram.bot_token", "")
        self.application = None
        self._user_sessions: Dict[int, List[Dict[str, Any]]] = {}
        self._running = False
        
        logger.info(f"🤖 Telegram Bot initialized (token: {self.bot_token[:10]}...)")
        
        if self.bot_token and self.bot_token != "YOUR_TELEGRAM_BOT_TOKEN":
            self._init_bot()
        else:
            logger.warning("⚠️ Telegram Bot Token not configured")
    
    def _init_bot(self):
        """Initialize the bot application."""
        try:
            self.application = Application.builder().token(self.bot_token).build()
            logger.info("✅ Application built")
            
            # Handler
            self.application.add_handler(CommandHandler("start", self._start_command))
            self.application.add_handler(CommandHandler("help", self._help_command))
            self.application.add_handler(CommandHandler("clear", self._clear_command))
            self.application.add_handler(CommandHandler("model", self._model_command))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
            self.application.add_error_handler(self._error_handler)
            
            logger.info("✅ Handlers added")
            
        except Exception as e:
            logger.error(f"❌ Bot init error: {e}")
            import traceback
            traceback.print_exc()
    
    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors."""
        logger.error(f"Telegram error: {context.error}")
    
    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user_id = update.effective_user.id
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []
        logger.info(f"📱 /start from user {user_id}")
        
        await update.message.reply_text(
            "🤖 **GABI Telegram Bot**\n\n"
            "Ich bin dein KI-Assistent! Stelle mir Fragen, ich antworte.\n\n"
            "**Befehle:**\n"
            "/help - Hilfe\n"
            "/clear - Verlauf löschen\n"
            "/model - Modell anzeigen\n"
            "/model liste - Modelle anzeigen",
            parse_mode='Markdown'
        )
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        await update.message.reply_text(
            "🤖 **GABI Hilfe**\n\n"
            "Einfach losschreiben! Ich antworte mit Ollama.\n\n"
            "/clear - Verlauf löschen\n"
            "/model - Aktuelles Modell\n"
            "/model liste - Alle Modelle",
            parse_mode='Markdown'
        )
    
    async def _clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /clear command."""
        user_id = update.effective_user.id
        self._user_sessions[user_id] = []
        await update.message.reply_text("✅ Verlauf gelöscht!")
    
    async def _model_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /model command."""
        from gateway.ollama_client import ollama_client
        args = context.args
        
        if not args:
            current = ollama_client.default_model
            await update.message.reply_text(f"🤖 Aktuelles Modell: `{current}`", parse_mode='Markdown')
            return
        
        if args[0].lower() in ["liste", "list", "ls"]:
            models_info = ollama_client.list_models()
            models = [m.get("name") for m in models_info.get("models", [])]
            current = ollama_client.default_model
            lines = [f"{'✅' if m == current else '•'} `{m}`" for m in models[:20]]
            await update.message.reply_text("📚 **Modelle:**\n\n" + "\n".join(lines), parse_mode='Markdown')
            return
        
        target = " ".join(args)
        models_info = ollama_client.list_models()
        available = [m.get("name") for m in models_info.get("models", [])]
        
        if target not in available:
            await update.message.reply_text(f"❌ Modell `{target}` nicht gefunden", parse_mode='Markdown')
            return
        
        config.set("ollama.default_model", target)
        ollama_client.default_model = target
        await update.message.reply_text(f"✅ Modell gewechselt zu `{target}`", parse_mode='Markdown')
    
    def _escape_markdown(self, text: str) -> str:
        """Escape special characters for Telegram Markdown."""
        special = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special:
            text = text.replace(char, f'\\{char}')
        return text
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages."""
        user_id = update.effective_user.id
        message = update.message.text
        
        logger.info(f"📨 Received from {user_id}: {message[:50]}...")
        
        # Session erstellen
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []
            logger.info(f"📱 Neue Session für {user_id}")
        
        # User message speichern
        self._user_sessions[user_id].append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        
        # Konversation aufbauen
        from gateway.ollama_client import ollama_client
        
        messages = [{"role": "system", "content": "Du bist GABI, ein hilfsbereiter KI-Assistent."}]
        messages.extend(self._user_sessions[user_id][-10:])
        
        try:
            # Typing indicator
            await update.message.chat.send_action(action="typing")
            
            # Ollama antwort
            response = await asyncio.to_thread(
                ollama_client.chat,
                model=ollama_client.default_model,
                messages=messages
            )
            
            reply = response.get("message", {}).get("content", "Keine Antwort.")
            logger.info(f"📤 Sending to {user_id}: {reply[:50]}...")
            
            # Bot antwort speichern
            self._user_sessions[user_id].append({
                "role": "assistant",
                "content": reply,
                "timestamp": datetime.now().isoformat()
            })
            
            # Session limit
            if len(self._user_sessions[user_id]) > 100:
                self._user_sessions[user_id] = self._user_sessions[user_id][-100:]
            
            # Senden
            safe_reply = self._escape_markdown(reply)
            await update.message.reply_text(safe_reply[:4096], parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Message error: {e}")
            await update.message.reply_text(f"❌ Fehler: {str(e)}")
    
    async def start(self):
        """Start the bot with polling."""
        if self.application and not self._running:
            try:
                logger.info("🚀 Starting bot...")
                await self.application.initialize()
                await self.application.start()
                await self.application.updater.start_polling()
                self._running = True
                
                # Bot info
                bot_info = await self.application.bot.get_me()
                logger.info(f"✅ Bot @{bot_info.username} (ID: {bot_info.id}) gestartet")
                
            except Exception as e:
                logger.error(f"❌ Failed to start bot: {e}")
                raise
    
    async def stop(self):
        """Stop the bot."""
        if self.application and self._running:
            try:
                logger.info("🛑 Stopping bot...")
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                self._running = False
                logger.info("✅ Bot stopped")
            except Exception as e:
                logger.error(f"Stop error: {e}")
    
    async def send_message(self, chat_id: int, text: str, parse_mode: str = 'Markdown'):
        """Send a message."""
        if self.application and self.application.bot and self._running:
            try:
                safe_text = self._escape_markdown(text)
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=safe_text[:4096],
                    parse_mode=parse_mode
                )
                return True
            except Exception as e:
                logger.error(f"Send error: {e}")
        return False
    
    def get_user_sessions(self) -> Dict[int, List[Dict[str, Any]]]:
        """Get all user sessions."""
        return self._user_sessions


# GLOBALE SINGLETON-INSTANZ
_telegram_bot = None
_bot_lock = asyncio.Lock()


async def get_telegram_bot() -> TelegramBot:
    """Get or create Telegram bot singleton (async-safe)."""
    global _telegram_bot
    async with _bot_lock:
        if _telegram_bot is None:
            _telegram_bot = TelegramBot()
            logger.info(f"✅ TelegramBot Singleton created (ID: {id(_telegram_bot)})")
        return _telegram_bot


def get_telegram_bot_sync() -> TelegramBot:
    """Synchronous version for API endpoints."""
    global _telegram_bot
    if _telegram_bot is None:
        _telegram_bot = TelegramBot()
        logger.info(f"✅ TelegramBot Singleton created sync (ID: {id(_telegram_bot)})")
    return _telegram_bot