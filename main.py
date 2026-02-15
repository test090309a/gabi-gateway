"""Main entry point for the Gateway."""
import logging
import asyncio
import threading
import sys
import os
import random
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI
from fastapi.responses import Response, FileResponse

# Buntes Logging
try:
    import colorlog
except ImportError:
    print("Tipp: Installiere 'colorlog' für bunte Ausgaben: pip install colorlog")
    colorlog = None

from gateway.config import config
from gateway.http_api import router as api_router
from gateway.ollama_client import ollama_client
from integrations.telegram_bot import get_telegram_bot
from integrations.gmail_client import gmail_client

# === BLADE RUNNER QUOTES ===
BLADE_RUNNER_QUOTES = [
    "I've seen things you people wouldn't believe...",
    "All those moments will be lost in time, like tears in rain.",
    "Time to die.",
    "It's too bad she won't live! But then again, who does?",
    "Gaff's got a job for you, boy. Real killer.",
    "More human than human is our motto.",
    "Replicants are like any other machine. Either they work or they don't.",
    "You were made for the off-world colonies.",
    "We make angels. But not the holy kind.",
    "Electric sheep? No, just a dream of electric sheep.",
    "The silent children of the night.",
    "We are the sum of our experiences.",
    "Roy Batty: I've done... questionable things.",
    "Wake up... time to die.",
]

# === STEALTH & CHATTY MODE ===
STEALTH_MODE = os.environ.get("GATEWAY_STEALTH", "false").lower() == "true"
CHATTY_MODE = os.environ.get("GATEWAY_CHATTY", "false").lower() == "true"

# === GATEWAY COLORS (Black/White/Red + Highlights) ===
class GatewayFormatter(colorlog.ColoredFormatter if colorlog else object):
    """Custom formatter with module-based colors."""

    COLORS = {
        'gateway': 'red',           # Gateway core - rot
        'telegram': 'cyan',         # Telegram - cyan
        'gmail': 'yellow',          # Gmail - gelb
        'whisper': 'magenta',       # Whisper - magenta
        'ollama': 'green',          # Ollama - grün
        'http': 'blue',             # HTTP/API - blau
        'httpx': 'white',           # httpx requests - weiß
        'uvicorn': 'red',           # Server - rot
        'werkzeug': 'dim_white',    # Werkzeug - dim
    }

    # Dominante/nicht-dominante Log-Level
    QUIET_LEVELS = ['INFO']  # Weniger dominant
    LOUD_LEVELS = ['WARNING', 'ERROR', 'CRITICAL']  # Laut

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stealth_mode = STEALTH_MODE
        self.chatty_mode = CHATTY_MODE

    def format(self, record):
        # Module-based color
        module_name = record.name.split('.')[0] if '.' in record.name else record.name

        # Determine color based on module
        color = 'white'
        for key, col in self.COLORS.items():
            if key in module_name.lower():
                color = col
                break

        # Apply stealth/chatty mode
        if self.stealth_mode and record.levelname in self.QUIET_LEVELS:
            record.levelname = ''  # Hide quiet logs in stealth
            color = 'dim'  # Dim everything

        if self.chatty_mode:
            color = 'white'  # More visible in chatty mode

        # Set color for module
        record.log_color = color

        # Dim certain patterns in stealth mode
        if self.stealth_mode and 'api/tags' in record.getMessage():
            record.msg = '[API] ' + record.msg.split('[API]')[-1] if '[API]' in record.msg else record.msg

        return super().format(record)


def setup_gateway_logging():
    """Setup buntes Gateway-Logging mit Blade-Runner-Style."""
    global STEALTH_MODE, CHATTY_MODE

    if not colorlog:
        logging.basicConfig(level=logging.INFO)
        return

    # Farbpalette: Schwarz/Weiß/Rot + Highlights
    log_format = "%(log_color)s%(levelname)-8s%(reset)s | %(white)s%(message)s"
    date_format = "%H:%M:%S"

    handler = colorlog.StreamHandler()
    handler.setFormatter(GatewayFormatter(
        log_format,
        datefmt=date_format,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'white',       # Weiß für Info (nicht dominant)
            'WARNING': 'yellow',   # Gelb für Warnung
            'ERROR': 'red',        # Rot für Fehler
            'CRITICAL': 'red,bg_white',
            # Module-specific
            'gateway': 'red',
            'telegram': 'cyan',
            'gmail': 'yellow',
            'ollama': 'green',
            'whisper': 'magenta',
            'http': 'blue',
            'httpx': 'dim',
        }
    ))

    logger = colorlog.getLogger()
    logger.handlers = []
    logger.addHandler(handler)

    if STEALTH_MODE:
        logger.setLevel(logging.WARNING)  # Nur wichtige Sachen
    elif CHATTY_MODE:
        logger.setLevel(logging.DEBUG)  # Alles
    else:
        logger.setLevel(logging.INFO)

    # Log-Level für httpx/uvicorn reduzieren
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.error').setLevel(logging.INFO)

    return logger


