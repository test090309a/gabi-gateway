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
    from tkinter import ttk
except ImportError:
    print("❌ Bitte installiere: pip install pystray pillow")
    sys.exit(1)

# === GLOBALE VARIABLEN DIREKT NACH IMPORTS DEFINIEREN ===
CHECK_INTERVAL = 60  # Sekunden (Standard)
AUTO_PUSH = True     # Auto-Push Standard

from auto_git_backup import GitBackup, logger


class LogWindow:
    """Separates Log-Fenster mit korrektem Schließen"""
    
    def __init__(self):
        self.window = None
        self.text = None
        self.running = True
        self.update_job = None
    
    def show(self):
        """Zeigt das Log-Fenster an"""
        if self.window is not None:
            try:
                # Prüfe ob Fenster noch existiert
                self.window.lift()
                self.window.focus_force()
                return
            except:
                self.window = None
        
        # Neues Fenster erstellen
        self.window = tk.Toplevel()
        self.window.title("📝 GABI Git Backup Log")
        self.window.geometry("700x500")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        
        # Damit das Fenster im Vordergrund bleibt
        self.window.lift()
        self.window.focus_force()
        
        # Hauptframe
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill='both', expand=True)
        
        # Textbereich mit Scrollbar
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill='both', expand=True)
        
        self.text = scrolledtext.ScrolledText(
            text_frame, 
            wrap=tk.WORD,
            font=('Consolas', 10),
            background='#1e1e1e',
            foreground='#d4d4d4'
        )
        self.text.pack(fill='both', expand=True)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(10, 0))
        
        ttk.Button(
            button_frame, 
            text="🔄 Aktualisieren", 
            command=self.refresh
        ).pack(side='left', padx=5)
        
        ttk.Button(
            button_frame, 
            text="🗑️ Log löschen", 
            command=self.clear_log
        ).pack(side='left', padx=5)
        
        ttk.Button(
            button_frame, 
            text="📋 Kopieren", 
            command=self.copy_log
        ).pack(side='left', padx=5)
        
        ttk.Button(
            button_frame, 
            text="❌ Schließen", 
            command=self.close
        ).pack(side='right', padx=5)
        
        # Log anzeigen
        self.refresh()
        
        # Automatisches Update starten
        self.start_auto_update()
    
    def refresh(self):
        """Aktualisiert den Log-Inhalt"""
        if not self.text or not self.window:
            return
            
        try:
            log_file = Path("git_backup.log")
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                self.text.delete('1.0', tk.END)
                self.text.insert('1.0', content)
                self.text.see(tk.END)  # Zum Ende scrollen
        except Exception as e:
            print(f"Fehler beim Log-Lesen: {e}")
    
    def clear_log(self):
        """Löscht das Log-File"""
        if messagebox.askyesno("Log löschen", "Wirklich den gesamten Log löschen?"):
            try:
                with open("git_backup.log", "w") as f:
                    f.write("")
                self.refresh()
                messagebox.showinfo("Erfolg", "Log wurde gelöscht!")
            except Exception as e:
                messagebox.showerror("Fehler", f"Konnte Log nicht löschen: {e}")
    
    def copy_log(self):
        """Kopiert Log in Zwischenablage"""
        try:
            content = self.text.get('1.0', tk.END)
            self.window.clipboard_clear()
            self.window.clipboard_append(content)
            messagebox.showinfo("Erfolg", "Log in Zwischenablage kopiert!")
        except Exception as e:
            messagebox.showerror("Fehler", f"Kopieren fehlgeschlagen: {e}")
    
    def start_auto_update(self):
        """Startet automatisches Update alle 5 Sekunden"""
        if not self.window or not self.running:
            return
            
        try:
            self.refresh()
            # Speichere die Job-ID
            self.update_job = self.window.after(5000, self.start_auto_update)
        except tk.TclError:
            # Fenster wurde geschlossen
            self.running = False
    
    def close(self):
        """Schließt das Fenster sauber"""
        self.running = False
        
        # Stoppe automatische Updates
        if self.update_job:
            try:
                self.window.after_cancel(self.update_job)
            except:
                pass
        
        # Fenster zerstören
        if self.window:
            try:
                self.window.destroy()
            except:
                pass
        
        self.window = None
        self.text = None


