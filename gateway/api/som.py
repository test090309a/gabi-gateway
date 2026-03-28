# gateway/api/som.py
"""Set-of-Mark (SoM) Agent API endpoints."""

import re
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Header, HTTPException, Depends

from gateway.auth import verify_token
from gateway.config import config
from gateway.ollama_client import ollama_client

logger = logging.getLogger(__name__)

router = APIRouter()


class SoMAgentWrapper:
    """Wrapper für SoM Agent mit Lazy-Import."""
    
    _agent = None
    _available = None
    
    @classmethod
    def get_agent(cls, headless: bool = True):
        if cls._agent is None and cls._available is not False:
            try:
                from gateway.integrations.som_agent import get_som_agent
                cls._agent = get_som_agent(headless=headless)
                cls._available = True
                logger.info("✅ SoM Agent initialized")
            except ImportError as e:
                logger.warning(f"⚠️ SoM Agent not available: {e}")
                cls._available = False
        return cls._agent
    
    @classmethod
    def is_available(cls):
        if cls._available is None:
            cls.get_agent()
        return cls._available is True


def get_som_agent(headless: bool = True):
    return SoMAgentWrapper.get_agent(headless)


@router.post("/som/navigate")
async def som_navigate(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Autonome Navigation mit SoM Agent."""
    url = payload.get("url", "")
    goal = payload.get("goal", "Erkunde die Seite")
    max_steps = payload.get("max_steps", 5)
    
    if not url:
        return {"status": "error", "reply": "❌ Keine URL angegeben"}
    
    agent = get_som_agent(headless=False)
    if not agent:
        return {"status": "error", "reply": "❌ SoM Agent nicht verfügbar"}
    
    try:
        result = await agent.navigate(url=url, goal=goal, max_steps=max_steps)
        
        if result.get("success"):
            extracted = result.get("extracted_content", {})
            results_count = len(extracted.get("search_results", []))
            
            reply = f"✅ **SoM Navigation erfolgreich!**\n\n"
            reply += f"📍 URL: {url}\n"
            reply += f"🎯 Ziel: {goal}\n"
            reply += f"📊 Schritte: {result.get('steps_taken', 0)}\n"
            
            if results_count > 0:
                reply += f"\n🔍 **Suchergebnisse ({results_count}):**\n\n"
                for i, res in enumerate(extracted.get("search_results", [])[:5], 1):
                    title = res.get('title', 'Kein Titel')
                    reply += f"{i}. **{title}**\n"
                    if res.get('url'):
                        reply += f"   🔗 {res.get('url', '')[:80]}\n"
                    reply += "\n"
            else:
                text = extracted.get('text', '')
                if text:
                    reply += f"\n📄 Content extrahiert: {len(text)} Zeichen\n"
            
            return {"status": "success", "reply": reply}
        else:
            return {"status": "error", "reply": f"❌ Navigation fehlgeschlagen: {result.get('error')}"}
    except Exception as e:
        logger.error(f"SoM navigate error: {e}")
        return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}


@router.post("/som/search")
async def som_search(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Führt eine Suche mit Startpage durch."""
    query = payload.get("query", "").strip()
    if not query:
        return {"status": "error", "reply": "❌ Keine Suchanfrage angegeben"}
    
    agent = get_som_agent(headless=True)
    if not agent:
        return {"status": "error", "reply": "❌ SoM Agent nicht verfügbar"}
    
    try:
        result = await agent.navigate(
            url="https://www.startpage.com",
            goal=f"Suche nach '{query}'",
            max_steps=5
        )
        
        if result.get("success"):
            extracted = result.get("extracted_content", {})
            results = extracted.get("search_results", [])
            
            if results:
                reply = f"🔍 **Suchergebnisse für '{query}':**\n\n"
                for i, res in enumerate(results[:10], 1):
                    title = res.get('title', 'Kein Titel')
                    url = res.get('url', '')
                    reply += f"{i}. **{title}**\n"
                    reply += f"   🔗 {url[:80]}\n\n"
                return {"status": "success", "reply": reply, "results": results[:10]}
            else:
                return {"status": "error", "reply": f"❌ Keine Ergebnisse für '{query}'"}
        else:
            return {"status": "error", "reply": f"❌ Suche fehlgeschlagen: {result.get('error')}"}
    except Exception as e:
        return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}


