# gateway/integrations/web_search_simple.py
"""Einfache Web-Suche ohne Selenium - wie im original http_api.py"""

import logging
import re
import httpx
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class SimpleWebSearch:
    """Einfache Web-Suche mit HTTP-Requests (funktioniert zuverlässig)"""
    
    def __init__(self):
        self.client = httpx.Client(timeout=30.0, follow_redirects=True)
    
    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Sucht im Internet mit Startpage.
        
        Args:
            query: Suchbegriff
            max_results: Maximale Anzahl Ergebnisse
            
        Returns:
            Liste mit Suchergebnissen (title, url, snippet)
        """
        try:
            logger.info(f"🔍 Web-Suche: {query}")
            
            # Startpage Search URL
            search_url = "https://www.startpage.com/sp/search"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            }
            
            params = {
                "query": query,
                "num": max_results,
                "sc": "de",
            }
            
            response = await self.client.get(search_url, params=params, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"HTTP Fehler: {response.status_code}")
                return []
            
            html = response.text
            results = self._parse_results(html, max_results)
            
            logger.info(f"✅ {len(results)} Suchergebnisse gefunden")
            return results
            
        except Exception as e:
            logger.error(f"Web-Suche Fehler: {e}")
            return []
    
    def _parse_results(self, html: str, max_results: int) -> List[Dict[str, Any]]:
        """Parst Suchergebnisse aus HTML"""
        results = []
        
        # Suche nach Ergebnis-Blöcken
        pattern = r'<div class="w-gl__result[^>]*>.*?</div>\s*</div>\s*</div>'
        blocks = re.findall(pattern, html, re.DOTALL)
        
        for block in blocks[:max_results]:
            try:
                # Titel
                title_match = re.search(r'<h3[^>]*>(.*?)</h3>', block, re.DOTALL)
                if not title_match:
                    title_match = re.search(r'<a[^>]*class="w-gl__result-title[^>]*>(.*?)</a>', block, re.DOTALL)
                
                title = ""
                if title_match:
                    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                    title = re.sub(r'\s+', ' ', title)
                
                # URL
                url_match = re.search(r'<a[^>]*href="([^"]+)"', block)
                url = url_match.group(1) if url_match else ""
                
                # Snippet
                snippet_match = re.search(r'<p[^>]*class="w-gl__result-snippet[^>]*>(.*?)</p>', block, re.DOTALL)
                if not snippet_match:
                    snippet_match = re.search(r'<div[^>]*class="w-gl__result-snippet[^>]*>(.*?)</div>', block, re.DOTALL)
                
                snippet = ""
                if snippet_match:
                    snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()
                    snippet = re.sub(r'\s+', ' ', snippet)
                
                if title and url and not url.startswith(('/sp/', '/search')):
                    results.append({
                        "title": title[:100],
                        "url": url[:200],
                        "snippet": snippet[:200] if snippet else ""
                    })
                    
            except Exception as e:
                logger.debug(f"Parse error: {e}")
                continue
        
        return results
    
    def close(self):
        """Schließt den HTTP-Client"""
        self.client.close()


# Singleton
_web_search = None


def get_web_search() -> SimpleWebSearch:
    """Get or create web search instance."""
    global _web_search
    if _web_search is None:
        _web_search = SimpleWebSearch()
    return _web_search