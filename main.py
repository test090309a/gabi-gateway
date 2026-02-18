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
from gateway.daemon import get_daemon, start_daemon, stop_daemon
from integrations.telegram_bot import get_telegram_bot
from integrations.gmail_client import gmail_client

# === CUSTOM LOG LEVEL: MUTED ===
MUTED_LEVEL = 15
logging.addLevelName(MUTED_LEVEL, "MUTED")


def _muted(self, message, *args, **kwargs):
    if self.isEnabledFor(MUTED_LEVEL):
        self._log(MUTED_LEVEL, message, args, **kwargs)


if not hasattr(logging.Logger, "muted"):
    logging.Logger.muted = _muted

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
    QUIET_LEVELS = ['INFO', 'MUTED']  # Weniger dominant
    LOUD_LEVELS = ['WARNING', 'ERROR', 'CRITICAL']  # Laut

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stealth_mode = STEALTH_MODE
        self.chatty_mode = CHATTY_MODE

    def format(self, record):
        original_level = record.levelname
        if record.levelname == "INFO" and not self.chatty_mode:
            record.levelname = "MUTED"

        # Module/category-based color
        full_name = record.name.lower()
        category = record.name.split('.')[-1].upper() if '.' in record.name else record.name.upper()
        record.category = category

        # Determine color based on module
        color = 'white'
        for key, col in self.COLORS.items():
            if key in full_name:
                color = col
                break

        # Apply stealth/chatty mode
        if self.stealth_mode and record.levelname in self.QUIET_LEVELS:
            record.levelname = ''  # Hide quiet logs in stealth
            color = 'dim'  # Dim everything

        if self.chatty_mode:
            color = 'white'  # More visible in chatty mode

        if record.levelname == "MUTED" and not self.chatty_mode:
            color = 'white'
            record.category = f"\033[90m{record.category}\033[0m"

        # Set color for module
        record.log_color = color

        raw_msg = record.getMessage()
        if record.levelname == "MUTED" and not self.chatty_mode:
            # Show muted logs in gray without noisy level labels.
            record.msg = f"\033[90m{raw_msg}\033[0m"
            record.args = ()
        elif record.levelno >= logging.WARNING:
            record.msg = f"[{original_level}] {raw_msg}"
            record.args = ()

        # Dim certain patterns in stealth mode
        if self.stealth_mode and 'api/tags' in record.getMessage():
            record.msg = '[API] ' + record.msg.split('[API]')[-1] if '[API]' in record.msg else record.msg

        return super().format(record)


