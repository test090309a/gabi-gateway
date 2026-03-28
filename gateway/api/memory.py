# gateway/api/memory.py
"""Memory API endpoints."""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from fastapi import APIRouter, Header, HTTPException, Depends

from gateway.auth import verify_token
from gateway.core.memory import chat_memory, MEMORY_FILE, NOTES_FILE

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/memory")
async def get_memory(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Gibt das aktuelle Memory zurück."""
    return {
        "memory": chat_memory.memory_content,
        "skills": chat_memory.skills_content,
        "heartbeat": chat_memory.heartbeat_content,
        "remembered_notes": chat_memory.get_remembered_notes(limit=100),
        "conversation_count": len(chat_memory.conversation_history) // 2,
        "last_updated": datetime.now().isoformat(),
    }


@router.get("/memory/notes")
async def get_notes(
    limit: int = 20,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Gibt die gespeicherten Notizen zurück."""
    notes = chat_memory.get_remembered_notes(limit=limit)
    return {"notes": notes, "count": len(notes)}


@router.post("/memory/note")
async def create_note(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Erstellt eine neue Notiz."""
    text = payload.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Notiztext erforderlich")
    
    entry, created = chat_memory.remember_note(text, source="api")
    
    return {
        "status": "success",
        "note": entry,
        "created": created,
        "timestamp": datetime.now().isoformat()
    }


@router.delete("/memory/note/{note_id}")
async def delete_note(
    note_id: str,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Löscht eine Notiz."""
    notes = chat_memory.user_notes
    for i, note in enumerate(notes):
        if note.get("id") == note_id:
            del notes[i]
            chat_memory._save_notes()
            return {"status": "success", "message": f"Notiz {note_id} gelöscht"}
    
    raise HTTPException(status_code=404, detail="Notiz nicht gefunden")


@router.get("/memory/stats")
async def memory_stats(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Gibt Statistiken über das Memory zurück."""
    memory_size = os.path.getsize(MEMORY_FILE) if os.path.exists(MEMORY_FILE) else 0
    memory_lines = len(chat_memory.memory_content.split("\n")) if chat_memory.memory_content else 0
    conversation_count = chat_memory.memory_content.count("## 20")
    
    archives = [f for f in os.listdir(".") if f.startswith("MEMORY_ARCHIVE") and f.endswith(".md")]
    
    return {
        "status": "success",
        "stats": {
            "memory_file": MEMORY_FILE,
            "file_size_kb": round(memory_size / 1024, 2),
            "lines": memory_lines,
            "conversations": conversation_count,
            "history_count": len(chat_memory.conversation_history) // 2,
            "remembered_notes": len(chat_memory.user_notes),
            "archives_available": len(archives),
            "archive_files": archives[-5:] if archives else [],
        }
    }


@router.post("/memory/archive")
async def archive_memory(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Archiviert das aktuelle Memory."""
    try:
        chat_memory._archive_old_memory()
        return {
            "status": "success",
            "message": "Memory wurde archiviert",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory/reset")
async def reset_memory(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Setzt das Memory zurück."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"MEMORY_BACKUP_{timestamp}.md"
        
        if os.path.exists(MEMORY_FILE):
            import shutil
            shutil.copy2(MEMORY_FILE, backup_name)
        
        default_content = f"""# GABI Memory System
## Aktuelle Konversation
- Datum: {datetime.now().strftime('%Y-%m-%d')}
- Thema: Memory zurückgesetzt
- User: Admin
## Letzte Aktivitäten
- {datetime.now().strftime('%H:%M')}: Memory wurde zurückgesetzt
---"""
        
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            f.write(default_content)
        
        chat_memory.memory_content = default_content
        chat_memory.conversation_history = []
        chat_memory.update_heartbeat()
        
        return {
            "status": "success",
            "message": "Memory wurde zurückgesetzt",
            "backup_file": backup_name,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory/generate-soul")
async def generate_soul(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Generiert SOUL.md aus den gesammelten Memory-Daten."""
    try:
        if not os.path.exists(MEMORY_FILE):
            return {"status": "error", "message": "MEMORY.md existiert nicht"}
        
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            memory_content = f.read()
        
        memory_lines = memory_content.split("\n")
        
        user_messages = []
        bot_messages = []
        for line in memory_lines:
            if "**User**:" in line:
                user_messages.append(line.replace("**User**:", "").strip())
            elif "**GABI**:" in line:
                bot_messages.append(line.replace("**GABI**:", "").strip())
        
        from collections import Counter
        stopwords = ["der", "die", "das", "und", "oder", "aber", "ein", "eine", "ist", "sind"]
        all_words = []
        for msg in user_messages:
            words = re.findall(r"\b[a-zA-ZäöüÄÖÜß]{3,}\b", msg.lower())
            all_words.extend([w for w in words if w not in stopwords])
        
        word_counts = Counter(all_words).most_common(10)
        
        soul_content = f"""# GABI Soul - Die Essenz meiner Erfahrungen
## 🧬 Meine Identität
- **Generiert am**: {datetime.now().strftime('%d.%m.%Y %H:%M')}
- **Basierend auf**: {len(user_messages)} User-Interaktionen

## 💭 Was ich über dich gelernt habe
### Deine Interessen (häufige Themen):
{chr(10).join([f'  • {word} ({count}x)' for word, count in word_counts]) if word_counts else '  • Noch nicht genug Daten'}

### Deine typischen Fragen:
"""
        for i, msg in enumerate(user_messages[-5:], 1):
            soul_content += f"\n  {i}. \"{msg[:80]}{'...' if len(msg) > 80 else ''}\""
        
        soul_content += f"""
## 📊 Detaillierte Statistik
| Metrik | Wert |
|--------|------|
| 💬 User-Nachrichten | {len(user_messages)} |
| 🤖 GABI-Antworten | {len(bot_messages)} |
| 📝 Vokabular | {len(set(all_words))} Wörter |
---
*Generiert am {datetime.now().strftime('%d.%m.%Y %H:%M')}*
"""
        
        with open("SOUL.md", "w", encoding="utf-8") as f:
            f.write(soul_content)
        
        return {
            "status": "success",
            "message": f"SOUL.md wurde generiert ({len(user_messages)} Nachrichten analysiert)",
            "stats": {
                "user_messages": len(user_messages),
                "bot_messages": len(bot_messages),
                "unique_words": len(set(all_words)),
                "top_topics": word_counts[:5]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/soul")
async def get_soul(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Gibt den Inhalt der SOUL.md zurück."""
    try:
        if os.path.exists('SOUL.md'):
            with open('SOUL.md', 'r', encoding='utf-8') as f:
                content = f.read()
            return {
                "status": "success",
                "content": content,
                "modified": datetime.fromtimestamp(os.path.getmtime('SOUL.md')).isoformat()
            }
        else:
            return {"status": "error", "message": "SOUL.md nicht gefunden"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))