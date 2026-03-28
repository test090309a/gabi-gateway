# gateway/integrations/web_search.py
"""Web search integration using Startpage (like original http_api.py)."""

import logging
import re
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger(__name__)


class WebSearch:
    """Web search using Startpage search engine."""
    
    def __init__(self):
        self.base_url = "https://www.startpage.com"
        self.client = httpx.Client(timeout=30.0, follow_redirects=True)
    
    async def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search the web using Startpage.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            
        Returns:
            List of search results with title, url, snippet
        """
        try:
            # Startpage search URL
            search_url = f"{self.base_url}/sp/search"
            
            # Headers to mimic a real browser
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            }
            
            params = {
                "query": query,
                "num": max_results,
                "sc": "de",  # German language results
            }
            
            logger.info(f"🔍 Web search: {query}")
            response = await self.client.get(search_url, params=params, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Search failed: {response.status_code}")
                return []
            
            # Parse HTML results
            results = self._parse_results(response.text, max_results)
            logger.info(f"✅ Found {len(results)} results for '{query}'")
            return results
            
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return []
    
    def _parse_results(self, html: str, max_results: int) -> List[Dict[str, Any]]:
        """Parse search results from Startpage HTML."""
        results = []
        
        # Startpage result pattern
        # Look for result containers
        result_pattern = r'<div class="w-gl__result[^>]*>.*?</div>\s*</div>\s*</div>'
        
        # Find all result divs
        result_blocks = re.findall(result_pattern, html, re.DOTALL)
        
        for block in result_blocks[:max_results]:
            try:
                # Extract title
                title_match = re.search(r'<h3[^>]*>(.*?)</h3>', block, re.DOTALL)
                if not title_match:
                    title_match = re.search(r'<a[^>]*class="w-gl__result-title[^>]*>(.*?)</a>', block, re.DOTALL)
                
                title = ""
                if title_match:
                    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                    title = re.sub(r'\s+', ' ', title)
                
                # Extract URL
                url_match = re.search(r'<a[^>]*href="([^"]+)"', block)
                url = url_match.group(1) if url_match else ""
                
                # Extract snippet
                snippet_match = re.search(r'<p[^>]*class="w-gl__result-snippet[^>]*>(.*?)</p>', block, re.DOTALL)
                if not snippet_match:
                    snippet_match = re.search(r'<div[^>]*class="w-gl__result-snippet[^>]*>(.*?)</div>', block, re.DOTALL)
                
                snippet = ""
                if snippet_match:
                    snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()
                    snippet = re.sub(r'\s+', ' ', snippet)
                
                if title and url:
                    results.append({
                        "title": title[:100],
                        "url": url[:200],
                        "snippet": snippet[:200] if snippet else ""
                    })
                    
            except Exception as e:
                logger.debug(f"Error parsing result: {e}")
                continue
        
        # Fallback: Try alternative parsing if no results found
        if not results:
            # Look for simpler pattern
            alt_pattern = r'<a[^>]*href="(https?://[^"]+)"[^>]*>.*?<h3[^>]*>(.*?)</h3>'
            matches = re.findall(alt_pattern, html, re.DOTALL)
            
            for url, title in matches[:max_results]:
                title = re.sub(r'<[^>]+>', '', title).strip()
                if title and url:
                    results.append({
                        "title": title[:100],
                        "url": url[:200],
                        "snippet": ""
                    })
        
        return results
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()


# Singleton
_web_search = None


def get_web_search() -> WebSearch:
    """Get or create web search instance."""
    global _web_search
    if _web_search is None:
        _web_search = WebSearch()
    return _web_search