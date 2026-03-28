# integrations/web_automation.py
"""Web automation with Selenium."""

import logging
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not installed. Web automation disabled.")


class WebAutomation:
    """Web automation with Selenium."""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self._init_driver()
    
    def _init_driver(self):
        """Initialize Chrome driver with better emulation."""
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not available")
            return
        
        try:
            options = Options()
            
            # Headless mode (optional)
            if self.headless:
                options.add_argument('--headless=new')
            
            # Wichtig: Bessere User-Agent und Emulation
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            # ===== WICHTIG: BESSERER USER-AGENT =====
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Entferne WebDriver-Spuren
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # Sprache
            options.add_argument('--lang=de')
            
            self.driver = webdriver.Chrome(options=options)
            
            if self.driver:
                # Entferne webdriver property nach dem Start
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                self.driver.set_page_load_timeout(60)
                self.driver.implicitly_wait(10)
                logger.info(f"✅ Web driver initialized (headless={self.headless})")
            else:
                logger.error("Driver creation failed")
                
        except Exception as e:
            logger.error(f"Failed to initialize web driver: {e}")
            self.driver = None
    
    async def goto(self, url: str, wait_seconds: int = 3) -> Dict[str, Any]:
        """Navigate to URL."""
        if not self.driver:
            return {"success": False, "error": "Driver not initialized"}
        
        try:
            logger.info(f"🌐 Navigating to: {url}")
            self.driver.get(url)
            
            # Warte auf Page Load
            await asyncio.sleep(wait_seconds)
            
            # Optional: Warte auf Body
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except:
                pass
            
            # Take screenshot
            screenshot = await self._take_screenshot()
            
            return {
                "success": True,
                "title": self.driver.title,
                "url": self.driver.current_url,
                "screenshot": screenshot,
                "html": self.driver.page_source[:10000]
            }
        except Exception as e:
            logger.error(f"Web goto error: {e}")
            return {"success": False, "error": str(e)}
    
    async def click(self, selector: str) -> Dict[str, Any]:
        """Click element by selector."""
        if not self.driver:
            return {"success": False, "error": "Driver not initialized"}
        
        try:
            element = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            element.click()
            await asyncio.sleep(1)
            
            screenshot = await self._take_screenshot()
            return {"success": True, "screenshot": screenshot}
        except TimeoutException:
            return {"success": False, "error": f"Element not found or not clickable: {selector}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        """Type text into input field."""
        if not self.driver:
            return {"success": False, "error": "Driver not initialized"}
        
        try:
            element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            element.clear()
            element.send_keys(text)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _take_screenshot(self) -> Dict[str, Any]:
        """Take screenshot and return as base64."""
        if not self.driver:
            return {}
        
        try:
            import base64
            screenshot = self.driver.get_screenshot_as_png()
            return {
                "base64": base64.b64encode(screenshot).decode('utf-8'),
                "size": len(screenshot)
            }
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return {}
    
    def close(self):
        """Close the driver."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.debug(f"Error closing driver: {e}")
            finally:
                self.driver = None
            logger.info("Web driver closed")


_web_automation = None


def get_web_automation(headless: bool = True) -> WebAutomation:
    """Get or create web automation instance."""
    global _web_automation
    
    # Wenn headless-Modus wechselt, neue Instanz erstellen
    if _web_automation is not None and _web_automation.headless != headless:
        logger.info(f"Switching headless mode: {_web_automation.headless} -> {headless}")
        _web_automation.close()
        _web_automation = None
    
    if _web_automation is None:
        _web_automation = WebAutomation(headless=headless)
    
    return _web_automation


def reset_web_automation():
    """Reset web automation instance."""
    global _web_automation
    if _web_automation:
        _web_automation.close()
    _web_automation = None
    logger.info("Web automation reset")