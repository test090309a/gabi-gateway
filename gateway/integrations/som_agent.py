# gateway/integrations/som_agent.py
"""Set-of-Mark (SoM) Agent for autonomous web navigation with VISION and Cookie Persistence."""

import json
import logging
import asyncio
import base64
import re
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SoMAgent:
    """Set-of-Mark Agent for autonomous web navigation with VISION and Cookie Persistence."""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.web = None
        self.memory_file = Path(__file__).parent / "som_memory.json"
        self.known_sites_file = Path(__file__).parent / "known_sites.json"
        self.cookie_file = Path(__file__).parent / "cookies.json"
        self.memory = self._load_memory()
        self.known_sites = self._load_known_sites()
        self.cookies = self._load_cookies()
        self.thinking_steps = []
        self.actions = []
    
    # ==================== LOAD/SAVE FUNCTIONS ====================
    
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
    
    def _load_known_sites(self) -> Dict[str, Any]:
        """Load known sites from JSON file."""
        if self.known_sites_file.exists():
            try:
                with open(self.known_sites_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Load known sites error: {e}")
        
        # Default known sites
        return {
            "startpage.com": {
                "input": "input[type='text']",
                "submit": None,
                "results": ".w-gl__result, .result"
            },
            "google.com": {
                "input": "input[name='q']",
                "submit": "input[name='btnK']",
                "results": "div.g"
            },
            "wikipedia.org": {
                "input": "input[name='search']",
                "submit": "button[type='submit']",
                "results": ".mw-search-result"
            },
            "github.com": {
                "input": "input[placeholder='Search GitHub']",
                "submit": None,
                "results": ".repo-list-item"
            },
            "youtube.com": {
                "input": "input[name='search_query']",
                "submit": "button#search-icon-legacy",
                "results": "ytd-video-renderer"
            }
        }
    
    def _save_known_sites(self):
        """Save known sites to file."""
        try:
            with open(self.known_sites_file, 'w', encoding='utf-8') as f:
                json.dump(self.known_sites, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ Known sites saved ({len(self.known_sites)} sites)")
        except Exception as e:
            logger.error(f"Save known sites error: {e}")
    
    def _load_cookies(self) -> Dict[str, Any]:
        """Load saved cookies per domain."""
        if self.cookie_file.exists():
            try:
                with open(self.cookie_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Remove expired cookies
                    now = datetime.now()
                    cleaned = {}
                    for domain, cookies in data.items():
                        valid_cookies = []
                        for cookie in cookies:
                            expires = cookie.get('expiry')
                            if expires:
                                expiry_date = datetime.fromtimestamp(expires)
                                if expiry_date > now:
                                    valid_cookies.append(cookie)
                            else:
                                valid_cookies.append(cookie)
                        if valid_cookies:
                            cleaned[domain] = valid_cookies
                    return cleaned
            except Exception as e:
                logger.error(f"Load cookies error: {e}")
        return {}
    
    def _save_cookies(self):
        """Save cookies to file."""
        try:
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                json.dump(self.cookies, f, indent=2, default=str)
            logger.info(f"✅ Cookies saved ({len(self.cookies)} domains)")
        except Exception as e:
            logger.error(f"Save cookies error: {e}")
    
    def _restore_cookies(self, domain: str):
        """Restore cookies for a domain."""
        if not self.web or not self.web.driver:
            return
        
        if domain in self.cookies:
            try:
                for cookie in self.cookies[domain]:
                    cookie_copy = {
                        'name': cookie['name'],
                        'value': cookie['value'],
                        'domain': cookie.get('domain', domain)
                    }
                    if cookie.get('path'):
                        cookie_copy['path'] = cookie['path']
                    if cookie.get('secure'):
                        cookie_copy['secure'] = cookie['secure']
                    if cookie.get('httpOnly'):
                        cookie_copy['httpOnly'] = cookie['httpOnly']
                    
                    self.web.driver.add_cookie(cookie_copy)
                
                logger.info(f"🍪 {len(self.cookies[domain])} cookies restored for {domain}")
            except Exception as e:
                logger.warning(f"Cookie restore failed: {e}")
    
    def _save_current_cookies(self, domain: str):
        """Save current cookies for a domain."""
        if not self.web or not self.web.driver:
            return
        
        try:
            cookies = self.web.driver.get_cookies()
            if cookies:
                self.cookies[domain] = cookies
                self._save_cookies()
                logger.info(f"🍪 {len(cookies)} cookies saved for {domain}")
        except Exception as e:
            logger.warning(f"Cookie save failed: {e}")
    
    # ==================== WEB INITIALIZATION ====================
    
    async def _init_web(self):
        """Initialize web automation."""
        if self.web is not None:
            return True
        
        try:
            from gateway.integrations.web_automation import get_web_automation
            self.web = get_web_automation(headless=self.headless)
            
            if self.web and self.web.driver:
                logger.info(f"✅ Web automation initialized (headless={self.headless})")
                return True
            else:
                logger.error("Web automation returned None or driver is None")
                return False
        except ImportError as e:
            logger.error(f"WebAutomation import error: {e}")
            return False
        except Exception as e:
            logger.error(f"WebAutomation init error: {e}")
            return False
    
    # ==================== VISION FUNCTIONS ====================
    
    async def _get_vision_model(self) -> Optional[str]:
        """Get best available vision model."""
        try:
            from gateway.ollama_client import ollama_client
            models_info = ollama_client.list_models()
            available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
            
            vision_hints = ["vl", "vision", "llava", "qwen2.5vl", "qwen3-vl", "moondream", "minicpm-v"]
            for hint in vision_hints:
                for model in available:
                    if hint in model.lower():
                        return model
            return None
        except Exception as e:
            logger.error(f"Get vision model error: {e}")
            return None
    
    async def _analyze_screenshot(self, screenshot_base64: str, prompt: str) -> str:
        """Analyze screenshot with vision model."""
        vision_model = await self._get_vision_model()
        if not vision_model:
            return '{"action": "wait", "target": "", "reasoning": "No vision model available"}'
        
        try:
            from gateway.ollama_client import ollama_client
            
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    ollama_client.chat,
                    model=vision_model,
                    messages=[{"role": "user", "content": prompt, "images": [screenshot_base64]}]
                ),
                timeout=45.0
            )
            return response.get("message", {}).get("content", "")
        except asyncio.TimeoutError:
            logger.error("Vision analysis timeout after 45 seconds")
            return '{"action": "wait", "target": "", "reasoning": "Vision timeout"}'
        except Exception as e:
            logger.error(f"Vision analysis error: {e}")
            return f'{{"action": "wait", "target": "", "reasoning": "Error: {e}"}}'
    
    async def _detect_captcha(self, screenshot_base64: str) -> bool:
        """Quick CAPTCHA detection."""
        prompt = "Is there a CAPTCHA on this page? Answer only YES or NO."
        
        try:
            response = await asyncio.wait_for(
                self._analyze_screenshot(screenshot_base64, prompt),
                timeout=5.0
            )
            return "YES" in response.upper()
        except:
            return False
    
    # ==================== HTML NAVIGATION (FAST) ====================
    
    async def _navigate_known_site(self, domain: str, url: str, goal: str) -> Dict[str, Any]:
        """HTML/CSS-based navigation for known sites."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, NoSuchElementException
        
        site_config = self.known_sites.get(domain, {})
        
        # Check if it's a search query
        if "suche nach" in goal.lower() or "search for" in goal.lower():
            search_term = re.sub(r'(?i)(suche nach|search for)\s*', '', goal).strip()
            
            if not search_term:
                search_term = goal.strip()
            
            logger.info(f"⚡ Fast search on {domain}: {search_term}")
            
            # ===== KORRIGIERT: Längere Wartezeit für das Suchfeld =====
            selectors = [
                "#q",
                "input[name='query']",
                "input[type='text']",
                ".search-form-input"
            ]
            
            search_input = None
            last_error = None
            
            for selector in selectors:
                try:
                    logger.info(f"🔍 Trying selector: {selector}")
                    # Wartezeit auf 10 Sekunden erhöht
                    search_input = WebDriverWait(self.web.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"✅ Found with selector: {selector}")
                    break
                except TimeoutException as e:
                    last_error = e
                    logger.debug(f"Selector {selector} timeout")
                    continue
                except Exception as e:
                    last_error = e
                    continue
            
            if not search_input:
                logger.warning(f"❌ Could not find search input on {domain}")
                return await self._navigate_vision(url, goal, 5)
            
            try:
                # Clear input
                logger.info("Clearing search input...")
                search_input.clear()
                await asyncio.sleep(0.5)
                
                # Type search term
                logger.info(f"Typing search term: {search_term}")
                search_input.send_keys(search_term)
                await asyncio.sleep(0.5)
                
                # Submit
                logger.info("Submitting search...")
                search_input.submit()
                logger.info("✅ Submitted with .submit()")
                
                # ===== WICHTIG: Längere Wartezeit für Ergebnisse =====
                logger.info("Waiting for results...")
                
                # Warte auf das Erscheinen von Ergebnis-Elementen
                try:
                    WebDriverWait(self.web.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".w-gl__result, .result, h3"))
                    )
                    logger.info("✅ Results detected")
                except TimeoutException:
                    logger.warning("Timeout waiting for results, but continuing...")
                
                # Extra Wartezeit für vollständiges Laden
                await asyncio.sleep(3)
                
                # Extract results
                logger.info("Extracting search results...")
                results = await self._extract_search_results_html(".w-gl__result")
                
                logger.info(f"✅ HTML search completed, {len(results)} results found")
                
                return {
                    "success": True,
                    "url": url,
                    "mode": "html",
                    "search_term": search_term,
                    "results": results[:10],
                    "extracted_content": {"search_results": results[:10]}
                }
                
            except Exception as e:
                logger.warning(f"HTML navigation failed: {e}")
                import traceback
                traceback.print_exc()
                return await self._navigate_vision(url, goal, 5)
        
        # Not a search goal, use vision
        return await self._navigate_vision(url, goal, 5)
    
    async def _extract_search_results_html(self, selector: str) -> List[Dict[str, Any]]:
        """Extract search results using HTML selectors."""
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException
        
        results = []
        
        # Warte etwas länger auf vollständiges Laden
        await asyncio.sleep(2)
        
        # Debug: Zeige die aktuelle URL
        current_url = self.web.driver.current_url
        logger.info(f"Current URL after search: {current_url}")
        
        # Startpage-spezifische Selektoren (nach der Suche)
        selectors_to_try = [
            ".w-gl__result",           # Startpage Haupt-Selector
            ".result",                 # Fallback
            "div[class*='result']",    # Jedes div mit 'result' in der Klasse
            "h3",                      # Überschriften
            "a[href*='http']"          # Links
        ]
        
        elements = []
        for sel in selectors_to_try:
            try:
                elements = self.web.driver.find_elements(By.CSS_SELECTOR, sel)
                if elements:
                    logger.info(f"✅ Found {len(elements)} elements with selector: {sel}")
                    # Zeige erstes Element als Beispiel
                    try:
                        sample = elements[0].text[:100] if elements[0].text else elements[0].get_attribute("outerHTML")[:100]
                        logger.info(f"   Sample: {sample}")
                    except:
                        pass
                    break
            except Exception as e:
                logger.debug(f"Selector {sel} error: {e}")
                continue
        
        if not elements:
            logger.warning("No result elements found with any selector")
            # Versuche die gesamte Seite zu loggen (für Debug)
            try:
                body_text = self.web.driver.find_element(By.TAG_NAME, "body").text[:500]
                logger.info(f"Page body preview: {body_text}")
            except:
                pass
            return results
        
        for elem in elements[:10]:
            try:
                # Titel extrahieren
                title = ""
                for tag in ["h3", ".w-gl__result__title", "a"]:
                    try:
                        te = elem.find_element(By.CSS_SELECTOR, tag) if tag != "h3" else elem if tag == "h3" else None
                        if tag == "h3":
                            te = elem
                        else:
                            te = elem.find_element(By.CSS_SELECTOR, tag)
                        title = te.text.strip()
                        if title:
                            break
                    except:
                        continue
                
                # URL extrahieren
                url = ""
                try:
                    link = elem.find_element(By.CSS_SELECTOR, "a")
                    url = link.get_attribute("href") or ""
                except:
                    pass
                
                # Snippet extrahieren
                snippet = ""
                for tag in [".w-gl__result__snippet", ".result__snippet", "p"]:
                    try:
                        se = elem.find_element(By.CSS_SELECTOR, tag)
                        snippet = se.text.strip()[:200]
                        if snippet:
                            break
                    except:
                        continue
                
                # Nur gültige Ergebnisse
                if title and url and "startpage" not in url.lower():
                    results.append({
                        "title": title[:100],
                        "url": url[:200],
                        "snippet": snippet
                    })
                    logger.debug(f"✅ Added: {title[:50]}...")
                    
            except Exception as e:
                logger.debug(f"Error extracting result: {e}")
                continue
        
        logger.info(f"✅ Extracted {len(results)} search results")
        return results
    
    # ==================== VISION NAVIGATION (SLOW BUT FLEXIBLE) ====================
    
    async def _navigate_vision(self, url: str, goal: str, max_steps: int) -> Dict[str, Any]:
        """Slow but flexible vision-based navigation."""
        logger.info(f"🐌 Vision mode activated for {url}")
        
        steps_taken = 0
        action_history = []
        extracted = {}
        
        while steps_taken < max_steps:
            steps_taken += 1
            
            if not self.web or not self.web.driver:
                logger.error("Web driver lost during navigation")
                break
            
            # Take screenshot
            screenshot = await self.web._take_screenshot()
            if not screenshot.get("base64"):
                logger.warning("No screenshot available")
                break
            
            # Analyze with vision
            analysis_prompt = f"""
            You are a web navigation agent. Current goal: {goal}
            
            Based on the screenshot, determine the next action.
            Choose ONE action from: click, type, scroll, wait, done
            
            Respond in JSON format:
            {{
                "action": "click|type|scroll|wait|done",
                "target": "element description or text to type",
                "reasoning": "why this action"
            }}
            """
            
            analysis = await asyncio.wait_for(
                self._analyze_screenshot(screenshot["base64"], analysis_prompt),
                timeout=45.0
            )
            
            # Parse action
            try:
                json_match = re.search(r'\{.*\}', analysis, re.DOTALL)
                if json_match:
                    action_data = json.loads(json_match.group())
                    action = action_data.get("action", "wait")
                    target = action_data.get("target", "")
                    reasoning = action_data.get("reasoning", "")
                    
                    action_history.append({
                        "step": steps_taken,
                        "action": action,
                        "target": target,
                        "reasoning": reasoning
                    })
                    
                    logger.info(f"🤖 Step {steps_taken}: {action} - {target[:50]}")
                    
                    # Execute action
                    if action == "click":
                        await asyncio.sleep(1)
                    
                    elif action == "type" and target:
                        await asyncio.sleep(1)
                    
                    elif action == "scroll" and self.web and self.web.driver:
                        try:
                            self.web.driver.execute_script("window.scrollBy(0, 500)")
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.warning(f"Scroll failed: {e}")
                    
                    elif action == "wait":
                        await asyncio.sleep(2)
                    
                    elif action == "done":
                        break
                    
            except Exception as e:
                logger.error(f"Parse action error: {e}")
                await asyncio.sleep(1)
        
        # Extract final content
        extracted = await self._extract_content()
        
        return {
            "success": True,
            "url": url,
            "mode": "vision",
            "steps_taken": steps_taken,
            "actions": action_history,
            "extracted_content": extracted
        }
    
    async def _extract_content(self) -> Dict[str, Any]:
        """Extract content from current page with timeouts."""
        if not self.web or not self.web.driver:
            return {}
        
        try:
            from selenium.webdriver.common.by import By
            
            async def extract():
                driver = self.web.driver
                
                try:
                    title = driver.title
                except:
                    title = ""
                
                text = ""
                try:
                    body = driver.find_element(By.TAG_NAME, "body")
                    text = body.text[:10000]
                except:
                    pass
                
                links = []
                try:
                    for a in driver.find_elements(By.TAG_NAME, "a")[:50]:
                        try:
                            href = a.get_attribute("href")
                            link_text = a.text
                            if href and href.startswith("http"):
                                links.append({"text": link_text[:50], "href": href[:200]})
                        except:
                            continue
                except:
                    pass
                
                # Extract search results
                search_results = []
                current_url = driver.current_url.lower()
                if "startpage" in current_url or "search" in current_url:
                    try:
                        selectors = [".w-gl__result", ".result", ".web-result"]
                        for selector in selectors:
                            elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            if elements:
                                for elem in elements[:10]:
                                    try:
                                        title_elem = elem.find_element(By.CSS_SELECTOR, "h3, .result__title, a")
                                        title = title_elem.text.strip()
                                        url = elem.find_element(By.CSS_SELECTOR, "a").get_attribute("href") or ""
                                        if title and url:
                                            search_results.append({"title": title[:100], "url": url[:200]})
                                    except:
                                        continue
                                break
                    except:
                        pass
                
                return {
                    "title": title[:200],
                    "text": text,
                    "links": links[:50],
                    "search_results": search_results[:10]
                }
            
            return await asyncio.wait_for(extract(), timeout=20.0)
            
        except asyncio.TimeoutError:
            logger.error("Extract content timeout after 20 seconds")
            return {"error": "Extraction timeout"}
        except Exception as e:
            logger.error(f"Extract content error: {e}")
            return {"error": str(e)}
    
    # ==================== MAIN NAVIGATION ====================
    
    async def navigate(self, url: str, goal: str, max_steps: int = 5) -> Dict[str, Any]:
        """Hybrid navigation with cookie persistence and auto-learning."""
        self.thinking_steps = []
        self.actions = []
        
        try:
            # Initialize web automation
            if not await self._init_web():
                return {"success": False, "error": "WebAutomation not available"}
            
            if not self.web or not self.web.driver:
                return {"success": False, "error": "Web driver not initialized"}
            
            # Parse domain
            domain = urlparse(url).netloc.lower().replace("www.", "")
            
            # Navigate to URL
            self.thinking_steps.append({"text": f"Navigating to {url}", "icon": "fa-globe"})
            logger.info(f"SoM Agent navigating to: {url}")
            
            result = await self.web.goto(url)
            
            if not result.get("success"):
                return {"success": False, "error": result.get("error")}
            
            # Restore cookies
            self._restore_cookies(domain)
            
            # Reload if cookies were restored
            if domain in self.cookies and self.cookies[domain]:
                logger.info("🍪 Reloading page with restored cookies...")
                await self.web.goto(url)
            
            # ===== KNOWN SITE? =====
            if domain in self.known_sites:
                logger.info(f"🏠 Known site: {domain} → HTML mode")
                nav_result = await self._navigate_known_site(domain, url, goal)
                
                if nav_result.get("success"):
                    self._save_current_cookies(domain)
                
                return nav_result
            
            # ===== CAPTCHA DETECTION =====
            screenshot = await self.web._take_screenshot()
            if screenshot.get("base64"):
                has_captcha = await self._detect_captcha(screenshot["base64"])
                if has_captcha:
                    logger.info(f"🔍 CAPTCHA detected → Vision mode")
                    nav_result = await self._navigate_vision(url, goal, max_steps)
                    if nav_result.get("success"):
                        self._save_current_cookies(domain)
                    return nav_result
            
            # ===== UNKNOWN SITE → USE VISION =====
            logger.info(f"🧠 Unknown site: {domain} → Vision mode")
            nav_result = await self._navigate_vision(url, goal, max_steps)
            
            if nav_result.get("success"):
                self._save_current_cookies(domain)
                
                # Try to learn selectors from successful vision navigation
                actions = nav_result.get("actions", [])
                for action in actions:
                    if action.get("action") == "type" and action.get("target"):
                        try:
                            from selenium.webdriver.common.by import By
                            active = self.web.driver.switch_to.active_element
                            if active:
                                elem_id = active.get_attribute("id")
                                elem_name = active.get_attribute("name")
                                elem_class = active.get_attribute("class")
                                
                                if elem_id:
                                    self.known_sites[domain] = {"input": f"#{elem_id}"}
                                elif elem_name:
                                    self.known_sites[domain] = {"input": f"input[name='{elem_name}']"}
                                elif elem_class:
                                    self.known_sites[domain] = {"input": f"input.{elem_class.split()[0]}"}
                                
                                if domain in self.known_sites:
                                    self._save_known_sites()
                                    logger.info(f"🎉 New site learned: {domain}")
                                break
                        except:
                            pass
            
            return nav_result
            
        except Exception as e:
            logger.error(f"SoM navigate error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
        
        finally:
            if self.web:
                try:
                    logger.info("🧹 Closing browser...")
                    self.web.close()
                    logger.info("✅ Browser closed")
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
    
    def close(self):
        """Close the agent and clean up."""
        if self.web:
            try:
                self.web.close()
            except:
                pass
        logger.info("SoM Agent closed")


# ==================== SINGLETON ====================

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