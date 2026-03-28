# gateway/web_commands.py
"""Web-Kommandos für GABI Gateway - Integration mit bestehendem Ollama Client"""

import asyncio
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("GABI.web_commands")

# Globale Web-Gateway-Instanz
_web_gateway = None


def get_web_gateway(headless: bool = True):
    """Lazy-Initialisierung des Web Gateways"""
    global _web_gateway
    if _web_gateway is None:
        from gateway.web_agent_integration import get_web_gateway as _get
        _web_gateway = _get(headless=headless)
    return _web_gateway


async def handle_web_command(command: str) -> Dict[str, Any]:
    """
    Verarbeitet Web-Kommandos in GABI Gateway.
    
    Unterstützte Kommandos:
    - "suche nach [text] auf [url]"
    - "suche [text] auf [url]"
    - "gehe zu [url]"
    - "logge ein auf [url] mit [user]/[pass]"
    
    Returns:
        Dict mit 'success', 'text' und optional 'data'
    """
    
    gateway = get_web_gateway(headless=False)
    
    try:
        result = await gateway.execute(command)
        
        if result["success"]:
            return {
                "success": True,
                "text": _format_success_response(result),
                "data": {
                    "results": result.get("results", []),
                    "count": result.get("result_count", 0),
                    "url": result.get("url"),
                    "actions": result.get("actions_taken", 0)
                }
            }
        else:
            return {
                "success": False,
                "text": f"❌ Web-Kommando fehlgeschlagen: {result.get('error', 'Unbekannter Fehler')}",
                "error": result.get("error")
            }
            
    except Exception as e:
        logger.error(f"Web-Kommando Fehler: {e}")
        return {
            "success": False,
            "text": f"❌ Fehler bei Web-Ausführung: {str(e)}",
            "error": str(e)
        }


def _format_success_response(result: Dict) -> str:
    """Formatiert eine erfolgreiche Antwort"""
    
    results = result.get("results", [])
    count = result.get("result_count", 0)
    url = result.get("url", "")
    
    if count == 0:
        return f"🔍 Keine Ergebnisse gefunden auf {url}"
    
    response = f"🔍 **{count} Suchergebnisse** von {url}\n\n"
    
    for i, item in enumerate(results[:5]):
        # Extrahiere Titel (erste Zeile)
        lines = item.split('\n')
        title = lines[0].strip() if lines else "Unbekannt"
        
        # Extrahiere Beschreibung (nächste 1-2 Zeilen)
        description = ""
        if len(lines) > 1:
            desc_lines = []
            for line in lines[1:3]:
                if line.strip() and not line.startswith("http"):
                    desc_lines.append(line.strip())
            description = " ".join(desc_lines)
        
        response += f"**{i+1}. {title[:80]}**\n"
        if description:
            response += f"   {description[:120]}\n"
        response += "\n"
    
    if count > 5:
        response += f"*... und {count - 5} weitere Ergebnisse*"
    
    return response


async def shutdown_web_agent():
    """Schließt den Web-Agenten beim Gateway-Shutdown"""
    global _web_gateway
    if _web_gateway:
        await _web_gateway.close()
        _web_gateway = None