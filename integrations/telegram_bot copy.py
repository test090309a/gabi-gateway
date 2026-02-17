"""Telegram bot integration."""
import logging
import asyncio
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

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Hallo! Ich bin ein Ollama-Gateway-Bot. "
            "Schreibe mir etwas und ich werde es an Ollama weiterleiten."
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Befehle:\n/start - Bot starten\n/clear - Gesprächsverlauf löschen\n/help - Hilfe"
        )

    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self._user_sessions.pop(user_id, None)
        await update.message.reply_text("Gesprächsverlauf gelöscht.")

    # In integrations/telegram_bot.py - in der handle_message Methode:
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_message = update.message.text
        timestamp = datetime.now().isoformat()  # <-- Timestamp hinzufügen
        
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []

        messages = self._user_sessions[user_id]
        
        # User-Nachricht mit Timestamp speichern
        messages.append({
            "role": "user", 
            "content": user_message,
            "timestamp": timestamp  # <-- Hier
        })

        try:
            response = ollama_client.chat(messages=messages)
            assistant_message = response.get("message", {}).get("content", "")
            
            # Bot-Antwort mit Timestamp speichern
            messages.append({
                "role": "assistant", 
                "content": assistant_message,
                "timestamp": datetime.now().isoformat()  # <-- Und hier
            })
            
            await update.message.reply_text(assistant_message)
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            await update.message.reply_text(f"Fehler: {e}")
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
            telegram_bot.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_bot.handle_message)
            )
    return telegram_bot
