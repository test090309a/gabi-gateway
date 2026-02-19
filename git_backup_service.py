# git_backup_service.py - System-Tray Version für Windows
"""
🖥️ GABI Git Backup Service - Läuft im System-Tray
"""

import os
import sys
import threading
import time
from pathlib import Path

# Füge Projekt-Pfad hinzu
sys.path.insert(0, str(Path(__file__).parent))

try:
    import pystray
    from PIL import Image, ImageDraw
    import tkinter as tk
    from tkinter import messagebox, scrolledtext
except ImportError:
    print("❌ Bitte installiere: pip install pystray pillow")
    sys.exit(1)

from auto_git_backup import GitBackup, logger, CHECK_INTERVAL, AUTO_PUSH


class GitBackupTray:
    """System-Tray App für Git Backup"""
    
    def __init__(self):
        self.git = GitBackup()
        self.running = True
        self.log_window = None
        
        # Tray-Icon erstellen
        self.icon = pystray.Icon(
            "gabi-git",
            self._create_image(),
            menu=self._create_menu()
        )
    
    def _create_image(self):
        """Erstellt ein Tray-Icon"""
        # Einfaches Icon: Blauer Kreis mit 'G'
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), (50, 50, 50))
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, width-8, height-8), fill=(0, 120, 212))
        draw.text((20, 16), "G", fill=(255, 255, 255), font=None)
        return image
    
    def _create_menu(self):
        """Erstellt das Tray-Menü"""
        return pystray.Menu(
            pystray.MenuItem("📊 Status anzeigen", self.show_status),
            pystray.MenuItem("📦 Manuelles Backup", self.manual_backup),
            pystray.MenuItem("📤 Jetzt pushen", self.manual_push),
            pystray.MenuItem("📝 Log anzeigen", self.show_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "⚙️ Einstellungen",
                pystray.Menu(
                    pystray.MenuItem(
                        f"Auto-Push: {'✅' if AUTO_PUSH else '❌'}",
                        self.toggle_auto_push
                    ),
                    pystray.MenuItem(
                        f"Intervall: {CHECK_INTERVAL}s",
                        self.change_interval
                    )
                )
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Beenden", self.stop)
        )
    
    def show_status(self):
        """Zeigt Status-Fenster"""
        status = f"""
🤖 GABI Auto Git Backup
{'='*40}

📁 Projekt: {self.git.repo_path}
⏱️  Intervall: {CHECK_INTERVAL} Sekunden
📤 Auto-Push: {'✅' if AUTO_PUSH else '❌'}
🔄 Watchdog läuft: {self.git.running}

📊 Letzte Änderungen:
  • Linke Hemisphäre: {len(self.git.left_history)//2 if hasattr(self.git, 'left_history') else 0} Chats
  • Rechte Hemisphäre: {len(self.git.right_history)//2 if hasattr(self.git, 'right_history') else 0} Chats
"""
        messagebox.showinfo("GABI Git Status", status)
    
    def manual_backup(self):
        """Führt manuelles Backup aus"""
        if self.git.check_and_commit():
            messagebox.showinfo("Erfolg", "✅ Backup erfolgreich erstellt!")
        else:
            messagebox.showinfo("Info", "ℹ️ Keine Änderungen gefunden")
    
    def manual_push(self):
        """Pusht manuell"""
        self.git.push()
        messagebox.showinfo("Push", "📤 Push abgeschlossen")
    
    def show_log(self):
        """Zeigt Log-Fenster"""
        if self.log_window is None or not self.log_window.winfo_exists():
            self.log_window = tk.Tk()
            self.log_window.title("GABI Git Backup Log")
            self.log_window.geometry("600x400")
            
            text = scrolledtext.ScrolledText(self.log_window)
            text.pack(fill='both', expand=True)
            
            # Log-Datei anzeigen
            log_file = Path("git_backup.log")
            if log_file.exists():
                with open(log_file, 'r') as f:
                    text.insert('1.0', f.read())
            
            def update_log():
                if log_file.exists():
                    with open(log_file, 'r') as f:
                        content = f.read()
                        text.delete('1.0', tk.END)
                        text.insert('1.0', content)
                self.log_window.after(5000, update_log)
            
            update_log()
    
    def toggle_auto_push(self):
        """Schaltet Auto-Push um"""
        global AUTO_PUSH
        AUTO_PUSH = not AUTO_PUSH
        self.icon.update_menu()
    
    def change_interval(self):
        """Ändert das Check-Intervall"""
        dialog = tk.Tk()
        dialog.title("Intervall ändern")
        dialog.geometry("300x150")
        
        tk.Label(dialog, text="Neues Intervall (Sekunden):").pack(pady=10)
        entry = tk.Entry(dialog)
        entry.insert(0, str(CHECK_INTERVAL))
        entry.pack(pady=5)
        
        def save():
            global CHECK_INTERVAL
            try:
                new_val = int(entry.get())
                if new_val >= 10:
                    CHECK_INTERVAL = new_val
                    dialog.destroy()
                    self.icon.update_menu()
            except:
                pass
        
        tk.Button(dialog, text="Speichern", command=save).pack(pady=10)
    
    def stop(self):
        """Beendet den Service"""
        self.git.stop_watching()
        self.running = False
        self.icon.stop()
    
    def run(self):
        """Startet den Tray-Service"""
        # Watchdog starten
        self.git.start_watching()
        
        # Tray-Icon starten
        self.icon.run()


if __name__ == "__main__":
    app = GitBackupTray()
    app.run()