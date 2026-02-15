"""Main entry point for the Gateway."""
import logging
import asyncio
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gateway.config import config
from gateway.http_api import router as api_router
from gateway.ollama_client import ollama_client
from integrations.telegram_bot import get_telegram_bot
from integrations.gmail_client import gmail_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def start_telegram_bot():
    """Start Telegram bot in a separate thread with proper asyncio handling."""
    import asyncio
    
    bot = get_telegram_bot()
    if not bot.bot_token or bot.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.info("Telegram bot not configured, skipping...")
        return

    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Initialize the application
        loop.run_until_complete(bot.application.initialize())
        
        # Start the bot
        loop.run_until_complete(bot.application.start())
        
        # Start polling without the allowed_updates parameter or with correct value
        loop.run_until_complete(
            bot.application.updater.start_polling()
        )
        
        logger.info("Telegram bot started successfully")
        
        # Keep the thread alive
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Telegram bot error: {e}")
    finally:
        # Cleanup
        try:
            loop.run_until_complete(bot.application.updater.stop())
            loop.run_until_complete(bot.application.stop())
            loop.run_until_complete(bot.application.shutdown())
        except:
            pass
        finally:
            loop.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting Gateway...")

    # Load config
    try:
        config.load("config.yaml")
        logger.info("Configuration loaded")
    except FileNotFoundError as e:
        logger.error(f"Config file not found: {e}")
        raise

    # Test Ollama connection
    try:
        ollama_client.list_models()
        logger.info("Ollama connection OK")
    except Exception as e:
        logger.warning(f"Ollama connection failed: {e}")

    # Start Telegram bot in background (optional)
    telegram_token = config.get("telegram.bot_token")
    if telegram_token and telegram_token != "YOUR_TELEGRAM_BOT_TOKEN":
        logger.info("Starting Telegram bot in background...")
        bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
        bot_thread.start()
    else:
        logger.info("Telegram bot not configured (telegram.bot_token missing or default)")

    yield

    # Shutdown
    logger.info("Shutting down Gateway...")


# Create FastAPI app
app = FastAPI(
    title="Ollama Gateway",
    description="Minimalistisches Gateway mit Ollama, Telegram, Gmail & Shell-Integration",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    # Load config before starting
    try:
        config.load("config.yaml")
    except FileNotFoundError:
        logger.warning("config.yaml not found, using defaults")
    
    host = config.get("host", "0.0.0.0")
    port = config.get("port", 8000)

    uvicorn.run(app, host=host, port=port)