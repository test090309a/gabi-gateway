#!/usr/bin/env python
"""
Ultimative Pipeline mit KI-Integration
Verwendung: python pipeline.py "Suchbegriff" --filter NASA --analyze "Fasse zusammen"
"""

import sys
import json
import subprocess
import argparse
from ai_analyzer import AIAnalyzer

class UltimatePipeline:
    def __init__(self):
        self.analyzer = AIAnalyzer()
        
    def run(self, search_term, filter_pattern=None, sort_it=False, 
            format_type=None, analyze_prompt=None):
        
        # Schritt 1: Web-Suche
        print(f"🔍 Suche nach: {search_term}")
        search_cmd = f'python tools/web_search.py "{search_term}"'
        search_result = subprocess.run(
            search_cmd,
            capture_output=True,
            text=True,
            shell=True,
            encoding='utf-8'
        )
        
        current_data = search_result.stdout
        
        # Schritt 2: Filtern (optional)
        if filter_pattern:
            print(f"🔎 Filtere nach: {filter_pattern}")
            filter_cmd = f'findstr {filter_pattern}'
            filter_result = subprocess.run(
                filter_cmd,
                input=current_data,
                capture_output=True,
                text=True,
                shell=True,
                encoding='utf-8'
            )
            current_data = filter_result.stdout
        
        # Schritt 3: Sortieren (optional)
        if sort_it:
            print("📊 Sortiere...")
            sort_cmd = 'sort'
            sort_result = subprocess.run(
                sort_cmd,
                input=current_data,
                capture_output=True,
                text=True,
                shell=True,
                encoding='utf-8'
            )
            current_data = sort_result.stdout
        
        # Schritt 4: Formatieren (optional)
        if format_type:
            print(f"🎨 Formatiere als {format_type}...")
            format_cmd = f'python tools/formatter.py {format_type}'
            format_result = subprocess.run(
                format_cmd,
                input=current_data,
                capture_output=True,
                text=True,
                shell=True,
                encoding='utf-8'
            )
            current_data = format_result.stdout
        
        # Schritt 5: KI-Analyse (optional)
        if analyze_prompt:
            print(f"🧠 KI analysiert: {analyze_prompt}")
            analysis = self.analyzer.analyze(current_data, analyze_prompt)
            
            # Kombiniere Ergebnisse
            result = f"""
{'='*60}
🔍 SUCHERGEBNISSE
{'='*60}
{current_data}

{'='*60}
🧠 KI-ANALYSE
{'='*60}
📝 Prompt: {analyze_prompt}
{'-'*60}
{analysis}
{'='*60}
"""
            return result
        
        return current_data

def main():
    parser = argparse.ArgumentParser(description='Ultimative Pipeline mit KI')
    parser.add_argument('search', help='Suchbegriff')
    parser.add_argument('--filter', '-f', help='Filter-Pattern (z.B. NASA)')
    parser.add_argument('--sort', '-s', action='store_true', help='Sortieren')
    parser.add_argument('--format', '-fmt', choices=['json', 'table', 'pretty'], help='Formatierung')
    parser.add_argument('--analyze', '-a', help='KI-Analyse mit Prompt')
    
    args = parser.parse_args()
    
    pipeline = UltimatePipeline()
    result = pipeline.run(
        search_term=args.search,
        filter_pattern=args.filter,
        sort_it=args.sort,
        format_type=args.format,
        analyze_prompt=args.analyze
    )
    
    print(result)

if __name__ == "__main__":
    main()