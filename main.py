# gateway/main.py
"""FastAPI App-Konfiguration und Router-Registrierung für GABI Gateway."""

import os
import sys
import logging
import colorlog

# Konfiguriere root logger mit Farben
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    log_colors={
        'DEBUG': 'white',
        'INFO': 'white',      # Weiß/Grau statt Grün
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }
))

root_logger = logging.getLogger()
root_logger.addHandler(handler)
root_logger.setLevel(logging.INFO)

# Setze laute Logger auf WARNING
for noisy_logger in ['httpx', 'chromadb', 'urllib3', 'selenium', 'webdriver_manager']:
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

import platform
import asyncio
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('gateway.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


# ===== LIFESPAN MANAGER =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager für Startup und Shutdown."""
    # Startup
    logger.info("=" * 60)
    logger.info("🧠 Gateway startet...")
    logger.info("=" * 60)
    
    try:
        # 1. Config laden - WICHTIG: explizit laden!
        from gateway.config import config
        config_path = Path("config.yaml")
        
        if config_path.exists():
            config.load(str(config_path))
            logger.info(f"✅ Config geladen von {config_path}")
        else:
            logger.error(f"❌ Config file not found: {config_path}")
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        logger.info(f"✅ Config geladen - API Key: {'*' * 8}...")
        
        # 2. Ollama Client initialisieren
        from gateway.ollama_client import ollama_client
        try:
            models = ollama_client.list_models()
            model_count = len(models.get("models", []))
            logger.info(f"✅ Ollama Client initialisiert - {model_count} Modelle verfügbar")
        except Exception as e:
            logger.warning(f"⚠️ Ollama nicht erreichbar: {e}")
        
        # 3. Chat Memory initialisieren
        from gateway.core.memory import chat_memory
        logger.info(f"✅ Chat Memory initialisiert - {len(chat_memory.conversation_history)} Konversationen")
        
        # 4. Brain (Corpus Callosum) initialisieren
        from gateway.core.brain import get_brain
        brain = get_brain()
        brain.initialize_hemispheres()
        logger.info(f"✅ Corpus Callosum aktiviert - Linke & Rechte Hemisphäre")
        
        # 5. Integration Watcher starten
        from gateway.core.integration_watcher import init_integration_watcher
        init_integration_watcher(app, auto_start=True)
        logger.info(f"✅ Integration Watcher gestartet")
        
        # 6. Progress Cleanup starten
        from gateway.core.progress import init_progress_cleanup
        init_progress_cleanup(interval_seconds=300)
        logger.info(f"✅ Progress Cleanup gestartet")
        
        # 7. Telegram Bot starten
        telegram_config = config.data.get("telegram", {})
        telegram_enabled = telegram_config.get("enabled", False)

        logger.info(f"📱 Telegram Config: enabled={telegram_enabled}, bot_token={telegram_config.get('bot_token', '')[:15]}...")

        if telegram_enabled:
            try:
                from gateway.integrations.telegram_bot import get_telegram_bot
                bot = await get_telegram_bot()  # async!
                await bot.start()
                logger.info("🚀 Telegram Bot gestartet")
            except Exception as e:
                logger.error(f"❌ Telegram Bot konnte nicht gestartet werden: {e}")
                import traceback
                traceback.print_exc()
        else:
            logger.info("ℹ️ Telegram ist in config.yaml deaktiviert")
        
        # 8. System-Informationen
        logger.info(f"🖥️  System: {platform.system()} {platform.release()}")
        logger.info(f"🐍 Python: {platform.python_version()}")
        logger.info(f"📁 Working Dir: {os.getcwd()}")
        
        # 9. Static dashboard prüfen
        static_dir = Path(__file__).parent / "static"
        dashboard_path = static_dir / "index.html"
        if dashboard_path.exists():
            logger.info(f"✅ Dashboard verfügbar: http://localhost:8000")
        else:
            logger.warning(f"⚠️ Dashboard nicht gefunden: {dashboard_path}")
            await _create_minimal_dashboard(dashboard_path)
        
        logger.info("=" * 60)
        logger.info("🚀 GABI Gateway erfolgreich gestartet!")
        logger.info(f"📚 API Docs: http://localhost:8000/docs")
        logger.info(f"📖 Redoc: http://localhost:8000/redoc")
        logger.info(f"🎨 Dashboard: http://localhost:8000")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Startup-Fehler: {e}")
        raise
    
    yield  # Hier läuft die App
    
    # Shutdown
    logger.info("=" * 60)
    logger.info("🛑 GABI Gateway wird heruntergefahren...")
    
    try:
        # Telegram Bot stoppen
        from gateway.config import config
        telegram_config = config.data.get("telegram", {})
        if telegram_config.get("enabled", False):
            try:
                from gateway.integrations.telegram_bot import get_telegram_bot
                bot = get_telegram_bot()
                await bot.stop()
                logger.info("🛑 Telegram Bot gestoppt")
            except Exception as e:
                logger.error(f"❌ Fehler beim Stoppen des Telegram Bots: {e}")
        
        # Integration Watcher stoppen
        from gateway.core.integration_watcher import shutdown_integration_watcher
        shutdown_integration_watcher()
        logger.info("✅ Integration Watcher gestoppt")
        
        # Memory speichern
        from gateway.core.memory import chat_memory
        chat_memory.update_heartbeat()
        logger.info("✅ Heartbeat aktualisiert")
        
        # Letzte Konversation archivieren wenn vorhanden
        if len(chat_memory.conversation_history) > 0:
            archive_path = chat_memory.save_chat_session()
            if archive_path:
                logger.info(f"✅ Letzte Konversation archiviert: {archive_path}")
        
    except Exception as e:
        logger.error(f"❌ Shutdown-Fehler: {e}")
    
    logger.info("👋 GABI Gateway beendet")
    logger.info("=" * 60)


# Create FastAPI app with lifespan
app = FastAPI(
    title="GABI Gateway",
    description="Gateway AI Bot Interface - Gehirn-aktivierter Assistent",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Import routers (after app creation to avoid circular imports)
from gateway.api import (
    chat,
    shell,
    gmail,
    calendar,
    telegram,
    gui,
    vision,
    whisper,
    comfy,
    memory,
    web,
    som,
    system,
    brain_api,
    integrations_api,
    models_api
)


# Register routers
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(shell.router, prefix="/api", tags=["Shell"])
app.include_router(gmail.router, prefix="/api", tags=["Gmail"])
app.include_router(calendar.router, prefix="/api", tags=["Calendar"])
app.include_router(telegram.router, prefix="/api", tags=["Telegram"])
app.include_router(gui.router, prefix="/api", tags=["GUI"])
app.include_router(vision.router, prefix="/api", tags=["Vision"])
app.include_router(whisper.router, prefix="/api", tags=["Whisper"])
app.include_router(comfy.router, prefix="/api", tags=["ComfyUI"])
app.include_router(memory.router, prefix="/api", tags=["Memory"])
app.include_router(web.router, prefix="/api", tags=["Web"])
app.include_router(som.router, prefix="/api", tags=["SoM"])
app.include_router(system.router, prefix="/api", tags=["System"])
app.include_router(brain_api.router, prefix="/api", tags=["Brain"])
app.include_router(integrations_api.router, prefix="/api", tags=["Integrations"])
app.include_router(models_api.router, prefix="/api", tags=["Models"])


# Static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"✅ Static files mounted from {static_dir}")
else:
    logger.warning(f"⚠️ Static directory not found: {static_dir}")
    static_dir.mkdir(exist_ok=True)


async def _create_minimal_dashboard(path: Path):
    """Create a minimal dashboard if none exists."""
    minimal_html = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GABI Gateway</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .card {
            background: rgba(255,255,255,0.95);
            color: #333;
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
        }
        h1 { margin-top: 0; color: #667eea; }
        .status { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }
        .online { background: #10b981; color: white; }
        .links { margin-top: 20px; }
        .links a { display: inline-block; margin-right: 15px; color: #667eea; text-decoration: none; }
        .links a:hover { text-decoration: underline; }
        pre { background: #f4f4f4; padding: 10px; border-radius: 8px; overflow-x: auto; }
    </style>
</head>
<body>
    <div class="card">
        <h1>🧠 GABI Gateway</h1>
        <p>Gateway AI Bot Interface - Gehirn-aktivierter Assistent</p>
        <div>
            <span class="status online">🟢 Online</span>
        </div>
        <div class="links">
            <a href="/docs">📚 API Docs (Swagger)</a>
            <a href="/redoc">📖 ReDoc</a>
            <a href="/api/status">📊 System Status</a>
        </div>
        <hr>
        <h3>📝 Hinweis</h3>
        <p>Das vollständige Dashboard wurde nicht gefunden. Bitte erstelle eine <code>static/index.html</code> Datei mit dem vollständigen Dashboard-Code.</p>
        <p>Das Dashboard wird unter folgendem Pfad erwartet:</p>
        <pre>M:\\projekte_2026\\gabi-gateway\\static\\index.html</pre>
        <p>API ist dennoch voll funktionsfähig. Nutze die Links oben für die API-Dokumentation.</p>
    </div>
</body>
</html>"""
    
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(minimal_html)
        logger.info(f"✅ Minimales Dashboard erstellt: {path}")
    except Exception as e:
        logger.error(f"❌ Fehler beim Erstellen des minimalen Dashboards: {e}")


@app.get("/")
async def root():
    """Root-Endpunkt - Zeigt das Dashboard oder API-Info."""
    dashboard_path = static_dir / "index.html"
    
    if dashboard_path.exists():
        try:
            with open(dashboard_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            return HTMLResponse(content=html_content)
        except Exception as e:
            logger.error(f"Fehler beim Lesen des Dashboards: {e}")
            return HTMLResponse(content=f"""
            <html>
            <body>
                <h1>GABI Gateway</h1>
                <p>Fehler beim Laden des Dashboards: {e}</p>
                <p><a href="/docs">API Docs</a></p>
            </body>
            </html>
            """)
    else:
        # Fallback: Minimales Dashboard anzeigen
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>GABI Gateway</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
                .card { background: rgba(255,255,255,0.95); color: #333; border-radius: 16px; padding: 30px; box-shadow: 0 20px 40px rgba(0,0,0,0.2); }
                h1 { margin-top: 0; color: #667eea; }
                .links a { display: inline-block; margin-right: 15px; color: #667eea; text-decoration: none; }
                .links a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🧠 GABI Gateway</h1>
                <p>Gateway AI Bot Interface - Gehirn-aktivierter Assistent</p>
                <div class="links">
                    <a href="/docs">📚 API Docs (Swagger)</a>
                    <a href="/redoc">📖 ReDoc</a>
                    <a href="/api/status">📊 System Status</a>
                </div>
                <hr>
                <p>Das vollständige Dashboard wurde nicht gefunden. Bitte erstelle eine <code>static/index.html</code> Datei.</p>
                <p>API ist dennoch voll funktionsfähig.</p>
            </div>
        </body>
        </html>
        """)


@app.get("/health")
async def health_check():
    """Health-Check Endpunkt."""
    from gateway.ollama_client import ollama_client
    
    ollama_status = "unknown"
    try:
        models = ollama_client.list_models()
        ollama_status = "healthy" if models.get("models") else "unhealthy"
    except Exception as e:
        ollama_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "ollama": ollama_status,
            "gateway": "running"
        }
    }


# ===== MAIN ENTRY POINT =====
if __name__ == "__main__":
    import uvicorn
    import argparse
    import os

    parser = argparse.ArgumentParser(description="🌉 GABI Gateway Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    # Stelle sicher, dass das static-Verzeichnis existiert
    static_dir.mkdir(exist_ok=True)

    # Fenster‑Titel im Terminal setzen
    title = f"🌉 Gabi-Gateway (http://{args.host}:{args.port})"
    if os.name == "nt":  # Windows
        os.system(f"title {title}")
    else:
        # ANSI‑Sequenz für Tab‑Titel (Linux/macOS/Terminals)
        print(f"\033]0;{title}\007", end="")

    uvicorn.run(
        "gateway.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )