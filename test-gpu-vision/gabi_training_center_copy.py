# gabi_training_center.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import os
import pyautogui
import keyboard
from PIL import Image, ImageTk
from gpu_screenshot import GPUScreenshot
from gui_controller import get_gui_controller

class GabiTrainingCenter:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GABI Training Center")
        self.root.geometry("800x600")
        
        # Variablen
        self.current_module = tk.StringVar(value="calc")
        self.elements = tk.StringVar(value="7,8,9,plus,minus,gleich")
        self.training_active = False
        self.vision = GPUScreenshot()
        self.gui = get_gui_controller()
        
        self.setup_ui()
        
    def setup_ui(self):
        # Notebook für Phasen
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Phase 1: Training
        self.training_frame = ttk.Frame(notebook)
        notebook.add(self.training_frame, text="📚 Training")
        self.setup_training_ui()
        
        # Phase 2: Test
        self.test_frame = ttk.Frame(notebook)
        notebook.add(self.test_frame, text="🧪 Test")
        self.setup_test_ui()
        
        # Phase 3: Automation
        self.auto_frame = ttk.Frame(notebook)
        notebook.add(self.auto_frame, text="🤖 Automation")
        self.setup_auto_ui()
        
        # Statusbar
        self.status = ttk.Label(self.root, text="Bereit", relief=tk.SUNKEN)
        self.status.pack(fill='x', padx=10, pady=5)
        
    def setup_training_ui(self):
        # Modul-Auswahl
        ttk.Label(self.training_frame, text="Modul:").grid(row=0, column=0, sticky='w', pady=5)
        ttk.Entry(self.training_frame, textvariable=self.current_module).grid(row=0, column=1, sticky='ew', padx=5)
        ttk.Button(self.training_frame, text="Neu", command=self.new_module).grid(row=0, column=2)
        
        # Elemente
        ttk.Label(self.training_frame, text="Elemente (kommagetrennt):").grid(row=1, column=0, sticky='w', pady=5)
        ttk.Entry(self.training_frame, textvariable=self.elements).grid(row=1, column=1, columnspan=2, sticky='ew', padx=5)
        
        # Trainings-Methoden
        method_frame = ttk.LabelFrame(self.training_frame, text="Trainings-Methode")
        method_frame.grid(row=2, column=0, columnspan=3, sticky='ew', pady=10)
        
        ttk.Button(method_frame, text="🔍 Grid Scan", command=self.start_grid_scan).pack(side='left', padx=5, pady=5)
        ttk.Button(method_frame, text="🎯 Manuell", command=self.start_manual).pack(side='left', padx=5, pady=5)
        ttk.Button(method_frame, text="📸 Batch", command=self.start_batch).pack(side='left', padx=5, pady=5)
        
        # Live Preview
        preview_frame = ttk.LabelFrame(self.training_frame, text="Live-Vorschau")
        preview_frame.grid(row=3, column=0, columnspan=3, sticky='nsew', pady=10)
        
        self.preview_label = ttk.Label(preview_frame, text="Bereit für Training...")
        self.preview_label.pack(pady=20)
        
        # Fortschritt
        self.progress = ttk.Progressbar(self.training_frame, mode='determinate')
        self.progress.grid(row=4, column=0, columnspan=3, sticky='ew', pady=5)
        
        self.training_frame.columnconfigure(1, weight=1)
        
    def setup_test_ui(self):
        # Einzeltest
        ttk.Button(self.test_frame, text="▶️ Einzeltest", command=self.single_test).pack(pady=5)
        
        # Sequenz
        seq_frame = ttk.LabelFrame(self.test_frame, text="Sequenz")
        seq_frame.pack(fill='x', padx=10, pady=10)
        
        self.sequence = tk.StringVar(value="7, plus, 8, gleich")
        ttk.Entry(seq_frame, textvariable=self.sequence).pack(fill='x', padx=5, pady=5)
        ttk.Button(seq_frame, text="Ausführen", command=self.run_sequence).pack(pady=5)
        
    def setup_auto_ui(self):
        # Automation
        ttk.Label(self.auto_frame, text="Aufgabe:").pack(anchor='w', padx=10, pady=5)
        self.task = tk.Text(self.auto_frame, height=3)
        self.task.pack(fill='x', padx=10, pady=5)
        self.task.insert('1.0', "7 + 8 * 9 - 3 =")
        
        control_frame = ttk.Frame(self.auto_frame)
        control_frame.pack(fill='x', padx=10, pady=10)
        
        self.loop_var = tk.BooleanVar()
        ttk.Checkbutton(control_frame, text="Wiederholen", variable=self.loop_var).pack(side='left')
        self.loop_count = ttk.Spinbox(control_frame, from_=1, to=100, width=5)
        self.loop_count.pack(side='left', padx=5)
        ttk.Label(control_frame, text="mal").pack(side='left')
        
        ttk.Button(control_frame, text="⚡ Start", command=self.start_auto).pack(side='right', padx=5)
        ttk.Button(control_frame, text="⏹️ Stop", command=self.stop_auto).pack(side='right')
        
    def start_manual(self):
        """Startet manuelles Training"""
        module = self.current_module.get()
        elements = [e.strip() for e in self.elements.get().split(',')]
        
        # Neuen Thread für Training starten (damit GUI nicht blockiert)
        thread = threading.Thread(target=self.manual_training_loop, args=(module, elements))
        thread.daemon = True
        thread.start()
        
    def manual_training_loop(self, module, elements):
        """Der eigentliche Trainings-Loop"""
        target_dir = f"assets/{module}/"
        os.makedirs(target_dir, exist_ok=True)
        
        self.training_active = True
        self.progress['maximum'] = len(elements)
        
        for i, element in enumerate(elements):
            if not self.training_active:
                break
                
            self.root.after(0, self.update_status, f"🎯 Bitte auf [{element}] zielen und 'S' drücken...")
            
            # Warte auf 'S'
            while self.training_active:
                if keyboard.is_pressed('s'):
                    break
                time.sleep(0.1)
            
            if not self.training_active:
                break
                
            # Position erfassen
            x, y = pyautogui.position()
            
            # Screenshot machen
            screenshot = pyautogui.screenshot(region=(x-30, y-30, 60, 60))
            path = f"{target_dir}btn_{element}.png"
            screenshot.save(path)
            
            # Fortschritt aktualisieren
            self.progress['value'] = i + 1
            self.root.after(0, self.update_status, f"✅ {element} erfasst bei ({x}, {y})")
            
            # Kurz warten bis Taste losgelassen
            while keyboard.is_pressed('s'):
                pass
                
        self.training_active = False
        self.root.after(0, self.update_status, "✅ Training abgeschlossen!")
        
    def run_sequence(self):
        """Testet eine Sequenz von Aktionen"""
        seq = [s.strip() for s in self.sequence.get().split(',')]
        
        thread = threading.Thread(target=self.execute_sequence, args=(seq,))
        thread.daemon = True
        thread.start()
        
    def execute_sequence(self, sequence):
        """Führt die Test-Sequenz aus"""
        module = self.current_module.get()
        
        for step in sequence:
            self.update_status(f"🔍 Suche: {step}")
            
            # Screenshot machen und Template suchen
            img_gpu, _ = self.vision.capture()
            found, pos = self.vision.find_template_gpu(
                img_gpu, 
                f"assets/{module}/btn_{step}.png"
            )
            
            if found:
                x, y = pos
                self.gui.safe_click(x, y)
                self.update_status(f"✅ {step} geklickt bei ({x}, {y})")
                time.sleep(0.5)
            else:
                self.update_status(f"❌ {step} nicht gefunden!")
                break
                
    def update_status(self, message):
        """Aktualisiert Status und Preview"""
        self.status.config(text=message)
        self.preview_label.config(text=message)
        
    def new_module(self):
        """Erstellt neues Modul"""
        name = tk.simpledialog.askstring("Neues Modul", "Modul-Name:")
        if name:
            self.current_module.set(name)
            os.makedirs(f"assets/{name}", exist_ok=True)
            
    def start_grid_scan(self):
        """Startet automatischen Grid-Scan"""
        # Hier kommt dein auto_learn_calc.py Code rein
        messagebox.showinfo("Grid Scan", "Funktion wird implementiert...")
        
    def start_batch(self):
        """Startet Batch-Training"""
        messagebox.showinfo("Batch", "Funktion wird implementiert...")
        
    def single_test(self):
        """Einzeltest eines Elements"""
        messagebox.showinfo("Test", "Funktion wird implementiert...")
        
    def start_auto(self):
        """Startet Automation"""
        messagebox.showinfo("Auto", "Funktion wird implementiert...")
        
    def stop_auto(self):
        """Stoppt Automation"""
        self.training_active = False
        
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = GabiTrainingCenter()
    app.run()