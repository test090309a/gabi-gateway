# gateway/integrations/smart_som_agent.py
"""Intelligenter SoM Agent mit Volltext-Extraktion für komplexe Fragen"""

import logging
import asyncio
from datetime import datetime
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
    position: int
    source: str
    snippet: str = ""           # Default-Werte NACH position
    full_content: str = ""      # Default-Werte NACH position
    confidence: float = 1.0     # Default-Werte NACH position


class SmartSoMAgent:
    
    def __init__(self, headless: bool = False, keep_alive: bool = True):
        self.headless = headless
        self.keep_alive = keep_alive
        self.web = None
        self.results = []
        self.thinking_steps = []
        self.is_browser_active = False
        self.cache: Dict[str, Dict] = {}
        self.cache_ttl = 300
        logger.info(f"SmartSoMAgent initialized")
    
    async def _init_web(self):
        if self.is_browser_active and self.keep_alive and self.web and self.web.driver:
            try:
                self.web.driver.current_url
                return True
            except:
                logger.warning("Browser session died, reinitializing...")
                self.is_browser_active = False
                if self.web:
                    try:
                        self.web.close()
                    except:
                        pass
                    self.web = None
        
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
        except Exception as e:
            logger.error(f"Web init error: {e}")
        
        return False
    
    async def _handle_cookie_consent(self):
        try:
            self.web.driver.execute_script("""
                document.querySelectorAll('button').forEach(btn => {
                    let text = btn.innerText.toLowerCase();
                    if(text.includes('accept') || text.includes('ok') || 
                       text.includes('allow') || text.includes('akzeptieren')) {
                        btn.click();
                    }
                });
            """)
            await asyncio.sleep(0.3)
        except:
            pass
    
    async def _find_search_input(self) -> Optional[Any]:
        search_selectors = [
            "input[name='q']",
            "#search_form_input_homepage",
            "input[type='text']"
        ]
        
        for selector in search_selectors:
            try:
                element = WebDriverWait(self.web.driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if element.is_displayed() and element.is_enabled():
                    logger.info(f"✅ Found search input")
                    return element
            except:
                continue
        
        return None
    
    async def _extract_results(self) -> List[SearchResult]:
        """Extrahiert Ergebnisse von DuckDuckGo"""
        results = []
        
        elements = self.web.driver.find_elements(By.CSS_SELECTOR, "article[data-testid='result']")
        
        if not elements:
            elements = self.web.driver.find_elements(By.CSS_SELECTOR, "li[data-layout='organic']")
        
        logger.info(f"Found {len(elements)} result elements")
        
        for idx, elem in enumerate(elements[:10], 1):
            try:
                title_elem = elem.find_element(By.CSS_SELECTOR, "h2")
                title = title_elem.text.strip()
                
                # URL aus dem Link im h2
                url = ""
                try:
                    link_elem = title_elem.find_element(By.TAG_NAME, "a")
                    url = link_elem.get_attribute("href") or ""
                except:
                    all_links = elem.find_elements(By.CSS_SELECTOR, "a[href]")
                    for link in all_links:
                        href = link.get_attribute("href") or ""
                        if href and "duckduckgo.com" not in href:
                            url = href
                            break
                
                if not url:
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
                    full_content="",  # Wird später gefüllt
                    position=idx,
                    source="ddg",
                    confidence=0.9
                ))
                
            except Exception as e:
                logger.debug(f"Extract error: {e}")
                continue
        
        logger.info(f"✅ Extracted {len(results)} results")
        return results
    
    # ===== NEU: VOLLTEXT-EXTRAKTION =====
    
    async def _extract_full_content(self, url: str, timeout: int = 10) -> str:
        """Öffnet eine URL und extrahiert den vollständigen Text"""
        if not self.web or not self.web.driver:
            return ""
        
        try:
            # Aktuelle URL speichern
            current_url = self.web.driver.current_url
            
            # Zur Ziel-URL navigieren
            logger.info(f"📖 Extracting content from: {url[:80]}...")
            self.web.driver.get(url)
            
            # Warte auf Body
            try:
                WebDriverWait(self.web.driver, timeout).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                logger.warning(f"Timeout loading {url}")
                return ""
            
            await asyncio.sleep(1)
            
            # Text extrahieren
            body = self.web.driver.find_element(By.TAG_NAME, "body")
            
            # Versuche, irrelevante Elemente zu entfernen
            for script in body.find_elements(By.TAG_NAME, "script"):
                self.web.driver.execute_script("arguments[0].remove();", script)
            for style in body.find_elements(By.TAG_NAME, "style"):
                self.web.driver.execute_script("arguments[0].remove();", style)
            for nav in body.find_elements(By.TAG_NAME, "nav"):
                self.web.driver.execute_script("arguments[0].remove();", nav)
            for footer in body.find_elements(By.TAG_NAME, "footer"):
                self.web.driver.execute_script("arguments[0].remove();", footer)
            
            text = body.text.strip()
            
            # Zurück zur ursprünglichen Seite
            self.web.driver.get(current_url)
            await asyncio.sleep(0.5)
            
            # Text bereinigen
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            cleaned = '\n'.join(lines[:100])  # Max 100 Zeilen
            
            logger.info(f"✅ Extracted {len(cleaned)} chars from {url[:50]}...")
            return cleaned[:5000]  # Max 5000 Zeichen
            
        except Exception as e:
            logger.error(f"Content extraction error for {url}: {e}")
            return ""
    
    async def _enrich_with_full_content(self, results: List[SearchResult], max_links: int = 3) -> List[SearchResult]:
        """Erweitert die Ergebnisse mit vollständigem Inhalt der ersten N Links"""
        if not results:
            return results
        
        enriched = []
        for i, res in enumerate(results):
            if i < max_links:
                logger.info(f"📖 Fetching full content for result {i+1}: {res.title[:50]}...")
                full_content = await self._extract_full_content(res.url)
                res.full_content = full_content
                enriched.append(res)
            else:
                enriched.append(res)
        
        return enriched
    
    # ===== NEU: KOMPLEXITÄTSERKENNUNG =====
    
    def _is_complex_query(self, query: str) -> bool:
        """Erkennt ob eine Frage komplex ist und Volltext benötigt"""
        query_lower = query.lower()
        
        # Komplexe Frage-Indikatoren
        complex_indicators = [
            "was ist", "wer ist", "erkläre", "bedeutung", "definition",
            "wie funktioniert", "wie wird", "geschichte", "hintergrund",
            "unterschied", "vergleich", "analyse", "zusammenfassung"
        ]
        
        # Länge und Komplexität
        is_long = len(query.split()) > 5
        has_question = "?" in query
        has_complex_word = any(ind in query_lower for ind in complex_indicators)
        
        return is_long or has_complex_word or has_question
    
    # ===== HAUPTH METHODE =====
    
    async def search(self, query: str, use_full_content: bool = None) -> List[SearchResult]:
        """Hauptmethode: Sucht nach einem Begriff"""
        self.thinking_steps = []
        self.results = []
        
        if use_full_content is None:
            use_full_content = self._is_complex_query(query)
            logger.info(f"Query: {'complex' if use_full_content else 'simple'} -> {'full content' if use_full_content else 'snippets'}")
        
        try:
            if not await self._init_web():
                return []
            
            if not self.web or not self.web.driver:
                return []
            
            # Cache prüfen
            cache_key = f"ddg:{query.lower()}"
            if cache_key in self.cache:
                cached = self.cache[cache_key]
                if (datetime.now() - cached["time"]).seconds < self.cache_ttl:
                    logger.info(f"⚡ Cache hit")
                    return cached["results"]
            
            # ===== FIX: IMMER ZUR STARTSEITE NAVIGIEREN =====
            logger.info(f"🌐 Navigating to DuckDuckGo homepage for fresh search...")
            self.web.driver.get("https://duckduckgo.com")
            await asyncio.sleep(0.5)
            
            # Cookie-Banner akzeptieren
            await self._handle_cookie_consent()
            
            # Suchfeld finden
            search_input = await self._find_search_input()
            if not search_input:
                logger.warning("No search input found")
                return []
            
            # Suchbegriff eingeben und absenden
            search_input.clear()
            search_input.send_keys(query)
            search_input.submit()
            self.thinking_steps.append({"text": f"Searching: {query}", "icon": "fa-search"})
            
            # Warte auf Ergebnisse
            try:
                WebDriverWait(self.web.driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article[data-testid='result']"))
                )
                logger.info(f"✅ Results loaded")
            except TimeoutException:
                logger.warning("Timeout waiting for results")
                return []
            
            # Ergebnisse extrahieren
            self.results = await self._extract_results()
            
            if use_full_content and self.results:
                self.thinking_steps.append({"text": "Extracting full content from top results...", "icon": "fa-download"})
                self.results = await self._enrich_with_full_content(self.results, max_links=3)
                logger.info(f"✅ Enriched {min(3, len(self.results))} results")
            
            if self.results:
                self.cache[cache_key] = {"time": datetime.now(), "results": self.results}
                logger.info(f"✅ Found {len(self.results)} results")
            else:
                logger.warning(f"No results found for '{query}'")
            
            return self.results
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    # ===== FORMATTING =====
    
    def format_results_markdown(self, max_results: int = 10, include_full_content: bool = False) -> str:
        """Formatiert Ergebnisse als Markdown"""
        if not self.results:
            return "🔍 **Keine Ergebnisse gefunden.**"
        
        lines = [f"## 🔍 Suchergebnisse\n"]
        
        for r in self.results[:max_results]:
            lines.append(f"### {r.position}. {r.title}")
            lines.append(f"🔗 [{r.url}]({r.url})")
            if r.snippet:
                lines.append(f"📝 {r.snippet}")
            if include_full_content and r.full_content:
                lines.append(f"\n<details>\n<summary>📖 Vollständiger Inhalt</summary>\n\n{r.full_content[:2000]}\n\n</details>")
            lines.append("")
        
        lines.append("---")
        lines.append(f"*{len(self.results)} Ergebnisse • Quelle: DuckDuckGo*")
        
        return "\n".join(lines)
    
    def format_for_llm(self, max_results: int = 5) -> str:
        """Formatiert Ergebnisse für LLM-Analyse (mit Volltext bei komplexen Fragen)"""
        if not self.results:
            return "Keine Suchergebnisse verfügbar."
        
        context = ""
        for i, r in enumerate(self.results[:max_results], 1):
            context += f"""
[QUELLE {i}]
Titel: {r.title}
URL: {r.url}
Auszug: {r.snippet}
"""
            if r.full_content:
                context += f"""
VOLLSTÄNDIGER INHALT:
{r.full_content[:3000]}
"""
            context += "---\n"
        
        return context
    
    def get_thinking_steps(self) -> List[Dict[str, str]]:
        return self.thinking_steps


_smart_agent = None

def get_smart_agent(headless: bool = False, keep_alive: bool = True) -> SmartSoMAgent:
    global _smart_agent
    if _smart_agent is None:
        _smart_agent = SmartSoMAgent(headless=headless, keep_alive=keep_alive)
    return _smart_agent