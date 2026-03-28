#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import urllib.parse
import urllib.request
import ssl
import re
import time
from fake_useragent import UserAgent
from bs4 import BeautifulSoup

# Fix Windows Unicode encoding
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Emojis als Fallback definieren (für Systeme ohne Unicode-Unterstützung)
USE_EMOJIS = True
try:
    # Test ob Emojis dargestellt werden können
    test = "📌".encode(sys.stdout.encoding)
except:
    USE_EMOJIS = False

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
        except Exception as e:
            return ""

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
        except: 
            pass
        return ""

    def clean_url(self, url, base_url):
        if not url: return ""
        if url.startswith('data:image'): return ""
        # Bereinige die URL von HTML-Tags und doppelten Einträgen
        url = url.strip()
        # Entferne alles nach "> " wenn es ein HTML-Tag ist
        if '">' in url:
            url = url.split('">')[0]
        return urllib.parse.urljoin(base_url, url)

    def extract_url(self, raw_url, domain):
        """Extrahiert die tatsächliche URL aus verschiedenen Formaten"""
        try:
            if 'uddg=' in raw_url:
                parsed = urllib.parse.urlparse(raw_url)
                query_dict = urllib.parse.parse_qs(parsed.query)
                if 'uddg' in query_dict:
                    return urllib.parse.unquote(query_dict['uddg'][0])
            elif 'url=' in raw_url:
                match = re.search(r'url=([^&]+)', raw_url)
                if match:
                    return urllib.parse.unquote(match.group(1))
            elif '//duckduckgo.com/l/?uddg=' in raw_url:
                match = re.search(r'uddg=([^&]+)', raw_url)
                if match:
                    return urllib.parse.unquote(match.group(1))
            # Normale URL
            return raw_url
        except:
            return raw_url

    def parse(self, html, selectors, domain):
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for item in soup.select(selectors['item']):
            try:
                link = item.select_one(selectors['link'])
                if not link: continue
                
                # Rohe URL extrahieren
                raw_url = link.get('href', '').strip()

                # HARTE HTML-BEREINIGUNG
                raw_url = raw_url.split('"')[0]
                raw_url = raw_url.split("'")[0]
                raw_url = raw_url.split('>')[0]
                
                # Bereinige die URL
                if raw_url.startswith('//'):
                    raw_url = 'https:' + raw_url
                elif raw_url.startswith('/'):
                    raw_url = domain + raw_url
                
                # Extrahiere die tatsächliche URL
                clean_url = self.extract_url(raw_url, domain)
                
                # Finale Bereinigung
                if '">' in clean_url:
                    clean_url = clean_url.split('">')[0]
                
                # URL vollständig qualifizieren
                url = urllib.parse.urljoin(domain, clean_url)
                title = link.get_text(strip=True)
                
                # Nur echte Zielseiten, keine DuckDuckGo-Redirects oder Fragmente
                if not url.startswith('http'):
                    continue

                if 'duckduckgo.com' in url and 'uddg=' not in url:
                    continue
                
                # Prüfe ob URL gültig ist (nicht nur ein Fragment oder leer)
                if url and url not in self.seen_urls and len(title) > 3 and url.startswith('http'):
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
                                if ',' in val: 
                                    val = val.split(',')[0].split(' ')[0]
                                img_url = self.clean_url(val, domain)
                                break
                    
                    # Deaktiviert für schnellere Suche - kann bei Bedarf aktiviert werden
                    # if not img_url:
                    #     img_url = self.get_deep_image(url)
                    
                    results.append({
                        'title': title, 
                        'url': url, 
                        'snippet': snippet[:300],
                        'image': img_url
                    })
                    self.seen_urls.add(url)
            except Exception as e:
                continue
        return results

    def search(self, query, max_results=80, start=0):
        all_results = []
        
        # DuckDuckGo HTML-Suche (funktioniert zuverlässiger)
        ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        if start > 0:
            ddg_url += f"&s={start}"
        
        ddg_selectors = {
            'item': '.result',
            'link': '.result__a', 
            'snips': ['.result__snippet']
        }
        
        try:
            html = self.fetch(ddg_url)
            if html:
                results = self.parse(html, ddg_selectors, "https://duckduckgo.com")
                all_results.extend(results)
        except:
            pass
        
        # Wenn keine Ergebnisse, versuche Startpage
        if not all_results:
            sp_start = (start // 10) * 10
            sp_url = f"https://www.startpage.com/sp/search?query={urllib.parse.quote(query)}&start={sp_start}"
            sp_selectors = {
                'item': ".w-gl__result, .result",
                'link': "a.w-gl__result-title, .result-title",
                'snips': ['.w-gl__description', '.result-description']
            }
            try:
                html = self.fetch(sp_url)
                if html:
                    results = self.parse(html, sp_selectors, "https://www.startpage.com")
                    all_results.extend(results)
            except:
                pass
        
        return all_results[:max_results]

def format_results(results, query, start_idx):
    """Formatiert die Suchergebnisse als hübsche Liste"""
    # Symbole je nach Unicode-Unterstützung
    if USE_EMOJIS:
        symbols = {
            'title': '📌',
            'url': '🔗',
            'image': '🖼️',
            'snippet': '📝',
            'no_desc': '❌'
        }
    else:
        symbols = {
            'title': '[TITEL]',
            'url': '[URL]',
            'image': '[BILD]',
            'snippet': '[TEXT]',
            'no_desc': '[KEINE BESCHREIBUNG]'
        }
    
    output = []
    output.append("=" * 80)
    output.append(f"SUCHERGEBNISSE FÜR: \"{query}\"")
    output.append(f"Startposition: {start_idx + 1}")
    output.append("=" * 80)
    output.append("")
    
    if not results:
        output.append(f"{symbols['no_desc']} Keine Ergebnisse gefunden.")
        return "\n".join(output)
    
    for i, result in enumerate(results, 1):
        # Titel mit Nummer
        output.append(f"{i:2d}. {symbols['title']} {result['title']}")
        
        # URL - sauber formatiert
        url = result['url']
        # Kürze die URL für bessere Lesbarkeit
        if len(url) > 70:
            url = url[:67] + "..."
        output.append(f"    {symbols['url']} {url}")
        
        # Bild-URL falls vorhanden (nur anzeigen wenn wirklich vorhanden)
        if result['image'] and not result['image'].endswith('.ico'):
            img = result['image']
            if len(img) > 60:
                img = img[:57] + "..."
            output.append(f"    {symbols['image']} {img}")
        
        # Snippet falls vorhanden
        if result['snippet']:
            # Snippet auf 80 Zeichen pro Zeile umbrechen
            snippet = result['snippet']
            first_line = True
            while snippet:
                if len(snippet) > 77:
                    line = snippet[:77]
                    snippet = snippet[77:]
                else:
                    line = snippet
                    snippet = ""
                
                if first_line:
                    output.append(f"    {symbols['snippet']} {line}")
                    first_line = False
                else:
                    output.append(f"      {line}")
        else:
            output.append(f"    {symbols['snippet']} {symbols['no_desc']} [Keine Beschreibung verfügbar]")
        
        output.append("")  # Leerzeile zwischen Ergebnissen
    
    output.append("=" * 80)
    output.append(f"Gesamt: {len(results)} Ergebnisse angezeigt")
    output.append("=" * 80)
    
    return "\n".join(output)

def main():
    if len(sys.argv) < 2:
        print("\n" + "="*50)
        print("WEBSEARCH - Kommandozeilen-Suchmaschine")
        print("="*50)
        print("\nVerwendung:")
        print("  python websearch.py \"Suchbegriff\" [Startposition]")
        print("\nBeispiele:")
        print("  python websearch.py \"Gregory Peck\"")
        print("  python websearch.py \"Python Programmierung\" 10")
        print("\n" + "="*50)
        return
    
    query = sys.argv[1]
    start_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    
    try:
        # Suchanzeige
        print("\n" + "="*50)
        if USE_EMOJIS:
            print(f"🔍 SUCHE: \"{query}\"")
        else:
            print(f"SUCHE: \"{query}\"")
        print(f"Position: {start_idx + 1}")
        print("="*50)
        print("Bitte warten...")
        print("")
        
        searcher = WebSearch()
        results = searcher.search(query, start=start_idx)
        
        # Formatiert ausgeben
        print(format_results(results, query, start_idx))
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Suche abgebrochen.")
    except Exception as e:
        print(f"\n❌ Fehler bei der Suche: {str(e)}")
        print("\nMögliche Ursachen:")
        print("  • Keine Internetverbindung")
        print("  • Die Suchmaschine ist nicht erreichbar")
        print("  • Zu viele Anfragen in kurzer Zeit")
        
if __name__ == "__main__":
    main()