# gateway/web_agent.py
"""Web-Agent Integration für GABI Gateway"""

import asyncio
import logging
import base64
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger("GABI.web_agent")

# Globale Agent-Instanz
_web_agent = None

def get_web_agent(headless: bool = True):
    """Singleton für den Web-Agent"""
    global _web_agent
    if _web_agent is None:
        from gateway.integrations.universal_web_agent import get_universal_agent
        _web_agent = get_universal_agent(headless=headless)
    return _web_agent


class WebAgentService:
    """Service für Web-Automation im GABI Gateway"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.agent = None
    
    async def initialize(self):
        """Initialisiert den Agenten"""
        self.agent = get_web_agent(headless=self.headless)
        logger.info("Web-Agent Service initialisiert")
    
    async def execute(self, command: str) -> Dict[str, Any]:
        """
        Führt einen Web-Befehl aus
        Unterstützte Befehle:
        - "suche nach [text] auf [url]"
        - "gehe zu [url] und [aktion]"
        - "logge ein auf [url] mit [user]/[pass]"
        - "extrahiere [daten] von [url]"
        """
        
        if not self.agent:
            await self.initialize()
        
        # Befehl parsen
        parsed = self._parse_command(command)
        
        if not parsed:
            return {
                "success": False,
                "error": "Befehl nicht verstanden. Beispiele: 'suche nach Wetter auf google.com', 'logge ein auf example.com mit user/pass'"
            }
        
        try:
            # Agent ausführen
            result = await self.agent.navigate(
                url=parsed["url"],
                goal=parsed["goal"],
                max_attempts=3
            )
            
            # Screenshot speichern (optional)
            if result.get("final_screenshot_base64"):
                screenshot_path = Path("screenshots") / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                screenshot_path.parent.mkdir(exist_ok=True)
                screenshot_path.write_bytes(base64.b64decode(result["final_screenshot_base64"]))
                result["screenshot_path"] = str(screenshot_path)
            
            return result
            
        except Exception as e:
            logger.error(f"Web-Agent Fehler: {e}")
            return {"success": False, "error": str(e)}
    
    def _parse_command(self, command: str) -> Optional[Dict]:
        """Parst natürliche Sprachbefehle"""
        cmd_lower = command.lower()
        
        # Suche nach "suche nach X auf Y"
        if "suche nach" in cmd_lower and "auf" in cmd_lower:
            search_term = cmd_lower.split("suche nach")[1].split("auf")[0].strip()
            url_part = cmd_lower.split("auf")[1].strip()
            
            # URL normalisieren
            if not url_part.startswith("http"):
                url_part = "https://" + url_part
            
            return {
                "url": url_part,
                "goal": f"Suche nach '{search_term}'"
            }
        
        # Login-Befehl: "logge ein auf X mit user/pass"
        if "logge ein" in cmd_lower or "einloggen" in cmd_lower:
            # Extrahiere URL
            if "auf" in cmd_lower:
                url_part = cmd_lower.split("auf")[1].split("mit")[0].strip()
                if not url_part.startswith("http"):
                    url_part = "https://" + url_part
                
                # Extrahiere Credentials
                credentials = ""
                if "mit" in cmd_lower:
                    credentials = cmd_lower.split("mit")[1].strip()
                
                return {
                    "url": url_part,
                    "goal": f"Logge dich ein mit {credentials}"
                }
        
        # Extraktions-Befehl
        if "extrahiere" in cmd_lower or "hole" in cmd_lower:
            # Extrahiere URL
            if "von" in cmd_lower:
                url_part = cmd_lower.split("von")[1].strip()
                if not url_part.startswith("http"):
                    url_part = "https://" + url_part
                
                return {
                    "url": url_part,
                    "goal": command
                }
        
        # Generische Navigation
        if "gehe zu" in cmd_lower:
            url_part = cmd_lower.split("gehe zu")[1].strip()
            if not url_part.startswith("http"):
                url_part = "https://" + url_part
            
            return {
                "url": url_part,
                "goal": command
            }
        
        return None
    
    async def close(self):
        """Schließt den Agenten"""
        if self.agent:
            await self.agent.close()


# Globale Service-Instanz
_web_service: Optional[WebAgentService] = None

def get_web_service(headless: bool = True) -> WebAgentService:
    """Singleton für den Web-Agent Service"""
    global _web_service
    if _web_service is None:
        _web_service = WebAgentService(headless=headless)
    return _web_service