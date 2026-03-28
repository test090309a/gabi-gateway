#!/usr/bin/env python
"""
Cleanup script for GABI Gateway project.
Removes unnecessary files, backups, and temporary files.
"""

import os
import shutil
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Projekt-Hauptverzeichnis
PROJECT_ROOT = Path(__file__).parent.absolute()

# ===== DEFINITIONEN =====

# Verzeichnisse, die komplett gelöscht werden sollen (falls vorhanden)
DIRS_TO_DELETE = [
    "gateway/integrations - Kopie",
    "integrations_____OFFLINE",
    "logs",  # leere Logs
    "tmp",   # temporäre Dateien
    "tests/test-gpu-vision",  # Test-Verzeichnis
    "tests/integrations",  # alte Tests
    "memory_archive",  # alte Memory-Archive (können riesig sein)
    "chroma_data",  # ChromaDB-Daten (optional - ggf. behalten)
    "__pycache__",  # wird automatisch neu erstellt
    "gateway/__pycache__",
    "gateway/api/__pycache__",
    "gateway/core/__pycache__",
    "gateway/integrations/__pycache__",
    "gateway/utils/__pycache__",
]

# Dateien, die gelöscht werden sollen (Patterns)
FILES_TO_DELETE = [
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.log.*",
    "*.tmp",
    "*.backup",
    "*.bak",
    "*~",
    "*.swp",
    "*.swo",
    "gateway.log",
    "semantic_memory.json",  # kann neu erstellt werden
    "MEMORY_ARCHIVE_*.md",   # alte Archive
    "MEMORY_BACKUP_*.md",    # alte Backups
    "chat_*.json",           # alte Chat-Archive (optional)
    "chat_*.md",             # alte Chat-Archive MD
    "webcam_*.png",          # alte Webcam-Bilder
    "20260325_*.png",        # alte Screenshots nach Datum
    "gui_*.png",             # alte GUI-Screenshots
]

# Backup-Dateien (werden archiviert statt gelöscht)
BACKUP_FILES = [
    "MEMORY_BACKUP_*.md",
    "chat_*.json",
    "chat_*.md",
]

# Dateien, die auf jeden Fall behalten werden (Whitelist)
KEEP_FILES = [
    "config.yaml",
    "config.example.yaml",
    "credentials.json",
    "token.json",
    "token.pickle",
    "IDENTITY.md",
    "SKILLS.md",
    "HEARTBEAT.md",
    "MEMORY.md",
    "requirements.txt",
    "yolov8n.pt",
    "workflow_api.json",
    ".gitignore",
]

# Zu behaltende Verzeichnisse (nicht löschen)
KEEP_DIRS = [
    "gateway",
    "static",
    "screenshots",
    "docs",
    "tools",
    "chat_archives",  # falls du Chat-Archive behalten willst
]

# ===== FUNKTIONEN =====

def confirm_action(prompt: str) -> bool:
    """Fragt den Benutzer um Bestätigung."""
    response = input(f"{prompt} (j/n): ").lower().strip()
    return response == 'j' or response == 'yes'

def get_size(path: Path) -> str:
    """Gibt die Größe einer Datei oder eines Verzeichnisses zurück."""
    if path.is_file():
        size = path.stat().st_size
    else:
        size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
    
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"

def list_items_to_delete() -> dict:
    """Listet alle zu löschenden Elemente auf."""
    items = {
        "dirs": [],
        "files": [],
        "size_total": 0
    }
    
    # Verzeichnisse
    for dir_pattern in DIRS_TO_DELETE:
        path = PROJECT_ROOT / dir_pattern
        if path.exists():
            items["dirs"].append(path)
            items["size_total"] += sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
    
    # Dateien (mit Pattern-Matching)
    for pattern in FILES_TO_DELETE:
        for file in PROJECT_ROOT.rglob(pattern):
            if file.is_file():
                # Prüfe ob in Keep-Liste
                should_keep = False
                for keep in KEEP_FILES:
                    if file.name == keep or file.name.endswith(keep.strip('*')):
                        should_keep = True
                        break
                
                if not should_keep and file not in items["files"]:
                    items["files"].append(file)
                    items["size_total"] += file.stat().st_size
    
    return items

