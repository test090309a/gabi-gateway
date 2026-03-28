# integrations/web_vision_agent.py
"""Web Vision Agent for autonomous navigation with vision."""

import logging
import asyncio
import base64
from datetime import datetime
from typing import Dict, Any, List, Optional

from gateway.config import config
from gateway.ollama_client import ollama_client

logger = logging.getLogger(__name__)


class WebVisionAgent:
    """Autonomous web agent using vision-language models."""
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.web = None
        self.thinking_steps = []
        self.action_history = []
    
    async def _init_web(self):
        """Initialize web automation."""
        from gateway.integrations.web_automation import get_web_automation
        self.web = get_web_automation(headless=self.headless)
    
    async def _get_vision_model(self) -> Optional[str]:
        """Get best available vision model."""
        models_info = ollama_client.list_models()
        available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
        
        vision_hints = ["vl", "vision", "llava", "qwen2.5vl", "qwen3-vl", "moondream", "minicpm-v"]
        for hint in vision_hints:
            for model in available:
                if hint in model.lower():
                    return model
        
        return None
    
    async def _analyze_screenshot(self, screenshot_base64: str, prompt: str) -> str:
        """Analyze screenshot with vision model."""
        vision_model = await self._get_vision_model()
        if not vision_model:
            return "No vision model available"
        
        try:
            response = await asyncio.to_thread(
                ollama_client.chat,
                model=vision_model,
                messages=[{"role": "user", "content": prompt, "images": [screenshot_base64]}]
            )
            return response.get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"Vision analysis error: {e}")
            return f"Error: {e}"
    
    async def analyze_and_navigate(self, url: str, goal: str, max_steps: int = 10) -> Dict[str, Any]:
        """Analyze page and navigate towards goal."""
        self.thinking_steps = []
        self.action_history = []
        
        if not self.web:
            await self._init_web()
        
        try:
            # Navigate to URL
            self.thinking_steps.append({"text": f"Navigating to {url}", "icon": "fa-globe"})
            result = await self.web.goto(url)
            
            if not result.get("success"):
                return {"success": False, "error": result.get("error")}
            
            steps_taken = 0
            current_goal = goal
            
            while steps_taken < max_steps:
                steps_taken += 1
                
                # Take screenshot
                screenshot = result.get("screenshot", {})
                if not screenshot.get("base64"):
                    return {"success": False, "error": "No screenshot available"}
                
                # Analyze with vision
                analysis_prompt = f"""
                You are a web navigation agent. Current goal: {current_goal}
                
                Based on the screenshot, determine the next action.
                Choose ONE action from: click, type, scroll, wait, done
                
                Respond in JSON format:
                {{
                    "action": "click|type|scroll|wait|done",
                    "target": "element description or text to type",
                    "reasoning": "why this action"
                }}
                """
                
                analysis = await self._analyze_screenshot(screenshot["base64"], analysis_prompt)
                self.thinking_steps.append({"text": analysis[:200], "icon": "fa-brain"})
                
                # Parse action
                import json
                import re
                
                try:
                    json_match = re.search(r'\{.*\}', analysis, re.DOTALL)
                    if json_match:
                        action_data = json.loads(json_match.group())
                        action = action_data.get("action", "wait")
                        target = action_data.get("target", "")
                        
                        self.action_history.append({
                            "step": steps_taken,
                            "action": action,
                            "target": target,
                            "reasoning": action_data.get("reasoning", "")
                        })
                        
                        # Execute action
                        if action == "click":
                            # Simple click - would need element location
                            # For now, just simulate
                            await asyncio.sleep(1)
                        
                        elif action == "type" and target:
                            # Would need to find input field
                            await asyncio.sleep(1)
                        
                        elif action == "scroll":
                            await self.web.driver.execute_script("window.scrollBy(0, 500)")
                            await asyncio.sleep(1)
                        
                        elif action == "wait":
                            await asyncio.sleep(2)
                        
                        elif action == "done":
                            break
                    
                except Exception as e:
                    logger.error(f"Parse action error: {e}")
                    await asyncio.sleep(2)
                
                # Refresh page content
                result = await self.web.screenshot()
            
            # Extract final content
            extracted = await self._extract_content()
            
            return {
                "success": True,
                "url": url,
                "goal": goal,
                "steps_taken": steps_taken,
                "extracted_content": extracted,
                "thinking_steps": self.thinking_steps,
                "action_history": self.action_history
            }
            
        except Exception as e:
            logger.error(f"Web vision agent error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if self.web:
                self.web.close()
    
    async def _extract_content(self) -> Dict[str, Any]:
        """Extract content from current page."""
        if not self.web or not self.web.driver:
            return {}
        
        try:
            driver = self.web.driver
            return {
                "title": driver.title,
                "url": driver.current_url,
                "text": driver.find_element("tag name", "body").text[:5000],
                "links": len(driver.find_elements("tag name", "a"))
            }
        except Exception as e:
            return {"error": str(e)}


_web_vision_agent = None

def get_web_vision_agent(headless: bool = False) -> WebVisionAgent:
    global _web_vision_agent
    if _web_vision_agent is None:
        _web_vision_agent = WebVisionAgent(headless=headless)
    return _web_vision_agent