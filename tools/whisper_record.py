#!/usr/bin/env python3
"""
Whisper Audio Recording Tool
Nimmt Audio auf und speichert es für Whisper-Transkription.
"""
import sys
import os

# Versuche verschiedene Recording-Methoden
def try_pyaudio():
    """Recording mit PyAudio."""
    try:
        import pyaudio  # type: ignore
        import wave
        import tempfile

        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        RECORD_SECONDS = 5

        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

        print("Recording...", file=sys.stderr)
        frames = []
        for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
            data = stream.read(CHUNK)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        p.terminate()

        # Speichern
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wf = wave.open(tmp.name, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
            wf.close()
            print(tmp.name)  # Nur Pfad ausgeben

        return True
    except Exception as e:
        print(f"PyAudio failed: {e}", file=sys.stderr)
        return False

def try_sounddevice():
    """Recording mit sounddevice."""
    try:
        import sounddevice as sd
        import tempfile
        import numpy as np

        print("Recording with sounddevice...", file=sys.stderr)
        duration = 5  # seconds
        recording = sd.rec(int(duration * 16000), samplerate=16000, channels=1)
        sd.wait()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            import scipy.io.wavfile
            scipy.io.wavfile.write(tmp.name, 16000, recording)
            print(tmp.name)

        return True
    except Exception as e:
        print(f"sounddevice failed: {e}", file=sys.stderr)
        return False

def try_simple_recording():
    """Einfacher Test mit os.system."""
    try:
        import tempfile
        import subprocess

        print("Trying simple recording...", file=sys.stderr)

        # Versuche verschiedene Audio-Quellen
        sources = [
            "audio=virtual-audio-capturer",
            "audio=@device_cm_{33F0A4D4-4BAC-4963-ACA1-AE2CD40F8518}\\wave",
        ]

        for source in sources:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                cmd = [
                    "ffmpeg", "-y", "-f", "dshow", "-i", f"audio={source}",
                    "-t", "5", "-ar", "16000", "-ac", "1", tmp.name
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=10)
                if result.returncode == 0 and os.path.getsize(tmp.name) > 1000:
                    print(tmp.name)
                    return True

        return False
    except Exception as e:
        print(f"Simple recording failed: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    # Versuche verschiedene Methoden
    methods = [
        ("sounddevice", try_sounddevice),
        ("PyAudio", try_pyaudio),
        ("ffmpeg", try_simple_recording),
    ]

    for name, method in methods:
        print(f"Trying {name}...", file=sys.stderr)
        if method():
            sys.exit(0)

    print("ERROR: No audio recording method available", file=sys.stderr)
    sys.exit(1)