def delete_items(items: dict, dry_run: bool = True):
    """Löscht die gesammelten Items."""
    deleted = {"dirs": 0, "files": 0, "size": 0}
    
    # Verzeichnisse löschen
    for path in items["dirs"]:
        size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
        if dry_run:
            print(f"  [DRY RUN] Would delete: {path} ({get_size(path)})")
        else:
            try:
                shutil.rmtree(path)
                print(f"  ✅ Deleted: {path} ({get_size(path)})")
                deleted["dirs"] += 1
                deleted["size"] += size
            except Exception as e:
                print(f"  ❌ Error deleting {path}: {e}")
    
    # Dateien löschen
    for path in items["files"]:
        size = path.stat().st_size
        if dry_run:
            print(f"  [DRY RUN] Would delete: {path} ({get_size(path)})")
        else:
            try:
                path.unlink()
                print(f"  ✅ Deleted: {path} ({get_size(path)})")
                deleted["files"] += 1
                deleted["size"] += size
            except Exception as e:
                print(f"  ❌ Error deleting {path}: {e}")
    
    return deleted

def archive_old_chats(days_old: int = 7):
    """Archiviert alte Chat-Archive (optional)."""
    archive_dir = PROJECT_ROOT / "chat_archives"
    if not archive_dir.exists():
        return
    
    cutoff = datetime.now() - timedelta(days=days_old)
    old_files = []
    
    for file in archive_dir.glob("chat_*.json"):
        mtime = datetime.fromtimestamp(file.stat().st_mtime)
        if mtime < cutoff:
            old_files.append(file)
    
    if old_files:
        print(f"\n📂 {len(old_files)} alte Chat-Archive gefunden (> {days_old} Tage alt)")
        if confirm_action(f"  {len(old_files)} Dateien archivieren/komprimieren?"):
            import zipfile
            zip_name = f"chat_archives_old_{datetime.now().strftime('%Y%m%d')}.zip"
            zip_path = PROJECT_ROOT / zip_name
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in old_files:
                    zipf.write(file, file.relative_to(PROJECT_ROOT))
                    file.unlink()
                    print(f"    📦 Archived: {file.name}")
            
            print(f"  ✅ Archiviert als: {zip_name} ({get_size(zip_path)})")

def main():
    print("=" * 60)
    print("🧹 GABI Gateway - Project Cleanup")
    print("=" * 60)
    print(f"📁 Project root: {PROJECT_ROOT}")
    print()
    
    # Liste zu löschende Items
    print("🔍 Scanning for files to delete...")
    items = list_items_to_delete()
    
    print(f"\n📊 Found:")
    print(f"   📁 {len(items['dirs'])} directories")
    print(f"   📄 {len(items['files'])} files")
    print(f"   💾 Total size: {items['size_total'] / (1024*1024):.1f} MB")
    
    if items['size_total'] == 0:
        print("\n✨ Nothing to clean up!")
        return
    
    print("\n" + "=" * 60)
    print("📋 ITEMS TO DELETE:")
    print("=" * 60)
    
    for path in items["dirs"][:20]:  # Zeige max 20
        print(f"  📁 {path} ({get_size(path)})")
    if len(items["dirs"]) > 20:
        print(f"  ... and {len(items['dirs']) - 20} more")
    
    for path in items["files"][:20]:  # Zeige max 20
        print(f"  📄 {path} ({get_size(path)})")
    if len(items["files"]) > 20:
        print(f"  ... and {len(items['files']) - 20} more")
    
    print()
    
    # Bestätigung
    if not confirm_action("🗑️ Delete these files?"):
        print("❌ Aborted.")
        return
    
    # Dry run
    print("\n🔍 DRY RUN - Preview of deletions...")
    dry_run_deleted = delete_items(items, dry_run=True)
    
    if not confirm_action("\n🚀 Proceed with actual deletion?"):
        print("❌ Aborted.")
        return
    
    # Echte Löschung
    print("\n🗑️ Deleting files...")
    deleted = delete_items(items, dry_run=False)
    
    # Optional: Alte Chats archivieren
    print("\n📦 Archiving old chats...")
    archive_old_chats(days_old=30)
    
    # Zusammenfassung
    print("\n" + "=" * 60)
    print("✅ CLEANUP COMPLETE")
    print("=" * 60)
    print(f"   📁 Directories deleted: {deleted['dirs']}")
    print(f"   📄 Files deleted: {deleted['files']}")
    print(f"   💾 Space freed: {deleted['size'] / (1024*1024):.1f} MB")
    
    # Empfehlungen
    print("\n💡 Recommendations:")
    print("   1. Run `pip install -r requirements.txt` if needed")
    print("   2. Check config.yaml for correct settings")
    print("   3. Start with: python -m gateway.main")
    print()

if __name__ == "__main__":
    main()