def setup_gateway_logging():
    """Setup buntes Gateway-Logging mit Blade-Runner-Style."""
    global STEALTH_MODE, CHATTY_MODE

    if not colorlog:
        logging.basicConfig(
            level=MUTED_LEVEL,
            format="%(asctime)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        return

    # Farbpalette: Schwarz/Weiß/Rot + Highlights

    # log_format = "%(cyan)s%(asctime)s%(reset)s \033[90m|\033[0m %(log_color)s%(name)-35s%(reset)s \033[90m|\033[0m %(white)s%(message)s"

    log_format = (
        "%(cyan)s%(asctime)s%(reset)s "
        "\033[90m|\033[0m "
        "%(log_color)s%(name)-30s%(reset)s "
        "\033[90m|\033[0m "
        "%(white)s%(message)s"
    )

    date_format = "%H:%M:%S"

    handler = colorlog.StreamHandler()
    handler.setFormatter(GatewayFormatter(
        log_format,
        datefmt=date_format,
        log_colors={
            'DEBUG': 'cyan',
            'MUTED': 'white',
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
        logger.setLevel(MUTED_LEVEL)

    # Log-Level für httpx/uvicorn reduzieren
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.error').setLevel(MUTED_LEVEL)

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
{dim}╔═══════════════════════════════════════════════════════╗{reset}
{dim}║{reset}  {bold}{red}███{white}███{red}███{white}  {bold}GABI{red}  {white}GATEWAY{red}  v1.0.2{reset}                     {dim}║{reset}
{dim}║{reset}        {white}More human than human{reset}                          {dim}║{reset}
{dim}║{reset}  {dim}"I've seen things you people wouldn't believe..."{reset}    {dim}║{reset}
{dim}║{reset}                                                       {dim}║{reset}
{dim}║{reset}  {white}[{red}={white}] System:  {white}ONLINE{reset}                                  {dim}║{reset}
{dim}║{reset}  {white}[{red}={white}] Mode:    {white}{'STEALTH' if STEALTH_MODE else 'CHATTY' if CHATTY_MODE else 'NORMAL'}{reset}                                  {dim}║{reset}
{dim}║{reset}  {white}[{red}={white}] Time:    {white}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{reset}                     {dim}║{reset}
{dim}╚═══════════════════════════════════════════════════════╝{reset}

{red}❧{white} {quote}{reset}
"""
    print(header)


# === SETUP LOGGING ===
setup_gateway_logging()

# 1. Namen kürzen für perfekte Bündigkeit (Gegen das Springen)
logging.getLogger("apscheduler.scheduler").name = "SCHEDULER"
logging.getLogger("telegram.ext.Application").name = "TELEGRAM"
logging.getLogger("gateway.http_api").name = "HTTP_API"
logging.getLogger("gateway.ollama_client").name = "OLLAMA"

# 2. Den nervigen Uvicorn-Startup-Text eliminieren
logging.getLogger("uvicorn.error").disabled = True
logging.getLogger("uvicorn.access").disabled = True

# 3. Google-Cache-Warnung unterdrücken
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

logger = logging.getLogger("GATEWAY") # Großgeschrieben sieht es schöner aus

def _build_dashboard_urls(host: str, port: int) -> tuple[str, str]:
    """Return bind URL and browser-friendly dashboard URL."""
    bind_url = f"http://{host}:{port}"
    dashboard_host = "localhost" if host in ("0.0.0.0", "::") else host
    dashboard_url = f"http://{dashboard_host}:{port}"
    return bind_url, dashboard_url


def start_telegram_bot():
    """Start Telegram bot."""
    import asyncio

    bot = get_telegram_bot()
    if not bot.bot_token or bot.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.muted("Telegram: Nicht konfiguriert, überspringe...")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(bot.application.initialize())
        loop.run_until_complete(bot.application.start())
        loop.run_until_complete(bot.application.updater.start_polling())

        logger.muted("Telegram: Bot gestartet!")

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
    print_blade_runner_header()
    logger.muted("Gateway: Starte System...")

    # Load config
    try:
        config.load("config.yaml")
        logger.muted("Config: Geladen")
    except FileNotFoundError as e:
        logger.error(f"Config: Nicht gefunden - {e}")
        raise

    # Test Ollama
    try:
        models = ollama_client.list_models()
        model_count = len(models.get("models", []))
        logger.muted(f"Ollama: Verbunden ({model_count} Modelle)")
    except Exception as e:
        logger.warning(f"Ollama: Nicht erreichbar - {e}")

    # Telegram
    telegram_enabled = config.get("telegram.enabled", False)
    telegram_token = config.get("telegram.bot_token")

    if telegram_enabled and telegram_token and telegram_token != "YOUR_TELEGRAM_BOT_TOKEN":
        logger.muted("Telegram: Starte Bot...")
        bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
        bot_thread.start()
    else:
        logger.muted("Telegram: Deaktiviert")

    # Gateway Daemon für autonome Aufgaben
    try:
        start_daemon()
        logger.muted("Daemon: Aktiv")
    except Exception as e:
        logger.warning(f"Daemon: Nicht gestartet - {e}")

    # AutoLearn Daemon starten
    try:
        daemon = get_daemon()
        daemon.start()
        logger.muted("Daemon: Autonomer Agent aktiv")
    except Exception as e:
        logger.warning(f"Daemon: Start fehlgeschlagen - {e}")

    # Gateway Mode Announcement
    if STEALTH_MODE:
        logger.warning("Mode: STEALTH - Minimale Ausgabe aktiviert")
    elif CHATTY_MODE:
        logger.muted("Mode: CHATTY - Verbose Logging aktiviert")
    else:
        logger.muted("Mode: NORMAL")

    host = config.get("host", "0.0.0.0")
    port = config.get("port", 8000)
    bind_url, dashboard_url = _build_dashboard_urls(host, port)
    # logger.muted(f"DASHBOARD: {dashboard_url}")

    # Nutze logger.muted oder print, damit es im Worker erscheint
    # \033[90m ist das typische Grau für "Muted" oder Metadaten
    print(f"  \033 \033[0m")
    print(f"  \033[91mGateway:        {bind_url}\033[0m")
    # print(f"  \033[90mDashboard:      {dashboard_url}\033[0m")
    print(f"  \033[97mAPI:            {dashboard_url}/docs\033[0m")
    print(f"  \033[91mStatus:         \033[3mOnline\033[0m\n")
    print(f"  \033 \033[0m")

    yield

    logger.muted("Gateway: Shutdown...")
    stop_daemon()


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

    bind_url, dashboard_url = _build_dashboard_urls(host, port)
    print(f"  Gateway (bind): {bind_url}")
    print(f"  Dashboard:      {dashboard_url}")
    print(f"  API:            {dashboard_url}/docs")
    print("  Status:         Online")
    print("\n  Druecke STRG+C zum Beenden\n")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_config=None,
        access_log=False,
    )
