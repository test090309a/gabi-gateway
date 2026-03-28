# gateway/integrations/smart_som_agent.py
"""Intelligenter SoM Agent - Komplette, lauffähige Version mit dynamischer Ergebnis-Extraktion"""

import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Ein strukturiertes Suchergebnis"""
    title: str
    url: str
    snippet: str
    position: int
    source: str
    confidence: float = 1.0


class SmartSoMAgent:
    """Intelligenter SoM Agent - optimiert für DuckDuckGo mit dynamischer Ergebnis-Extraktion"""
    
    def __init__(self, headless: bool = False, keep_alive: bool = True):
        """
        Args:
            headless: Ob Browser unsichtbar sein soll (False = sichtbar für CAPTCHA)
            keep_alive: Browser zwischen Suchen offen halten (für Geschwindigkeit)
        """
        self.headless = headless
        self.keep_alive = keep_alive
        self.web = None
        self.results = []
        self.thinking_steps = []
        self.is_browser_active = False
        
        # Cache für wiederholte Suchen
        self.cache: Dict[str, Dict] = {}
        self.cache_ttl = 300  # 5 Minuten Cache
        
        logger.info(f"SmartSoMAgent initialized (headless={headless}, keep_alive={keep_alive})")
    
    # ==================== WEB INITIALIZATION ====================
    
    async def _init_web(self):
        """Initialisiert Web-Automation - mit Reset wenn nötig"""
        # Wenn Browser aktiv und wir ihn behalten wollen
        if self.is_browser_active and self.keep_alive and self.web and self.web.driver:
            # Prüfe ob Browser noch lebt
            try:
                self.web.driver.current_url
                return True
            except:
                logger.warning("Browser session died, reinitializing...")
                self.is_browser_active = False
                self.web = None
        
        # Schließe alten Browser falls vorhanden
        if self.web:
            try:
                self.web.close()
            except:
                pass
            self.web = None
        
        try:
            from gateway.integrations.web_automation import get_web_automation
            self.web = get_web_automation(headless=self.headless)
            
            if self.web and self.web.driver:
                self.web.driver.set_page_load_timeout(15)
                self.web.driver.implicitly_wait(3)
                self.is_browser_active = True
                logger.info(f"✅ Web driver ready")
                return True
            else:
                logger.error("Web driver is None")
                return False
                
        except Exception as e:
            logger.error(f"Web init error: {e}")
            return False
    
    # ==================== COOKIE HANDLING ====================
    
    async def _handle_cookie_consent(self):
        """Akzeptiert Cookie-Banner automatisch"""
        from selenium.webdriver.common.by import By
        
        cookie_selectors = [
            "button[aria-label='Accept cookies']",
            "button:contains('Accept')",
            "button:contains('OK')",
            "button:contains('Allow')",
            "button:contains('Akzeptieren')",
            "button:contains('Zustimmen')",
            "button[id*='accept']",
            "button[class*='accept']",
            ".cookie-consent button"
        ]
        
        for selector in cookie_selectors:
            try:
                buttons = self.web.driver.find_elements(By.CSS_SELECTOR, selector)
                for btn in buttons:
                    if btn.is_displayed():
                        btn.click()
                        logger.info(f"🍪 Accepted cookies via: {selector}")
                        await asyncio.sleep(0.5)
                        return True
            except:
                continue
        
        return False
    
    # ==================== SEARCH FIELD DETECTION ====================
    
    async def _find_search_input(self) -> Optional[Any]:
        """Findet das Suchfeld automatisch"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        search_selectors = [
            "input[name='q']",           # DuckDuckGo, Google
            "#search_form_input_homepage", # DuckDuckGo
            "#q",                        # Startpage
            "input[type='text']",        # Allgemein
            "input[type='search']"       # Allgemein
        ]
        
        for selector in search_selectors:
            try:
                element = WebDriverWait(self.web.driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if element.is_displayed() and element.is_enabled():
                    logger.info(f"✅ Found search input: {selector}")
                    return element
            except:
                continue
        
        return None
    
    # ==================== RESULT EXTRACTION ====================
    
    async def _extract_results(self) -> List[SearchResult]:
        """Korrigierte Extraktion – nimmt den Link aus dem Titel"""
        from selenium.webdriver.common.by import By
        
        results = []
        
        elements = self.web.driver.find_elements(By.CSS_SELECTOR, "article[data-testid='result']")
        
        if not elements:
            elements = self.web.driver.find_elements(By.CSS_SELECTOR, "li[data-layout='organic']")
        
        logger.info(f"Found {len(elements)} result elements")
        
        for idx, elem in enumerate(elements[:10], 1):
            try:
                # Titel aus h2
                title_elem = elem.find_element(By.CSS_SELECTOR, "h2")
                title = title_elem.text.strip()
                
                # ===== WICHTIG: URL aus dem Link im h2 (das ist der echte Link) =====
                url = ""
                try:
                    # Der Link ist direkt im h2
                    link_elem = title_elem.find_element(By.TAG_NAME, "a")
                    url = link_elem.get_attribute("href") or ""
                    logger.info(f"Found URL in h2: {url[:80]}")
                except:
                    # Fallback: Alle Links durchsuchen, den ersten externen nehmen
                    all_links = elem.find_elements(By.CSS_SELECTOR, "a[href]")
                    for link in all_links:
                        href = link.get_attribute("href") or ""
                        if href and "duckduckgo.com" not in href:
                            url = href
                            logger.info(f"Found external URL in fallback: {url[:80]}")
                            break
                
                if not url:
                    logger.warning(f"No external URL found for element {idx}")
                    continue
                
                # Snippet
                snippet = ""
                try:
                    snippet_elem = elem.find_element(By.CSS_SELECTOR, "p")
                    snippet = snippet_elem.text.strip()[:200]
                except:
                    pass
                
                results.append(SearchResult(
                    title=title[:150],
                    url=url[:300],
                    snippet=snippet,
                    position=idx,
                    source="ddg",
                    confidence=0.9
                ))
                logger.info(f"✅ Added: {title[:50]} -> {url[:50]}...")
                
            except Exception as e:
                logger.debug(f"Extract error for element {idx}: {e}")
                continue
        
        logger.info(f"✅ Extracted {len(results)} results")
        return results
    
    # ==================== MAIN SEARCH METHOD ====================
    
    async def search(self, query: str) -> List[SearchResult]:
        """Hauptmethode: Sucht nach einem Begriff"""
        self.thinking_steps = []
        self.results = []
        
        try:
            # Web initialisieren (mit Reset wenn nötig)
            if not await self._init_web():
                logger.error("Web automation not available")
                return []
            
            if not self.web or not self.web.driver:
                logger.error("Web driver is None after init")
                return []
            
            # Cache prüfen
            cache_key = f"ddg:{query.lower()}"
            if cache_key in self.cache:
                cached = self.cache[cache_key]
                if (datetime.now() - cached["time"]).seconds < self.cache_ttl:
                    logger.info(f"⚡ Cache hit")
                    return cached["results"]
            
            logger.info(f"🌐 Loading DuckDuckGo...")
            self.web.driver.get("https://duckduckgo.com")
            await asyncio.sleep(0.5)
            
            await self._handle_cookie_consent()
            
            search_input = await self._find_search_input()
            if not search_input:
                logger.warning("No search input found")
                return []
            
            search_input.clear()
            search_input.send_keys(query)
            search_input.submit()
            self.thinking_steps.append({"text": f"Searching: {query}", "icon": "fa-search"})
            
            try:
                WebDriverWait(self.web.driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article[data-testid='result']"))
                )
                logger.info(f"✅ Results loaded")
            except TimeoutException:
                logger.warning("Timeout waiting for results")
                return []
            
            self.results = await self._extract_results()
            
            if self.results:
                self.cache[cache_key] = {"time": datetime.now(), "results": self.results}
                logger.info(f"✅ Found {len(self.results)} results")
            else:
                logger.warning(f"No results found for '{query}'")
            
            return self.results
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
        
        finally:
            # Browser nur schließen wenn keep_alive=False
            if not self.keep_alive and self.web:
                try:
                    self.web.close()
                    self.is_browser_active = False
                    logger.info("🧹 Browser closed")
                except:
                    pass
    
    # ==================== FORMATTING ====================
    
    def format_results_markdown(self, max_results: int = 10) -> str:
        """Formatiert Ergebnisse als schöne Markdown-Ausgabe"""
        if not self.results:
            return "🔍 **Keine Ergebnisse gefunden.**"
        
        lines = [f"## 🔍 Suchergebnisse\n"]
        
        for r in self.results[:max_results]:
            lines.append(f"### {r.position}. {r.title}")
            lines.append(f"🔗 [{r.url}]({r.url})")
            if r.snippet:
                lines.append(f"📝 {r.snippet}")
            lines.append("")
        
        lines.append("---")
        lines.append(f"*{len(self.results)} Ergebnisse • Quelle: DuckDuckGo*")
        
        return "\n".join(lines)
    
    def format_results_json(self) -> List[Dict[str, Any]]:
        """Gibt Ergebnisse als JSON zurück"""
        return [{"title": r.title, "url": r.url, "snippet": r.snippet, "position": r.position} 
                for r in self.results]
    
    def get_thinking_steps(self) -> List[Dict[str, str]]:
        """Gibt die Gedankenschritte zurück"""
        return self.thinking_steps
    
    def clear_cache(self):
        """Löscht den Cache"""
        self.cache.clear()
        logger.info("🗑️ Cache cleared")
    
    def close(self):
        """Schließt den Agent und den Browser"""
        if self.web:
            try:
                self.web.close()
                self.is_browser_active = False
                logger.info("🧹 Agent closed")
            except:
                pass


# ==================== SINGLETON ====================

_smart_agent = None


def get_smart_agent(headless: bool = False, keep_alive: bool = True) -> SmartSoMAgent:
    """Singleton für den SmartSoMAgent"""
    global _smart_agent
    if _smart_agent is None:
        _smart_agent = SmartSoMAgent(headless=headless, keep_alive=keep_alive)
    return _smart_agent


def reset_smart_agent():
    """Setzt den Agent zurück"""
    global _smart_agent
    if _smart_agent:
        _smart_agent.close()
    _smart_agent = None
    logger.info("SmartSoMAgent reset")