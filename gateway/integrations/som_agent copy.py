# gateway/integrations/som_agent.py
"""Set-of-Mark (SoM) Agent for autonomous web navigation."""

import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class SoMAgent:
    """Set-of-Mark Agent for autonomous web navigation."""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.web = None
        self.memory_file = Path(__file__).parent / "som_memory.json"
        self.memory = self._load_memory()
        self.thinking_steps = []
        self.actions = []
    
    def _load_memory(self) -> Dict[str, Any]:
        """Load memory from file."""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Load SoM memory error: {e}")
        return {"pages": {}, "learned_actions": []}
    
    def _save_memory(self):
        """Save memory to file."""
        try:
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(self.memory, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Save SoM memory error: {e}")
    
    async def _init_web(self):
        """Initialize web automation."""
        if self.web is not None:
            return True
        
        try:
            from gateway.integrations.web_automation import get_web_automation
            self.web = get_web_automation(headless=self.headless)
            return self.web is not None
        except ImportError as e:
            logger.error(f"WebAutomation import error: {e}")
            return False
        except Exception as e:
            logger.error(f"WebAutomation init error: {e}")
            return False
    
    async def navigate(self, url: str, goal: str, max_steps: int = 5) -> Dict[str, Any]:
        """Navigate to URL with a goal."""
        self.thinking_steps = []
        self.actions = []
        
        try:
            # Initialize web automation
            if not await self._init_web():
                return {"success": False, "error": "WebAutomation not available"}
            
            # Navigate to URL
            self.thinking_steps.append({"text": f"Navigating to {url}", "icon": "fa-globe"})
            logger.info(f"SoM Agent navigating to: {url}")
            
            result = await self.web.goto(url)
            
            if not result.get("success"):
                return {"success": False, "error": result.get("error")}
            
            # ===== FÜR STARTPAGE SUCHE =====
            if "startpage" in url.lower() and "suche nach" in goal.lower():
                import time
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                logger.info("🔍 Startpage erkannt - führe Suche aus...")
                
                # Extrahiere Suchbegriff aus goal
                search_term = goal.replace("Suche nach", "").replace("'", "").replace('"', "").strip()
                logger.info(f"🔍 Suchbegriff: {search_term}")
                
                # Korrigierter Selektor (basierend auf Debug)
                search_selectors = [
                    "input[type='text']",  # ← Der richtige Selektor!
                    "input[name='q']",
                    "input[type='search']",
                    "#q",
                    ".search-form-input"
                ]
                
                search_input = None
                for selector in search_selectors:
                    try:
                        search_input = WebDriverWait(self.web.driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        logger.info(f"✅ Suchfeld gefunden mit Selektor: {selector}")
                        break
                    except:
                        continue
                
                if search_input:
                    try:
                        # Suchbegriff eingeben
                        search_input.clear()
                        search_input.send_keys(search_term)
                        logger.info(f"📝 Suchbegriff eingegeben: {search_term}")
                        
                        # Suche absenden (Enter)
                        search_input.submit()
                        logger.info("⏎ Suche abgesendet")
                        
                        # Warte auf Ergebnisse mit intelligentem Timeout
                        import time
                        max_wait = 15  # Maximal 15 Sekunden warten
                        results_found = False
                        
                        for i in range(max_wait):
                            time.sleep(1)
                            # Prüfe ob Ergebnisse da sind
                            try:
                                page_source = self.web.driver.page_source
                                if "w-gl__result" in page_source or "result" in page_source or "w-gl__result__title" in page_source:
                                    logger.info(f"✅ Ergebnisse nach {i+1} Sekunden gefunden")
                                    results_found = True
                                    break
                                elif i == 5:  # Nach 5 Sekunden einmal kurz loggen
                                    logger.debug(f"⏳ Warte auf Ergebnisse... (5/{max_wait})")
                            except:
                                pass
                        
                        if not results_found:
                            logger.warning(f"⚠️ Keine Ergebnisse nach {max_wait} Sekunden gefunden")
                            # Optional: Screenshot für Debug
                            try:
                                self.web.driver.save_screenshot("debug_no_results.png")
                                logger.info("📸 Debug-Screenshot gespeichert: debug_no_results.png")
                            except:
                                pass
                        
                        logger.info("✅ Suche ausgeführt")
                        
                    except Exception as e:
                        logger.error(f"Suche fehlgeschlagen: {e}")
                else:
                    logger.error("❌ Kein Suchfeld gefunden!")
            
            # Extract content
            self.thinking_steps.append({"text": "Extracting content", "icon": "fa-download"})
            extracted = await self._extract_content()
            
            # Save to memory
            self.memory["pages"][url] = {
                "url": url,
                "goal": goal,
                "extracted_at": datetime.now().isoformat(),
                "content": extracted
            }
            
            self.memory["learned_actions"].append({
                "url": url,
                "goal": goal,
                "learned_at": datetime.now().isoformat(),
                "content": extracted
            })
            
            self._save_memory()
            
            return {
                "success": True,
                "url": url,
                "extracted_content": extracted,
                "steps_taken": len(self.actions),
                "thinking_steps": self.thinking_steps,
                "action_history": self.actions
            }
            
        except Exception as e:
            logger.error(f"SoM navigate error: {e}")
        return {"success": False, "error": str(e)}
    
    async def _extract_content(self) -> Dict[str, Any]:
        """Extract content from current page with timeout."""
        if not self.web or not self.web.driver:
            return {}
        
        try:
            # Timeout für die Extraktion
            import asyncio
            
            async def extract():
                driver = self.web.driver
                
                # Get title
                title = driver.title
                
                # Get main content
                try:
                    body = driver.find_element("tag name", "body")
                    text = body.text
                except:
                    text = ""
                
                # Get links
                links = []
                for a in driver.find_elements("tag name", "a")[:50]:
                    try:
                        href = a.get_attribute("href")
                        link_text = a.text
                        if href and href.startswith("http"):
                            links.append({"text": link_text[:50], "href": href})
                    except:
                        continue
                
                # Get headings
                headings = []
                for h in driver.find_elements("tag name", "h1")[:10]:
                    headings.append({"level": "h1", "text": h.text})
                for h in driver.find_elements("tag name", "h2")[:10]:
                    headings.append({"level": "h2", "text": h.text})
                
                # Check for search results
                search_results = []
                current_url = driver.current_url.lower()
                if "startpage" in current_url or "search" in current_url:
                    search_results = self._extract_search_results(driver)
                
                return {
                    "title": title,
                    "text": text[:10000],
                    "links": links[:50],
                    "headings": headings[:30],
                    "search_results": search_results
                }
            
            # Timeout nach 30 Sekunden
            return await asyncio.wait_for(extract(), timeout=30.0)
            
        except asyncio.TimeoutError:
            logger.error("Extract content timeout after 30 seconds")
            return {"error": "Extraction timeout"}
        except Exception as e:
            logger.error(f"Extract content error: {e}")
            return {"error": str(e)}
    
    def _extract_search_results(self, driver) -> List[Dict[str, Any]]:
        """Extract search results from Startpage - simplified version."""
        import time
        results = []
        
        try:
            # Kurze Wartezeit
            time.sleep(2)
            
            # Einfache Suche nach Links mit Titeln
            logger.info("🔍 Extrahiere Suchergebnisse...")
            
            # Methode 1: Suche nach Ergebnis-Containern
            selectors = [".w-gl__result", ".result", ".web-result"]
            result_elements = []
            
            for selector in selectors:
                try:
                    elements = driver.find_elements("css selector", selector)
                    if elements:
                        logger.info(f"Found {len(elements)} elements with {selector}")
                        result_elements = elements
                        break
                except:
                    continue
            
            # Methode 2: Wenn keine Container, nimm alle Links
            if not result_elements:
                logger.info("No result containers, using links...")
                links = driver.find_elements("css selector", "a")
                for link in links[:20]:
                    try:
                        title = link.text.strip()
                        url = link.get_attribute("href")
                        if title and url and len(title) > 10 and url.startswith("http"):
                            if not url.startswith(('/sp/', '/search', 'https://www.startpage.com')):
                                results.append({
                                    "title": title[:100],
                                    "url": url[:200],
                                    "snippet": ""
                                })
                    except:
                        continue
                return results[:10]
            
            # Extrahiere aus Ergebnissen
            for elem in result_elements[:10]:
                try:
                    # Titel
                    title = ""
                    for tag in ["h3", ".result__title", ".w-gl__result__title", "a"]:
                        try:
                            te = elem.find_element("css selector", tag)
                            title = te.text.strip()
                            if title:
                                break
                        except:
                            continue
                    
                    # URL
                    url = ""
                    try:
                        link = elem.find_element("css selector", "a")
                        url = link.get_attribute("href")
                    except:
                        pass
                    
                    # Snippet
                    snippet = ""
                    for tag in [".result__snippet", ".w-gl__result__snippet", ".s"]:
                        try:
                            se = elem.find_element("css selector", tag)
                            snippet = se.text.strip()
                            if snippet:
                                break
                        except:
                            continue
                    
                    if title and url and not url.startswith(('/sp/', '/search')):
                        results.append({
                            "title": title[:100],
                            "url": url[:200],
                            "snippet": snippet[:200] if snippet else ""
                        })
                except Exception:
                    continue
            
            logger.info(f"✅ Extracted {len(results)} search results")
            
        except Exception as e:
            logger.error(f"Extract error: {e}")
        
        return results[:10]
    
    def close(self):
        """Close the agent and clean up."""
        if self.web:
            try:
                self.web.close()
            except:
                pass
        logger.info("SoM Agent closed")


_som_agent = None
_som_agent_lock = asyncio.Lock()


async def get_som_agent(headless: bool = True, force_new: bool = False) -> SoMAgent:
    """Get or create SoM agent singleton."""
    global _som_agent
    async with _som_agent_lock:
        if force_new or _som_agent is None:
            if _som_agent:
                _som_agent.close()
            _som_agent = SoMAgent(headless=headless)
            logger.info(f"SoM Agent created (headless={headless})")
        return _som_agent


def reset_som_agent():
    """Reset the SoM agent."""
    global _som_agent
    if _som_agent:
        _som_agent.close()
    _som_agent = None
    logger.info("SoM Agent reset")