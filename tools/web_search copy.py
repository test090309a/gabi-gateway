#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, urllib.parse, urllib.request, ssl, re, time
from fake_useragent import UserAgent
from bs4 import BeautifulSoup

# Fix Windows Unicode encoding
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

class WebSearch:
    def __init__(self):
        self.ua = UserAgent()
        self.seen_urls = set()

    def fetch(self, url):
        try:
            ctx = ssl._create_unverified_context()
            headers = {
                'User-Agent': self.ua.random,
                'Accept-Language': 'de-DE,de;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Connection': 'keep-alive'
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
                return r.read().decode(r.headers.get_content_charset() or 'utf-8', errors='replace')
        except: return ""

    def get_deep_image(self, url):
        """Besucht die Zielseite, um ein echtes Vorschaubild zu finden"""
        html = self.fetch(url)
        if not html: return ""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            # 1. Suche nach Social Media Meta-Bildern (Open Graph)
            og_img = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'twitter:image'})
            if og_img and og_img.get('content'):
                return self.clean_url(og_img['content'], url)
            # 2. Suche nach dem ersten großen Bild im Body
            for img in soup.find_all('img'):
                src = img.get('data-src') or img.get('src') or img.get('data-lazy-src')
                if src and not any(x in src.lower() for x in ['pixel', 'tracker', 'icon', 'logo', 'button', '.ico']):
                    return self.clean_url(src, url)
        except: pass
        return ""

    def clean_url(self, url, base_url):
        if not url: return ""
        if url.startswith('data:image'): return ""
        return urllib.parse.urljoin(base_url, url)

    def parse(self, html, selectors, domain):
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for item in soup.select(selectors['item']):
            try:
                link = item.select_one(selectors['link'])
                if not link: continue
                raw_url = link.get('href', '')
                if 'uddg=' in raw_url:
                    raw_url = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)['uddg'][0]
                elif 'url=' in raw_url:
                    match = re.search(r'url=([^&]+)', raw_url)
                    if match: raw_url = urllib.parse.unquote(match.group(1))
                url = self.clean_url(raw_url, domain)
                title = link.get_text(strip=True)
                if url and url not in self.seen_urls and len(title) > 3:
                    snippet = ""
                    for s in selectors['snips']:
                        snip_el = item.select_one(s)
                        if snip_el:
                            snippet = snip_el.get_text(strip=True)
                            break
                    img_url = ""
                    img_el = item.find('img')
                    if img_el:
                        for attr in ['data-src', 'srcset', 'src']:
                            val = img_el.get(attr)
                            if val and not val.endswith('.ico') and 'data:image' not in val:
                                if ',' in val: val = val.split(',')[0].split(' ')[0]
                                img_url = self.clean_url(val, domain)
                                break
                    if not img_url:
                        img_url = self.get_deep_image(url)
                    results.append({
                        'title': title, 
                        'url': url, 
                        'snippet': snippet[:300],
                        'image': img_url
                    })
                    self.seen_urls.add(url)
            except: continue
        return results

    def search(self, query, max_results=80, start=0):
        # Startpage nutzt 'start' (0, 10, 20...) - wir runden auf 10er Schritte auf für bessere Kompatibilität
        sp_start = (start // 10) * 10 
        configs = [
            (f"https://www.startpage.com/sp/search?query={urllib.parse.quote(query)}&start={start}", 
             {'item': ".w-gl__result, .result", 'link': "a.w-gl__result-title, .result-title", 'snips': ['.w-gl__description', '.result-description']}, "https://www.startpage.com"),
            (f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}&s={start}", 
             {'item': '.result', 'link': '.result__a', 'snips': ['.result__snippet']}, "https://duckduckgo.com")
        ]
        all_results = []
        for url, sel, domain in configs:
            res = self.parse(self.fetch(url), sel, domain)
            if res:
                all_results.extend(res)
                if len(all_results) >= max_results:
                    break
        return all_results[:max_results]

def main():
    query = sys.argv[1] if len(sys.argv) > 1 else ""
    start_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    res = WebSearch().search(query, start=start_idx) if query else []
    print(json.dumps({"ok": bool(res), "results": res}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()