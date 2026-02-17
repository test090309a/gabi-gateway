#!/usr/bin/env python
"""
AI Analyzer für Pipelines
Verwendung: befehl | python ai_analyzer.py "Dein Prompt"
oder: befehl | python ai_analyzer.py --prompt "Analysiere dies"
"""

import sys
import json
import requests
import argparse
from urllib.parse import quote

# UTF-8 für Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

class AIAnalyzer:
    def __init__(self):
        self.ollama_url = "http://localhost:11434/api/generate"
        self.model = "llama3.2"  # oder dein Modell
        
    def analyze(self, data, prompt):
        """Sendet Daten an Ollama zur Analyse"""
        
        # Bereite Prompt vor
        full_prompt = f"""{prompt}

Hier sind die Daten zur Analyse:
{data[:3000]}  # Begrenze auf 3000 Zeichen

Bitte analysiere diese Informationen und gib eine strukturierte Antwort."""
        
        try:
            # Anfrage an Ollama
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "Keine Antwort")
            else:
                return f"❌ Fehler bei Ollama: {response.status_code}"
                
        except Exception as e:
            return f"❌ Fehler: {str(e)}"
    
    def analyze_with_context(self, data, prompt, previous_results=None):
        """Analyse mit Kontext aus vorherigen Pipeline-Schritten"""
        
        context = ""
        if previous_results:
            context = f"Vorherige Ergebnisse:\n{previous_results}\n\n"
        
        full_prompt = f"""{context}{prompt}

Aktuelle Daten:
{data[:2000]}

Bitte analysiere und gib eine strukturierte Antwort."""
        
        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get("response", "")
            return f"❌ Fehler: {response.status_code}"
            
        except Exception as e:
            return f"❌ Fehler: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description='KI-Analyzer für Pipelines')
    parser.add_argument('prompt', nargs='*', help='Der Prompt für die Analyse')
    parser.add_argument('--prompt', '-p', dest='named_prompt', help='Prompt als benanntes Argument')
    parser.add_argument('--model', '-m', default='llama3.2', help='Ollama Modell')
    parser.add_argument('--context', '-c', help='Vorherige Ergebnisse als Kontext')
    
    args = parser.parse_args()
    
    # Bestimme Prompt
    prompt = ' '.join(args.prompt) if args.prompt else args.named_prompt
    if not prompt:
        prompt = "Fasse die wichtigsten Informationen zusammen"
    
    # Lese Input von stdin
    if sys.stdin.isatty():
        print("❌ Keine Eingabe. Verwende: befehl | python ai_analyzer.py 'dein prompt'")
        sys.exit(1)
    
    input_data = sys.stdin.read()
    
    # Analysiere
    analyzer = AIAnalyzer()
    analyzer.model = args.model
    
    if args.context:
        result = analyzer.analyze_with_context(input_data, prompt, args.context)
    else:
        result = analyzer.analyze(input_data, prompt)
    
    # Ausgabe mit schöner Formatierung
    print("\n" + "="*60)
    print("🔍 KI-ANALYSE")
    print("="*60)
    print(f"📝 Prompt: {prompt}")
    print("-"*60)
    print(result)
    print("="*60)

if __name__ == "__main__":
    main()