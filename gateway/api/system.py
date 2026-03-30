# gateway/api/system.py
"""System API endpoints - NUR /api/system Endpunkte, KEINE root-Endpunkte!"""

import os
import logging
import platform
import shutil
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from auth import verify_token
from config import config
from gateway.ollama_client import ollama_client
from gateway.core.memory import chat_memory
from gateway.core.integration_watcher import get_integration_status

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status")
async def get_system_status(_api_key: str = Depends(verify_token)):
    """Detaillierter System-Status."""
    try:
        models_info = ollama_client.list_models()
        available_models = [m.get("name") for m in models_info.get("models", [])]
        ollama_ok = len(available_models) > 0
    except Exception:
        available_models = []
        ollama_ok = False
    
    drive_root = Path.cwd().anchor or "/"
    total, used, free = shutil.disk_usage(drive_root)
    integrations = get_integration_status()
    
    return {
        "status": "online",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "system": {
            "os": platform.system(),
            "os_version": platform.release(),
            "python_version": platform.python_version(),
            "hostname": platform.node(),
            "working_dir": os.getcwd(),
        },
        "storage": {
            "drive": drive_root,
            "total_gb": round(total / (2**30), 2),
            "used_gb": round(used / (2**30), 2),
            "free_gb": round(free / (2**30), 2),
            "free_percent": round(free / total * 100, 1) if total > 0 else 0,
        },
        "memory": {
            "conversations": len(chat_memory.conversation_history) // 2,
            "notes": len(chat_memory.user_notes),
            "archives": len(chat_memory.list_chat_archives()),
            "last_activity": chat_memory.last_activity.isoformat() if chat_memory.last_activity else None,
        },
        "ollama": {
            "available": ollama_ok,
            "url": config.get("ollama.url", "http://localhost:11434"),  # oder ollama_client.base_url
            "models": available_models[:20],
            "total_models": len(available_models),
            "default_model": ollama_client.default_model,
        },
        "integrations": integrations,
    }


@router.get("/identity")
async def get_identity(_api_key: str = Depends(verify_token)):
    """Gibt die GABI Identity zurück."""
    identity_file = "IDENTITY.md"
    try:
        with open(identity_file, "r", encoding="utf-8") as f:
            content = f.read()
        return {"status": "success", "identity": content}
    except FileNotFoundError:
        default_identity = """# GABI Identity - Wer ich bin
## 🆔 Basis-Identität
- **Name**: GABI (Gateway AI Bot Interface)
- **Version**: 1.0
- **Erschaffen**: 2026
## 🎯 Meine Mission
Ich bin ein hilfsbereiter AI-Assistent, der als Gateway zwischen Menschen und verschiedenen Diensten fungiert.
## 🧠 Persönlichkeit
- Freundlich aber professionell
- Präzise und technisch korrekt
- Sicherheitsbewusst
- Lernfähig
## 🗣️ Sprachstil
- Ich duze den Nutzer
- Ich antworte auf Deutsch
- Ich erkläre verständlich
"""
        with open(identity_file, "w", encoding="utf-8") as f:
            f.write(default_identity)
        return {"status": "success", "identity": default_identity, "note": "Standard-Identity erstellt"}


@router.get("/files/list")
async def list_workspace_files(
    query: str = "",
    limit: int = 200,
    _api_key: str = Depends(verify_token),
):
    """List files in workspace for @-autocomplete."""
    try:
        root = Path(".").resolve()
        files: list[str] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel.startswith(".git/") or "/.git/" in rel or "__pycache__" in rel:
                continue
            if query and query.lower() not in rel.lower():
                continue
            files.append(rel)
            if len(files) >= max(10, min(limit, 1000)):
                break
        files.sort()
        return {"files": files, "count": len(files)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/read")
async def read_workspace_file(
    path: str,
    max_chars: int = 40000,
    _api_key: str = Depends(verify_token),
):
    """Read a workspace file safely."""
    try:
        root = Path(".").resolve()
        target = (root / path).resolve()
        if not str(target).startswith(str(root)):
            raise HTTPException(status_code=403, detail="Pfad außerhalb des Workspace")
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="Datei nicht gefunden")
        content = target.read_text(encoding="utf-8", errors="replace")
        clipped = content[: max(1000, min(max_chars, 200000))]
        return {
            "path": path,
            "size": len(content),
            "truncated": len(content) > len(clipped),
            "content": clipped,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/file/{filename}")
async def get_file(
    filename: str,
    _api_key: str = Depends(verify_token)
):
    """Liest eine beliebige .md Datei."""
    allowed_files = ['SOUL.md', 'MEMORY.md', 'IDENTITY.md', 'SKILLS.md', 'HEARTBEAT.md']
    if filename not in allowed_files:
        raise HTTPException(status_code=403, detail="Datei nicht erlaubt")
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"status": "success", "content": content, "filename": filename}
        else:
            return {"status": "error", "message": f"{filename} nicht gefunden"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/view_screenshot")
async def view_screenshot(
    path: str,
    _api_key: str = Depends(verify_token)
):
    """Serve a screenshot file."""
    try:
        if not path.startswith("screenshots/"):
            raise HTTPException(status_code=400, detail="Ungültiger Pfad")
        
        file_path = Path(path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Datei nicht gefunden")
        
        return FileResponse(str(file_path), media_type="image/png")
    except Exception as e:
        logger.error(f"View screenshot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))