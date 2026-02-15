"""Main entry point for the Gateway."""
import logging
import asyncio
import threading
import sys
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles

# Neu: Import für bunte Konsolenausgabe
try:
    import colorlog
except ImportError:
    # Falls colorlog nicht installiert ist, geben wir einen Hinweis aus
    print("Tipp: Installiere 'colorlog' für bunte Ausgaben: pip install colorlog")
    colorlog = None

from fastapi import FastAPI

from gateway.config import config
from gateway.http_api import router as api_router
from gateway.ollama_client import ollama_client
from integrations.telegram_bot import get_telegram_bot
from integrations.gmail_client import gmail_client

# --- Konfiguration des bunten Loggings ---
def setup_logging():
    log_format = "%(asctime)s - %(name)s - %(log_color)s%(levelname)-8s%(reset)s - %(white)s%(message)s"
    
    if colorlog:
        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            log_format,
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                'DEBUG':    'cyan',
                'INFO':     'green',
                'WARNING':  'yellow',
                'ERROR':    'red',
                'CRITICAL': 'red,bg_white',
            }
        ))
        logger = colorlog.getLogger()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

setup_logging()
logger = logging.getLogger(__name__)


def start_telegram_bot():
    """Start Telegram bot in a separate thread with proper asyncio handling."""
    import asyncio
    
    bot = get_telegram_bot()
    # Prüfung auf Token und ob der Bot überhaupt aktiv sein soll
    if not bot.bot_token or bot.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.info("Telegram bot not configured, skipping...")
        return

    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(bot.application.initialize())
        loop.run_until_complete(bot.application.start())
        loop.run_until_complete(bot.application.updater.start_polling())
        
        logger.info("Telegram bot gestartet und bereit!") # Jetzt in Grün
        
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Telegram bot error: {e}")
    finally:
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
    logger.info("Starting Gateway...")

    # Load config
    try:
        config.load("config.yaml")
        logger.info("Configuration geladen")
    except FileNotFoundError as e:
        logger.error(f"Config file not found: {e}")
        raise

    # Test Ollama connection
    try:
        ollama_client.list_models()
        logger.info("Ollama Verbindung steht!")
    except Exception as e:
        logger.warning(f"Ollama nicht erreichbar: {e}")

    # Start Telegram bot nur wenn explizit gewünscht
    # Erwartet in config.yaml: telegram: { enabled: true, bot_token: "..." }
    telegram_enabled = config.get("telegram.enabled", False)
    telegram_token = config.get("telegram.bot_token")
    
    if telegram_enabled and telegram_token and telegram_token != "YOUR_TELEGRAM_BOT_TOKEN":
        logger.info("Starte Telegram Bot im Hintergrund...")
        bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
        bot_thread.start()
    else:
        logger.info("Telegram Bot ist deaktiviert (siehe config.yaml 'telegram.enabled')")

    yield

    logger.info("Shutting down Gateway...")


# Create FastAPI app
app = FastAPI(
    title="Ollama Gateway",
    description="Minimalistisches Gateway mit Ollama, Telegram, Gmail & Shell-Integration",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="."), name="static")
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    try:
        config.load("config.yaml")
    except FileNotFoundError:
        logger.warning("config.yaml not found, using defaults")
    
    host = config.get("host", "0.0.0.0")
    port = config.get("port", 8000)

    # Kleiner visueller Start-Hinweis
    print(f"\033[1;35m" + "="*50 + "\033[0m")
    print(f"\033[1;36mGateway läuft auf http://{host}:{port}\033[0m")
    print(f"\033[1;35m" + "="*50 + "\033[0m")

    uvicorn.run(app, host=host, port=port)