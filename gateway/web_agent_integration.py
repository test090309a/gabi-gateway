# gateway/web_agent_integration.py
"""Integration des Universal Web Agents in GABI Gateway"""

import asyncio
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger("GABI.web_integration")

class WebAgentGateway:
    """
    Verbindet den Universal Web Agent mit GABI Gateway
    """
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.agent = None
        self._initialized = False
    
    async def initialize(self):
        """Initialisiert den Agenten"""
        if not self._initialized:
            from gateway.integrations.universal_web_agent import get_universal_agent
            self.agent = get_universal_agent(headless=self.headless)
            self._initialized = True
            logger.info("Web Agent Gateway initialisiert")
    
    async def execute(self, command: str) -> Dict[str, Any]:
        """
        Führt einen Web-Befehl aus.
        
        Unterstützte Befehle:
        - "suche nach [text] auf [url]"
        - "suche [text] auf [url]"
        - "gehe zu [url]"
        - "logge ein auf [url] mit [user]/[pass]"
        """
        
        await self.initialize()
        
        # Befehl parsen
        parsed = self._parse_command(command)
        
        if not parsed:
            return {
                "success": False,
                "error": "Befehl nicht verstanden. Beispiele: 'suche nach Python auf startpage.com'"
            }
        
        try:
            logger.info(f"📝 Führe aus: {parsed}")
            result = await self.agent.navigate(
                url=parsed["url"],
                goal=parsed["goal"],
                max_attempts=3
            )
            
            return self._format_result(result, parsed)
            
        except Exception as e:
            logger.error(f"Web-Agent Fehler: {e}", exc_info=True)
            return {"success": False, "error": str(e), "command": parsed}
    
    def _parse_command(self, command: str) -> Optional[Dict]:
        """Parst natürliche Sprachbefehle"""
        cmd_lower = command.lower()
        
        # Suche: "suche nach X auf Y"
        if "suche nach" in cmd_lower and "auf" in cmd_lower:
            search_term = cmd_lower.split("suche nach")[1].split("auf")[0].strip()
            url_part = cmd_lower.split("auf")[1].strip()
            
            # Entferne Anführungszeichen
            search_term = search_term.strip("'\"")
            url_part = url_part.strip("'\"")
            
            if not url_part.startswith("http"):
                url_part = "https://" + url_part
            
            return {
                "url": url_part,
                "goal": f"Suche nach '{search_term}'. Extrahiere die Suchergebnisse."
            }
        
        # Suche: "suche X auf Y"
        if cmd_lower.startswith("suche ") and " auf " in cmd_lower:
            parts = cmd_lower.split(" auf ")
            search_term = parts[0].replace("suche ", "").strip()
            url_part = parts[1].strip()
            
            search_term = search_term.strip("'\"")
            url_part = url_part.strip("'\"")
            
            if not url_part.startswith("http"):
                url_part = "https://" + url_part
            
            return {
                "url": url_part,
                "goal": f"Suche nach '{search_term}'. Extrahiere die Suchergebnisse."
            }
        
        # Navigation: "gehe zu Y"
        if cmd_lower.startswith("gehe zu "):
            url_part = cmd_lower.replace("gehe zu ", "").strip()
            url_part = url_part.strip("'\"")
            
            if not url_part.startswith("http"):
                url_part = "https://" + url_part
            
            return {
                "url": url_part,
                "goal": "Öffne die Seite"
            }
        
        # Login
        if "logge ein" in cmd_lower and "auf" in cmd_lower and "mit" in cmd_lower:
            url_part = cmd_lower.split("auf")[1].split("mit")[0].strip()
            credentials = cmd_lower.split("mit")[1].strip()
            
            url_part = url_part.strip("'\"")
            
            if not url_part.startswith("http"):
                url_part = "https://" + url_part
            
            return {
                "url": url_part,
                "goal": f"Logge dich ein mit {credentials}"
            }
        
        return None
    
    def _format_result(self, result: Dict, parsed: Dict) -> Dict:
        """Formatiert das Ergebnis für GABI Gateway"""
        
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Unbekannter Fehler"),
                "command": parsed,
                "actions_taken": result.get("actions_taken", 0)
            }
        
        # Extrahiere Daten
        extracted_data = result.get("extracted_data", [])
        search_results = []
        
        for data in extracted_data:
            if isinstance(data, dict):
                if "data" in data:
                    if isinstance(data["data"], list):
                        for item in data["data"]:
                            if item and len(str(item)) > 5:
                                search_results.append(str(item)[:300])
                    else:
                        search_results.append(str(data["data"])[:300])
                elif "results" in data:
                    for item in data["results"]:
                        if item and len(str(item)) > 5:
                            search_results.append(str(item)[:300])
            elif isinstance(data, list):
                for item in data:
                    if item and len(str(item)) > 5:
                        search_results.append(str(item)[:300])
            elif isinstance(data, str) and len(data) > 5:
                search_results.append(data[:300])
        
        # Entferne Duplikate und begrenze
        seen = set()
        unique_results = []
        for r in search_results:
            if r not in seen:
                seen.add(r)
                unique_results.append(r)
        
        url = result.get("url", parsed.get("url", ""))
        
        return {
            "success": True,
            "command": parsed,
            "url": url,
            "actions_taken": result.get("actions_taken", 0),
            "results": unique_results[:10],
            "result_count": len(unique_results),
            "raw_data": extracted_data[:3]  # Nur erste 3 für Debug
        }
    
    async def close(self):
        """Schließt den Agenten"""
        if self.agent:
            await self.agent.close()


# Singleton
_web_gateway: Optional[WebAgentGateway] = None

def get_web_gateway(headless: bool = True) -> WebAgentGateway:
    """Singleton für Web Agent Gateway"""
    global _web_gateway
    if _web_gateway is None:
        _web_gateway = WebAgentGateway(headless=headless)
    return _web_gateway