@router.get("/som/learned")
async def som_learned(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Zeigt gelernte Inhalte des SoM Agents."""
    agent = get_som_agent()
    if not agent:
        return {"status": "error", "reply": "❌ SoM Agent nicht verfügbar"}
    
    learned = agent.memory.get("learned_actions", [])[-10:]
    
    if not learned:
        return {"status": "success", "reply": "📭 Noch keine gelernten Inhalte."}
    
    reply = "🧠 **Letzte 10 gelernte Inhalte:**\n\n"
    for i, entry in enumerate(learned, 1):
        if entry.get("url"):
            reply += f"{i}. 🌐 {entry.get('url', '')[:60]}\n"
            reply += f"   🎯 {entry.get('goal', '')[:60]}\n"
            reply += f"   📅 {entry.get('learned_at', '')[:19]}\n\n"
        else:
            reply += f"{i}. 📝 {entry.get('text', '')[:80]}\n\n"
    
    return {"status": "success", "reply": reply, "learned": learned}


@router.get("/som/stats")
async def som_stats(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Zeigt Statistiken des SoM Agents."""
    agent = get_som_agent()
    if not agent:
        return {"status": "error", "reply": "❌ SoM Agent nicht verfügbar"}
    
    memory_file = Path(__file__).parent.parent / "integrations" / "som_memory.json"
    learned = agent.memory.get("learned_actions", [])
    
    total_results = 0
    urls = set()
    for entry in learned:
        if entry.get("url"):
            urls.add(entry.get("url"))
        content = entry.get("content", {})
        total_results += len(content.get("search_results", []))
    
    memory_size = memory_file.stat().st_size if memory_file.exists() else 0
    
    reply = f"📊 **SoM Agent Statistiken:**\n\n"
    reply += f"📚 Gelernte Aktionen: {len(learned)}\n"
    reply += f"🌐 Besuchte URLs: {len(urls)}\n"
    reply += f"🔍 Gespeicherte Suchergebnisse: {total_results}\n"
    reply += f"💾 Memory-Größe: {memory_size / 1024:.1f} KB\n"
    
    return {"status": "success", "reply": reply, "stats": {
        "learned_actions": len(learned),
        "unique_urls": len(urls),
        "search_results": total_results,
        "memory_size_kb": round(memory_size / 1024, 1)
    }}


@router.post("/som/clear")
async def som_clear(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Löscht das SoM Memory."""
    agent = get_som_agent()
    if not agent:
        return {"status": "error", "reply": "❌ SoM Agent nicht verfügbar"}
    
    memory_file = Path(__file__).parent.parent / "integrations" / "som_memory.json"
    
    if memory_file.exists():
        backup = memory_file.with_suffix(f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        backup.write_bytes(memory_file.read_bytes())
    
    empty_memory = {"pages": {}, "learned_actions": []}
    memory_file.write_text(json.dumps(empty_memory, indent=2, ensure_ascii=False), encoding='utf-8')
    agent.memory = empty_memory
    
    return {"status": "success", "reply": "✅ SoM Memory wurde gelöscht. Backup wurde erstellt."}


@router.get("/som/help")
async def som_help(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Zeigt Hilfe für SoM Agent-Befehle an."""
    help_text = """🤖 **SoM (Set-of-Mark) Agent Befehle:**

**Navigation:**
`/som/navigate <url> <ziel>` - Autonome Navigation
`/som/search <suchbegriff>` - Suche mit Startpage

**Memory:**
`/som/learned` - Gelernte Inhalte anzeigen
`/som/stats` - Statistiken anzeigen
`/som/clear` - Memory löschen

**Beispiele:**
- `/som/search Python Tutorial`
- `/som/navigate https://example.com "Finde den Login-Button"`
- `/som/learned` - Was habe ich gelernt?`"""
    
    return {"status": "success", "help": help_text}