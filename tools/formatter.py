#!/usr/bin/env python
# tools/formatter.py - Verbesserte Version für Pipes

import sys
import json
import re

# UTF-8 für Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def extract_titles(data):
    """Extrahiert nur Titel aus JSON"""
    try:
        if isinstance(data, str):
            data = json.loads(data)
        if data.get("ok") and "results" in data:
            titles = [r.get("title", "") for r in data["results"]]
            return "\n".join(titles)
    except:
        pass
    return data

def format_json(data):
    """Formatiert als JSON"""
    try:
        if isinstance(data, str):
            data = json.loads(data)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except:
        return data

def format_table(data):
    """Formatiert als Tabelle"""
    try:
        if isinstance(data, str):
            data = json.loads(data)
        if data.get("ok") and "results" in data:
            results = data["results"]
            table = "┌────┬─────────────────────────────────────┐\n"
            table += "│ #  │ Titel                              │\n"
            table += "├────┼─────────────────────────────────────┤\n"
            for i, r in enumerate(results[:10], 1):
                title = r.get("title", "")[:35]
                table += f"│ {i:<2} │ {title:<35} │\n"
            table += "└────┴─────────────────────────────────────┘\n"
            return table
    except:
        pass
    return data

def main():
    # Lese Input
    if not sys.stdin.isatty():
        input_data = sys.stdin.read()
    else:
        print("❌ Keine Eingabe. Verwende: befehl | python formatter.py [format]")
        return
    
    # Bestimme Format
    format_type = sys.argv[1] if len(sys.argv) > 1 else "auto"
    
    # Formatiere
    if format_type == "titles" or format_type == "title":
        output = extract_titles(input_data)
    elif format_type == "json":
        output = format_json(input_data)
    elif format_type == "table":
        output = format_table(input_data)
    else:
        # Auto-Erkennung
        try:
            data = json.loads(input_data)
            if data.get("ok") and "results" in data:
                output = format_table(data)
            else:
                output = format_json(data)
        except:
            output = input_data
    
    print(output)

if __name__ == "__main__":
    main()