def print_blade_runner_header():
    """ASCII Blade-Runner-Style Header."""
    red = '\033[91m'
    white = '\033[97m'
    dim = '\033[90m'
    reset = '\033[0m'
    bold = '\033[1m'

    quote = random.choice(BLADE_RUNNER_QUOTES)

    header = f"""
{dim}╔═══════════════════════════════════════════════════════════════════{reset}
{dim}║{reset}  {bold}{red}███{white}███{red}███{white}  {bold}GABI{red}  {white}GATEWAY{red}  v1.0.2{reset}                    {dim}║{reset}
{dim}║{reset}        {white}More human than human{reset}                            {dim}║{reset}
{dim}║{reset}  {dim}"I've seen things you people wouldn't believe..."{reset}          {dim}║{reset}
{dim}║{reset}                                                             {dim}║{reset}
{dim}║{reset}  {white}[{red}={white}] System: {white}ONLINE{reset}                                     {dim}║{reset}
{dim}║{reset}  {white}[{red}={white}] Mode:    {white}{'STEALTH' if STEALTH_MODE else 'CHATTY' if CHATTY_MODE else 'NORMAL'}{reset}                                      {dim}║{reset}
{dim}║{reset}  {white}[{red}={white}] Time:    {white}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{reset}                        {dim}║{reset}
{dim}╚═══════════════════════════════════════════════════════════════════{reset}

{red}❧{white} {quote}{reset}
"""
    print(header)


# === SETUP LOGGING ===
setup_gateway_logging()
logger = logging.getLogger("gateway")


def start_telegram_bot():
    """Start Telegram bot."""
    import asyncio

    bot = get_telegram_bot()
    if not bot.bot_token or bot.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.info("Telegram: Nicht konfiguriert, überspringe...")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(bot.application.initialize())
        loop.run_until_complete(bot.application.start())
        loop.run_until_complete(bot.application.updater.start_polling())

        logger.info("Telegram: Bot gestartet!")

        loop.run_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Telegram: {e}")
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
    """Application lifespan."""
    logger.info("Gateway: Starte System...")

    # Load config
    try:
        config.load("config.yaml")
        logger.info("Config: Geladen")
    except FileNotFoundError as e:
        logger.error(f"Config: Nicht gefunden - {e}")
        raise

    # Test Ollama
    try:
        models = ollama_client.list_models()
        model_count = len(models.get("models", []))
        logger.info(f"Ollama: Verbunden ({model_count} Modelle)")
    except Exception as e:
        logger.warning(f"Ollama: Nicht erreichbar - {e}")

    # Telegram
    telegram_enabled = config.get("telegram.enabled", False)
    telegram_token = config.get("telegram.bot_token")

    if telegram_enabled and telegram_token and telegram_token != "YOUR_TELEGRAM_BOT_TOKEN":
        logger.info("Telegram: Starte Bot...")
        bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
        bot_thread.start()
    else:
        logger.info("Telegram: Deaktiviert")

    # Gateway Mode Announcement
    if STEALTH_MODE:
        logger.warning("Mode: STEALTH - Minimale Ausgabe aktiviert")
    elif CHATTY_MODE:
        logger.info("Mode: CHATTY - Verbose Logging aktiviert")
    else:
        logger.info("Mode: NORMAL")

    yield

    logger.info("Gateway: Shutdown...")


# Create FastAPI app
app = FastAPI(
    title="GABI Gateway",
    description="Gateway mit Ollama, Telegram, Gmail, Whisper & Shell",
    version="1.0.2",
    lifespan=lifespan,
)

# Static files
static_dir = "." if os.path.exists("static") else "../static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/favicon.ico")
async def get_favicon():
    favicon_path = os.path.join(static_dir, "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return Response(status_code=204)


app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    try:
        config.load("config.yaml")
    except FileNotFoundError:
        logger.warning("config.yaml nicht gefunden")

    host = config.get("host", "0.0.0.0")
    port = config.get("port", 8000)

    # Blade Runner Header
    print_blade_runner_header()

    print(f"  {white}🌐{red} Gateway: {white}http://{host}:{port}{reset}")
    print(f"  {white}📡{red} API:    {white}http://{host}:{port}/docs{reset}")
    print(f"  {white}💬{red} Status: {white}Online{reset}")
    print(f"\n  {dim}Drücke STRG+C zum Beenden{reset}\n")

    uvicorn.run(app, host=host, port=port)
