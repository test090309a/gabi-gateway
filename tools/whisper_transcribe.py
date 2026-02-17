#!/usr/bin/env python
"""
Whisper Transkriptions-Tool für Pipelines
Verwendung: python tools/whisper_transcribe.py audio.mp3
           cat audio.mp3 | python tools/whisper_transcribe.py
"""

import sys
import requests
import json
import os
from pathlib import Path

WHISPER_URL = "http://127.0.0.1:9090"

def transcribe_file(file_path):
    """Transkribiert eine Audiodatei"""
    try:
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(
                f"{WHISPER_URL}/inference",
                files=files,
                timeout=30
            )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def main():
    if len(sys.argv) > 1:
        # Datei als Argument
        file_path = sys.argv[1]
        if not os.path.exists(file_path):
            print(json.dumps({"error": f"Datei nicht gefunden: {file_path}"}))
            sys.exit(1)
        
        result = transcribe_file(file_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    elif not sys.stdin.isatty():
        # Von stdin lesen (für Pipes)
        data = sys.stdin.buffer.read()
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        
        try:
            result = transcribe_file(tmp_path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            os.unlink(tmp_path)
    else:
        print("❌ Bitte Audiodatei angeben oder per Pipe übergeben")
        print("Beispiele:")
        print("  python tools/whisper_transcribe.py aufnahme.wav")
        print("  cat aufnahme.wav | python tools/whisper_transcribe.py")

if __name__ == "__main__":
    main()