class StatusWindow:
    """Separates Status-Fenster mit OK-Button"""
    
    def __init__(self, git_backup):
        self.git = git_backup
        self.window = None
    
    def show(self):
        """Zeigt Status-Fenster an"""
        if self.window is not None:
            try:
                self.window.lift()
                self.window.focus_force()
                return
            except:
                self.window = None
        
        # Neues Fenster erstellen
        self.window = tk.Toplevel()
        self.window.title("📊 GABI Git Status")
        self.window.geometry("500x400")
        self.window.resizable(False, False)
        
        # Damit das Fenster im Vordergrund bleibt
        self.window.lift()
        self.window.focus_force()
        
        # Hauptframe
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill='both', expand=True)
        
        # Header
        header = ttk.Label(
            main_frame, 
            text="🤖 GABI Auto Git Backup", 
            font=('Arial', 16, 'bold')
        )
        header.pack(pady=(0, 20))
        
        # Status-Info als Text
        status_text = self._get_status_text()
        
        text_widget = tk.Text(
            main_frame, 
            height=12, 
            font=('Consolas', 10),
            wrap=tk.WORD,
            relief='solid',
            borderwidth=1
        )
        text_widget.pack(fill='both', expand=True, pady=10)
        text_widget.insert('1.0', status_text)
        text_widget.config(state='disabled')
        
        # OK-Button
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(10, 0))
        
        ttk.Button(
            button_frame, 
            text="✅ OK", 
            command=self.close,
            width=20
        ).pack()
    
    def _get_status_text(self):
        """Generiert Status-Text"""
        try:
            # Git-Status
            result = self.git._run_git_command(["status", "--porcelain"])
            changes = len(result.stdout.strip().split('\n')) if result.stdout else 0
            
            # Letzter Commit
            last_commit = self.git._run_git_command(["log", "-1", "--pretty=format:%h | %s | %cr"])
            last_commit_text = last_commit.stdout if last_commit.stdout else "Kein Commit"
            
            # Branch
            branch = self.git._run_git_command(["branch", "--show-current"])
            branch_text = branch.stdout.strip() if branch.stdout else "unknown"
            
            # Hier KEIN global - nur lesender Zugriff auf die Variablen
            return f"""
📁 Projekt: {self.git.repo_path}
🌿 Branch: {branch_text}
⏱️  Intervall: {CHECK_INTERVAL} Sekunden
📤 Auto-Push: {'✅' if AUTO_PUSH else '❌'}
🔄 Watchdog läuft: {self.git.running}

📊 Offene Änderungen: {changes}
🕒 Letzter Commit: {last_commit_text}

🧠 Gehirn-Status:
  • Linke Hemisphäre: {len(self.git.left_history)//2 if hasattr(self.git, 'left_history') else 0} Chats
  • Rechte Hemisphäre: {len(self.git.right_history)//2 if hasattr(self.git, 'right_history') else 0} Chats
  • Corpus Callosum: {'✅ Aktiv' if hasattr(self.git, 'left_history') else '⏳ Initialisiert'}
"""
        except Exception as e:
            return f"❌ Fehler beim Laden des Status: {e}"
    
    def close(self):
        """Schließt das Fenster"""
        if self.window:
            try:
                self.window.destroy()
            except:
                pass
        self.window = None


class GitBackupTray:
    """System-Tray App für Git Backup"""
    
    def __init__(self):
        self.git = GitBackup()
        self.running = True
        self.log_window = LogWindow()
        self.status_window = None
        
        # Tray-Icon erstellen
        self.icon = pystray.Icon(
            "gabi-git",
            self._create_image(),
            menu=self._create_menu(),
            title="GABI Git Backup"
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
                        f"Intervall ändern ({CHECK_INTERVAL}s)",
                        self.change_interval
                    )
                )
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Beenden", self.stop)
        )
    
    def show_status(self, icon=None, item=None):
        """Zeigt Status-Fenster"""
        # In eigenem Thread ausführen um Tkinter nicht zu blockieren
        def show():
            if self.status_window is None:
                self.status_window = StatusWindow(self.git)
            self.status_window.show()
        
        threading.Thread(target=show, daemon=True).start()
    
    def show_log(self, icon=None, item=None):
        """Zeigt Log-Fenster"""
        def show():
            self.log_window.show()
        
        threading.Thread(target=show, daemon=True).start()
    
    def manual_backup(self, icon=None, item=None):
        """Führt manuelles Backup aus"""
        def backup():
            if self.git.check_and_commit():
                # Kurze Benachrichtigung
                self.icon.notify(
                    "✅ Backup erfolgreich erstellt!",
                    "GABI Git Backup"
                )
            else:
                self.icon.notify(
                    "ℹ️ Keine Änderungen gefunden",
                    "GABI Git Backup"
                )
        
        threading.Thread(target=backup, daemon=True).start()
    
    def manual_push(self, icon=None, item=None):
        """Pusht manuell"""
        def push():
            self.icon.notify("📤 Pushe zu GitHub...", "GABI Git Backup")
            self.git.push()
            self.icon.notify("✅ Push abgeschlossen!", "GABI Git Backup")
        
        threading.Thread(target=push, daemon=True).start()
    
    def toggle_auto_push(self, icon=None, item=None):
        """Schaltet Auto-Push um"""
        global AUTO_PUSH
        AUTO_PUSH = not AUTO_PUSH
        self.icon.update_menu()
        self.icon.notify(
            f"Auto-Push: {'✅ AN' if AUTO_PUSH else '❌ AUS'}",
            "GABI Git Backup"
        )
    
    def change_interval(self, icon=None, item=None):
        """Öffnet Dialog zum Ändern des Intervalls"""
        def dialog():
            import tkinter.simpledialog
            global CHECK_INTERVAL  # ← global GANZ AM ANFANG der Funktion!
            
            new_val = tkinter.simpledialog.askinteger(
                "Intervall ändern",
                "Neues Intervall in Sekunden (min. 10):",
                minvalue=10,
                maxvalue=3600,
                initialvalue=CHECK_INTERVAL
            )
            if new_val:
                CHECK_INTERVAL = new_val
                self.icon.update_menu()
                self.icon.notify(
                    f"⏱️ Intervall auf {new_val}s geändert",
                    "GABI Git Backup"
                )
        
        threading.Thread(target=dialog, daemon=True).start()
    
    def stop(self, icon=None, item=None):
        """Beendet den Service"""
        self.git.stop_watching()
        self.running = False
        
        # Log-Fenster schließen
        if self.log_window:
            self.log_window.close()
        
        # Status-Fenster schließen
        if self.status_window:
            self.status_window.close()
        
        # Tray-Icon stoppen
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