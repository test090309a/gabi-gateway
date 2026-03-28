# integrations/web_learning.py
"""Web learning for extracting and remembering web content."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class WebLearning:
    """Learn and remember web content."""
    
    def __init__(self):
        self.memory_file = Path("web_learning.json")
        self.memory = self._load_memory()
    
    def _load_memory(self) -> Dict[str, Any]:
        """Load learned content from file."""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Load web learning error: {e}")
        return {"pages": {}, "learned": []}
    
    def _save_memory(self):
        """Save learned content to file."""
        try:
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(self.memory, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Save web learning error: {e}")
    
    def learn_page(self, url: str, content: Dict[str, Any]) -> None:
        """Learn content from a page."""
        self.memory["pages"][url] = {
            "learned_at": datetime.now().isoformat(),
            "content": content
        }
        self.memory["learned"].append({
            "url": url,
            "learned_at": datetime.now().isoformat(),
            "summary": content.get("title", "")[:100]
        })
        
        # Limit learned items
        if len(self.memory["learned"]) > 100:
            self.memory["learned"] = self.memory["learned"][-100:]
        
        self._save_memory()
        logger.info(f"Learned page: {url}")
    
    def get_learned(self, url: str) -> Optional[Dict[str, Any]]:
        """Get learned content for a URL."""
        return self.memory["pages"].get(url)
    
    def search_learned(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search learned content."""
        results = []
        query_lower = query.lower()
        
        for entry in reversed(self.memory["learned"]):
            if query_lower in entry.get("url", "").lower() or query_lower in entry.get("summary", "").lower():
                results.append(entry)
                if len(results) >= limit:
                    break
        
        return results
    
    def get_all_learned(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get all learned items."""
        return self.memory["learned"][-limit:]


_web_learning = None

def get_web_learning() -> WebLearning:
    global _web_learning
    if _web_learning is None:
        _web_learning = WebLearning()
    return _web_learning