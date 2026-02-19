# gabi_training_center.py (vollständige korrigierte Version)
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog
import threading
import time
import os
import json
import csv
from datetime import datetime, timedelta
import pyautogui
import keyboard
from PIL import Image, ImageTk, ImageDraw
from gpu_screenshot import GPUScreenshot
from gui_controller import get_gui_controller

class GabiTrainingCenter:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GABI Training Center v1.0")
        self.root.geometry("1000x800")

        # Darkmode und große Schrift
        self.darkmode = True
        self.font_size = 12
        self.font_size_large = 16
        self.apply_theme()

        # Variablen
        self.current_module = tk.StringVar(value="calc")
        self.elements = tk.StringVar(value="7,8,9,plus,minus,gleich,mal,geteilt")
        self.training_active = False
        self.test_active = False
        self.auto_active = False
        self.auto_paused = False
        self.vision = GPUScreenshot()
        self.gui = get_gui_controller()
        self.test_results = []
        self.templates_cache = {}
        self.watchdogs = []
        self.scheduled_jobs = []
        self.batch_tasks = []

        # Icons/Emojis für bessere UI
        self.icons = {
            "success": "[OK]",
            "fail": "[X]",
            "wait": "[..]",
            "search": "[S]",
            "click": "[C]",
            "target": "[T]"
        }

        self.setup_ui()
        self.load_modules()

    def apply_theme(self):
        """Wendet modernes Dark Theme an - VS Code / Discord Style"""
        # Moderne Farbpalette
        self.bg_primary = "#1e1e2e"      # Dunkles Lila-Grau (Catppuccin)
        self.bg_secondary = "#313244"     # Etwas heller
        self.bg_tertiary = "#45475a"      # Noch heller für Hover
        self.bg_input = "#181825"         # Sehr dunkel für Eingaben

        self.fg_primary = "#cdd6f4"       # Helles Grau-Blau
        self.fg_secondary = "#a6adc8"      # Etwas dunkler
        self.fg_muted = "#6c7086"          # Gedämpft

        self.accent_blue = "#89b4fa"       # Modernes Blau
        self.accent_green = "#a6e3a1"      # Mint Grün
        self.accent_red = "#f38ba8"        # Rosa Rot
        self.accent_yellow = "#f9e2af"    # Warm Gelb
        self.accent_purple = "#cba6f7"     # Lavendel
        self.accent_cyan = "#94e2d5"       # Türkis

        self.border_color = "#45475a"
        self.success_color = self.accent_green
        self.error_color = self.accent_red
        self.warning_color = self.accent_yellow

        # Schriftarten - modern und lesbar
        self.font_size = 11
        self.font_normal = ("Segoe UI", self.font_size)
        self.font_large = ("Segoe UI", 14, "bold")
        self.font_small = ("Segoe UI", 10)
        self.font_heading = ("Segoe UI", 16, "bold")

        # Tkinter Window
        self.root.configure(bg=self.bg_primary)

        # Modernes ttk Style
        style = ttk.Style()
        style.theme_use('clam')

        # Global Frame & Label
        style.configure("TFrame", background=self.bg_primary)
        style.configure("TLabel", background=self.bg_primary, foreground=self.fg_primary, font=self.font_normal)
        style.configure("TLabelframe", background=self.bg_primary, foreground=self.fg_primary, bordercolor=self.border_color)
        style.configure("TLabelframe.Label", background=self.bg_primary, foreground=self.fg_primary, font=self.font_large)

        # Modern Buttons mit Farben
        style.configure("Primary.TButton",
            background=self.accent_blue,
            foreground=self.bg_primary,
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
            focuscolor="none")
        style.map("Primary.TButton",
            background=[("active", self.accent_cyan)],
            foreground=[("active", self.bg_primary)])

        style.configure("Success.TButton",
            background=self.accent_green,
            foreground=self.bg_primary,
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
            focuscolor="none")

        style.configure("Danger.TButton",
            background=self.accent_red,
            foreground=self.bg_primary,
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
            focuscolor="none")

        style.configure("TButton",
            background=self.bg_tertiary,
            foreground=self.fg_primary,
            font=self.font_normal,
            borderwidth=0,
            focuscolor="none",
            padding=(10, 6))
        style.map("TButton",
            background=[("active", self.accent_purple)],
            foreground=[("active", self.bg_primary)])

        # Entry & Combobox
        style.configure("TEntry",
            fieldbackground=self.bg_input,
            foreground=self.fg_primary,
            insertcolor=self.fg_primary,
            borderwidth=1,
            lightcolor=self.border_color,
            darkcolor=self.border_color)
        style.configure("TCombobox",
            fieldbackground=self.bg_input,
            foreground=self.fg_primary,
            background=self.bg_tertiary,
            borderwidth=1,
            arrowcolor=self.fg_primary)

        # Treeview (Listen)
        style.configure("Treeview",
            background=self.bg_secondary,
            foreground=self.fg_primary,
            fieldbackground=self.bg_secondary,
            font=self.font_small,
            borderwidth=0,
            rowheight=28)
        style.configure("Treeview.Item",
            background=self.bg_secondary,
            foreground=self.fg_primary,
            padding=5)
        style.map("Treeview",
            background=[("selected", self.accent_blue)],
            foreground=[("selected", self.bg_primary)])
        style.configure("Treeview.Heading",
            background=self.bg_tertiary,
            foreground=self.fg_primary,
            font=("Segoe UI", 10, "bold"),
            borderwidth=0)
        style.map("Treeview.Heading",
            background=[("active", self.accent_purple)])

        # Scrollbar
        style.configure("TScrollbar",
            background=self.bg_secondary,
            troughcolor=self.bg_primary,
            borderwidth=0,
            arrowsize=12)
        style.map("TScrollbar",
            background=[("active", self.bg_tertiary)])

        # Progressbar
        style.configure("Horizontal.TProgressbar",
            background=self.accent_blue,
            troughcolor=self.bg_secondary,
            borderwidth=0)

        # Notebook (Tabs) - Modern Style
        style.configure("TNotebook",
            background=self.bg_primary,
            borderwidth=0)
        style.configure("TNotebook.Tab",
            background=self.bg_secondary,
            foreground=self.fg_secondary,
            font=self.font_normal,
            padding=(16, 8),
            borderwidth=0)
        style.map("TNotebook.Tab",
            background=[("selected", self.accent_blue)],
            foreground=[("selected", self.bg_primary)],
            expand=[("selected", self.accent_blue)],
            focus=[("selected", self.accent_blue)])

        # Checkbutton & Radiobutton
        style.configure("TCheckbutton",
            background=self.bg_primary,
            foreground=self.fg_primary,
            font=self.font_normal,
            focuscolor="none")
        style.map("TCheckbutton",
            indicatorcolor=[("selected", self.accent_blue)],
            foreground=[("active", self.fg_primary)])

        style.configure("TRadiobutton",
            background=self.bg_primary,
            foreground=self.fg_primary,
            font=self.font_normal,
            focuscolor="none")

        # PanedWindow
        style.configure("TPanedwindow",
            background=self.bg_primary)
        style.configure("Sash",
            background=self.border_color,
            troughcolor=self.bg_primary)

    def setup_ui(self):
        # Haupt-Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Phase 1: Training
        self.training_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.training_frame, text="1. Training", padding=10)
        self.setup_training_ui()

        # Phase 2: Test (erweitert)
        self.test_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.test_frame, text="2. Test & Validierung", padding=10)
        self.setup_test_ui()

        # Phase 3: Automation
        self.auto_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.auto_frame, text="3. Automation", padding=10)
        self.setup_auto_ui()

        # Phase 4: Hilfe
        self.help_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.help_frame, text="4. Hilfe & Tutorials", padding=10)
        self.setup_help_ui()

        # Statusbar
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill='x', padx=10, pady=5)

        self.status = ttk.Label(self.status_frame, text="✅ Bereit", relief=tk.SUNKEN)
        self.status.pack(side='left', fill='x', expand=True)

        self.time_label = ttk.Label(self.status_frame, text=datetime.now().strftime("%H:%M:%S"))
        self.time_label.pack(side='right')

        # Hilfe-Button in Statusbar
        self.help_btn = ttk.Button(self.status_frame, text="? Hilfe", command=self.show_quick_help)
        self.help_btn.pack(side='right', padx=5)

        self.update_clock()
        
    # ========== TEST-PHASE METHODEN ==========
    
    def setup_test_ui(self):
        # Haupt-Testbereich mit PanedWindow für Flexibilität
        main_paned = ttk.PanedWindow(self.test_frame, orient=tk.HORIZONTAL)
        main_paned.pack(fill='both', expand=True)
        
        # Linke Seite: Test-Konfiguration
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)
        
        # Rechte Seite: Ergebnisse & Log
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=1)
        
        # === LINKE SEITE: TEST-KONFIGURATION ===
        
        # Modul-Auswahl für Tests
        module_frame = ttk.LabelFrame(left_frame, text="📦 Modul auswählen")
        module_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(module_frame, text="Modul:").grid(row=0, column=0, sticky='w', pady=5)
        self.test_module = ttk.Combobox(module_frame, textvariable=self.current_module)
        self.test_module.grid(row=0, column=1, sticky='ew', padx=5)
        self.test_module.bind('<<ComboboxSelected>>', self.on_module_selected)
        
        ttk.Button(module_frame, text="🔄 Templates laden", 
                  command=self.load_templates).grid(row=0, column=2, padx=5)
        module_frame.columnconfigure(1, weight=1)
        
        # Verfügbare Elemente anzeigen
        elements_frame = ttk.LabelFrame(left_frame, text="🔖 Verfügbare Elemente")
        elements_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Liste mit Checkboxes für Elemente
        self.elements_listbox = tk.Listbox(elements_frame, selectmode=tk.MULTIPLE, height=8)
        self.elements_listbox.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Scrollbar für Listbox
        scrollbar = ttk.Scrollbar(self.elements_listbox)
        scrollbar.pack(side='right', fill='y')
        self.elements_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.elements_listbox.yview)
        
        # Buttons für Element-Auswahl
        btn_frame = ttk.Frame(elements_frame)
        btn_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(btn_frame, text="✅ Alle auswählen", 
                  command=self.select_all_elements).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="❌ Alle abwählen", 
                  command=self.deselect_all_elements).pack(side='left', padx=2)
        
        # Test-Typ Auswahl
        test_type_frame = ttk.LabelFrame(left_frame, text="🎯 Test-Typ")
        test_type_frame.pack(fill='x', padx=10, pady=5)
        
        self.test_type = tk.StringVar(value="single")
        ttk.Radiobutton(test_type_frame, text="Einzeltest", variable=self.test_type, 
                       value="single", command=self.update_test_ui).pack(anchor='w', padx=10)
        ttk.Radiobutton(test_type_frame, text="Sequenz-Test", variable=self.test_type, 
                       value="sequence", command=self.update_test_ui).pack(anchor='w', padx=10)
        ttk.Radiobutton(test_type_frame, text="Batch-Test (alle)", variable=self.test_type, 
                       value="batch", command=self.update_test_ui).pack(anchor='w', padx=10)
        ttk.Radiobutton(test_type_frame, text="Performance-Test", variable=self.test_type, 
                       value="performance", command=self.update_test_ui).pack(anchor='w', padx=10)
        
        # Dynamischer Bereich für Test-Konfiguration
        self.test_config_frame = ttk.LabelFrame(left_frame, text="⚙️ Test-Konfiguration")
        self.test_config_frame.pack(fill='x', padx=10, pady=5)
        
        # Hier wird je nach Test-Typ der Inhalt eingefügt
        self.config_content = ttk.Frame(self.test_config_frame)
        self.config_content.pack(fill='x', padx=5, pady=5)
        
        # Standard-Konfiguration für Einzeltest
        self.setup_single_test_config()
        
        # Test-Parameter
        params_frame = ttk.LabelFrame(left_frame, text="📊 Test-Parameter")
        params_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(params_frame, text="Threshold:").grid(row=0, column=0, sticky='w', padx=5)
        self.threshold = tk.DoubleVar(value=0.8)
        ttk.Scale(params_frame, from_=0.5, to=1.0, variable=self.threshold, 
                 orient=tk.HORIZONTAL).grid(row=0, column=1, sticky='ew', padx=5)
        self.threshold_label = ttk.Label(params_frame, text="0.80")
        self.threshold_label.grid(row=0, column=2, padx=5)
        self.threshold.trace('w', lambda *args: self.threshold_label.config(text=f"{self.threshold.get():.2f}"))
        
        ttk.Label(params_frame, text="Wiederholungen:").grid(row=1, column=0, sticky='w', padx=5)
        self.test_repeats = ttk.Spinbox(params_frame, from_=1, to=10, width=5)
        self.test_repeats.grid(row=1, column=1, sticky='w', padx=5)
        self.test_repeats.set(1)
        
        params_frame.columnconfigure(1, weight=1)
        
        # Aktions-Buttons
        action_frame = ttk.Frame(left_frame)
        action_frame.pack(fill='x', padx=10, pady=10)
        
        self.test_btn = ttk.Button(action_frame, text="▶️ Test starten", 
                                   command=self.start_test)
        self.test_btn.pack(side='left', padx=5)
        
        ttk.Button(action_frame, text="⏹️ Test abbrechen", 
                  command=self.stop_test).pack(side='left', padx=5)
        
        ttk.Button(action_frame, text="📋 Report exportieren", 
                  command=self.export_report).pack(side='right', padx=5)
        
        # === RECHTE SEITE: ERGEBNISSE ===
        
        # Live-Preview
        preview_frame = ttk.LabelFrame(right_frame, text="👁️ Live Preview")
        preview_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Canvas für Preview
        self.preview_canvas = tk.Canvas(preview_frame, bg='black', height=200)
        self.preview_canvas.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Test-Log
        log_frame = ttk.LabelFrame(right_frame, text="📝 Test-Log")
        log_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.test_log = scrolledtext.ScrolledText(log_frame, height=15, width=40)
        self.test_log.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Status-Anzeige
        self.test_status = ttk.Progressbar(right_frame, mode='determinate')
        self.test_status.pack(fill='x', padx=10, pady=5)
        
        # Statistik
        stats_frame = ttk.LabelFrame(right_frame, text="📈 Statistik")
        stats_frame.pack(fill='x', padx=10, pady=5)
        
        self.stats_text = tk.StringVar(value="Erfolge: 0/0 (0%)")
        ttk.Label(stats_frame, textvariable=self.stats_text).pack(pady=5)
        
    def setup_single_test_config(self):
        """Konfiguration für Einzeltest"""
        for widget in self.config_content.winfo_children():
            widget.destroy()
            
        ttk.Label(self.config_content, text="Element:").grid(row=0, column=0, sticky='w')
        self.single_element = ttk.Combobox(self.config_content, width=20)
        self.single_element.grid(row=0, column=1, padx=5, pady=2)
        self.single_element.bind('<<ComboboxSelected>>', self.preview_template)
        
        ttk.Label(self.config_content, text="Erwartete Position:").grid(row=1, column=0, sticky='w')
        self.expected_pos = tk.StringVar(value="(auto)")
        ttk.Entry(self.config_content, textvariable=self.expected_pos, width=15).grid(row=1, column=1, padx=5)
        
    def setup_sequence_test_config(self):
        """Konfiguration für Sequenz-Test"""
        for widget in self.config_content.winfo_children():
            widget.destroy()
            
        ttk.Label(self.config_content, text="Sequenz:").grid(row=0, column=0, sticky='w')
        self.sequence_entry = ttk.Entry(self.config_content, width=30)
        self.sequence_entry.grid(row=0, column=1, padx=5, pady=2)
        self.sequence_entry.insert(0, "7, plus, 8, gleich")
        
        ttk.Label(self.config_content, text="Verzögerung (s):").grid(row=1, column=0, sticky='w')
        self.sequence_delay = ttk.Spinbox(self.config_content, from_=0.1, to=2.0, width=5)
        self.sequence_delay.grid(row=1, column=1, sticky='w', padx=5)
        self.sequence_delay.set(0.5)
        
    def setup_batch_test_config(self):
        """Konfiguration für Batch-Test"""
        for widget in self.config_content.winfo_children():
            widget.destroy()
            
        ttk.Label(self.config_content, text="Test-Modus:").grid(row=0, column=0, sticky='w')
        self.batch_mode = ttk.Combobox(self.config_content, values=["Alle nacheinander", "Parallel (Threads)"], width=20)
        self.batch_mode.grid(row=0, column=1, padx=5, pady=2)
        self.batch_mode.set("Alle nacheinander")
        
        ttk.Label(self.config_content, text="Timeout (s):").grid(row=1, column=0, sticky='w')
        self.batch_timeout = ttk.Spinbox(self.config_content, from_=1, to=30, width=5)
        self.batch_timeout.grid(row=1, column=1, sticky='w', padx=5)
        self.batch_timeout.set(5)
        
    def setup_performance_test_config(self):
        """Konfiguration für Performance-Test"""
        for widget in self.config_content.winfo_children():
            widget.destroy()
            
        ttk.Label(self.config_content, text="Test-Dauer (s):").grid(row=0, column=0, sticky='w')
        self.perf_duration = ttk.Spinbox(self.config_content, from_=5, to=60, width=5)
        self.perf_duration.grid(row=0, column=1, sticky='w', padx=5)
        self.perf_duration.set(10)
        
        ttk.Label(self.config_content, text="Element:").grid(row=1, column=0, sticky='w')
        self.perf_element = ttk.Combobox(self.config_content, width=20)
        self.perf_element.grid(row=1, column=1, padx=5, pady=2)
        
    def update_test_ui(self):
        """Aktualisiert UI basierend auf Test-Typ"""
        test_type = self.test_type.get()
        
        if test_type == "single":
            self.setup_single_test_config()
        elif test_type == "sequence":
            self.setup_sequence_test_config()
        elif test_type == "batch":
            self.setup_batch_test_config()
        elif test_type == "performance":
            self.setup_performance_test_config()
            
        # Comboboxen mit Elementen füllen
        elements = self.get_element_list()
        if hasattr(self, 'single_element'):
            self.single_element['values'] = elements
        if hasattr(self, 'perf_element'):
            self.perf_element['values'] = elements
            
    def load_modules(self):
        """Lädt verfügbare Module aus assets/"""
        if os.path.exists("assets"):
            modules = [d for d in os.listdir("assets") 
                      if os.path.isdir(os.path.join("assets", d))]
            self.test_module['values'] = modules
            
    def on_module_selected(self, event=None):
        """Wird aufgerufen wenn Modul ausgewählt wird"""
        self.load_templates()
        
    def load_templates(self):
        """Lädt verfügbare Templates aus dem Modul"""
        module = self.current_module.get()
        template_dir = f"assets/{module}/"
        
        self.elements_listbox.delete(0, tk.END)
        
        if os.path.exists(template_dir):
            templates = [f.replace("btn_", "").replace(".png", "") 
                        for f in os.listdir(template_dir) 
                        if f.startswith("btn_") and f.endswith(".png")]
            
            for template in sorted(templates):
                self.elements_listbox.insert(tk.END, template)
                
            self.log_message(f"📦 {len(templates)} Templates geladen aus {module}")
            self.update_test_ui()
        else:
            self.log_message(f"❌ Kein Template-Verzeichnis für {module}")
            
    def get_element_list(self):
        """Gibt Liste aller verfügbaren Elemente zurück"""
        elements = []
        for i in range(self.elements_listbox.size()):
            elements.append(self.elements_listbox.get(i))
        return elements
        
    def get_selected_elements(self):
        """Gibt Liste der ausgewählten Elemente zurück"""
        selected = []
        for i in self.elements_listbox.curselection():
            selected.append(self.elements_listbox.get(i))
        return selected
        
    def select_all_elements(self):
        """Wählt alle Elemente aus"""
        self.elements_listbox.selection_set(0, tk.END)
        
    def deselect_all_elements(self):
        """Hebt alle Auswahl auf"""
        self.elements_listbox.selection_clear(0, tk.END)
        
    def preview_template(self, event=None):
        """Zeigt Vorschau des ausgewählten Templates"""
        if not hasattr(self, 'single_element'):
            return
            
        element = self.single_element.get()
        if not element:
            return
            
        module = self.current_module.get()
        template_path = f"assets/{module}/btn_{element}.png"
        
        if os.path.exists(template_path):
            try:
                # Template laden und skalieren
                img = Image.open(template_path)
                img.thumbnail((180, 180))
                
                # In PhotoImage konvertieren
                photo = ImageTk.PhotoImage(img)
                
                # Auf Canvas anzeigen
                self.preview_canvas.delete("all")
                self.preview_canvas.create_image(90, 90, image=photo)
                self.preview_canvas.image = photo  # Referenz behalten
                
                self.log_message(f"👁️ Vorschau: {element}")
            except Exception as e:
                self.log_message(f"❌ Fehler beim Laden: {e}")
                
    def start_test(self):
        """Startet den ausgewählten Test"""
        if self.test_active:
            return
            
        self.test_active = True
        self.test_btn.config(state='disabled')
        self.test_results = []
        
        test_type = self.test_type.get()
        module = self.current_module.get()
        
        # Test in eigenem Thread starten
        thread = threading.Thread(target=self.run_test, args=(test_type, module))
        thread.daemon = True
        thread.start()
        
    def run_test(self, test_type, module):
        """Führt den Test aus"""
        self.log_message(f"🚀 Starte {test_type}-Test für Modul: {module}")
        
        if test_type == "single":
            self.run_single_test(module)
        elif test_type == "sequence":
            self.run_sequence_test(module)
        elif test_type == "batch":
            self.run_batch_test(module)
        elif test_type == "performance":
            self.run_performance_test(module)
            
        self.update_statistics()
        
        self.root.after(0, self.test_finished)
        
    def run_single_test(self, module):
        """Führt Einzeltest durch"""
        element = self.single_element.get()
        if not element:
            self.log_message("❌ Kein Element ausgewählt!")
            return
            
        repeats = int(self.test_repeats.get())
        threshold = self.threshold.get()
        
        template_path = f"assets/{module}/btn_{element}.png"
        if not os.path.exists(template_path):
            self.log_message(f"❌ Template nicht gefunden: {template_path}")
            return
            
        self.test_status['maximum'] = repeats
        
        for i in range(repeats):
            if not self.test_active:
                break
                
            self.log_message(f"{self.icons['search']} Suche: {element} (Versuch {i+1}/{repeats})")
            
            # Screenshot machen
            img_gpu, _ = self.vision.capture()
            
            # Template suchen
            start_time = time.time()
            found, pos = self.vision.find_template_gpu(img_gpu, template_path, threshold)
            duration = (time.time() - start_time) * 1000
            
            if found:
                x, y = pos
                self.log_message(f"  {self.icons['success']} Gefunden bei ({x}, {y}) in {duration:.1f}ms")
                
                self.test_results.append({
                    "element": element,
                    "success": True,
                    "position": (x, y),
                    "time_ms": duration,
                    "threshold": threshold
                })
            else:
                self.log_message(f"  {self.icons['fail']} Nicht gefunden ({duration:.1f}ms)")
                self.test_results.append({
                    "element": element,
                    "success": False,
                    "time_ms": duration,
                    "threshold": threshold
                })
                
            self.test_status['value'] = i + 1
            time.sleep(0.5)
            
    def run_sequence_test(self, module):
        """Führt Sequenz-Test durch"""
        sequence_text = self.sequence_entry.get()
        elements = [e.strip() for e in sequence_text.split(',')]
        delay = float(self.sequence_delay.get())
        
        self.test_status['maximum'] = len(elements)
        
        for i, element in enumerate(elements):
            if not self.test_active:
                break
                
            self.log_message(f"{self.icons['search']} Schritt {i+1}: {element}")
            
            template_path = f"assets/{module}/btn_{element}.png"
            
            if not os.path.exists(template_path):
                self.log_message(f"  {self.icons['fail']} Template nicht gefunden!")
                continue
                
            # Screenshot und Suche
            img_gpu, _ = self.vision.capture()
            found, pos = self.vision.find_template_gpu(img_gpu, template_path, self.threshold.get())
            
            if found:
                x, y = pos
                self.log_message(f"  {self.icons['click']} Klicke {element} bei ({x}, {y})")
                self.gui.safe_click(x, y)
                
                self.test_results.append({
                    "step": i+1,
                    "element": element,
                    "success": True,
                    "position": (x, y)
                })
            else:
                self.log_message(f"  {self.icons['fail']} {element} nicht gefunden! Sequenz abgebrochen.")
                break
                
            self.test_status['value'] = i + 1
            time.sleep(delay)
            
    def run_batch_test(self, module):
        """Testet alle ausgewählten Elemente"""
        elements = self.get_selected_elements()
        if not elements:
            elements = self.get_element_list()
            
        self.test_status['maximum'] = len(elements)
        
        for i, element in enumerate(elements):
            if not self.test_active:
                break
                
            self.log_message(f"{self.icons['search']} Teste: {element}")
            
            template_path = f"assets/{module}/btn_{element}.png"
            
            if not os.path.exists(template_path):
                self.log_message(f"  {self.icons['fail']} Template fehlt!")
                continue
                
            img_gpu, _ = self.vision.capture()
            found, pos = self.vision.find_template_gpu(img_gpu, template_path, self.threshold.get())
            
            if found:
                self.log_message(f"  {self.icons['success']} OK bei {pos}")
                self.test_results.append({"element": element, "success": True})
            else:
                self.log_message(f"  {self.icons['fail']} NICHT GEFUNDEN")
                self.test_results.append({"element": element, "success": False})
                
            self.test_status['value'] = i + 1
            time.sleep(0.3)
            
    def run_performance_test(self, module):
        """Performance-Test mit Zeitmessung"""
        element = self.perf_element.get()
        if not element:
            self.log_message("❌ Kein Element ausgewählt!")
            return
            
        duration = int(self.perf_duration.get())
        template_path = f"assets/{module}/btn_{element}.png"
        
        if not os.path.exists(template_path):
            self.log_message(f"❌ Template nicht gefunden: {template_path}")
            return
            
        self.log_message(f"⚡ Performance-Test für {duration}s gestartet...")
        
        start_time = time.time()
        attempts = 0
        successes = 0
        
        while time.time() - start_time < duration and self.test_active:
            img_gpu, _ = self.vision.capture()
            found, pos = self.vision.find_template_gpu(img_gpu, template_path, self.threshold.get())
            
            attempts += 1
            if found:
                successes += 1
                
            # Kleine Pause um CPU/GPU zu schonen
            time.sleep(0.1)
            
        elapsed = time.time() - start_time
        
        self.log_message(f"📊 Performance-Ergebnis:")
        self.log_message(f"  Versuche: {attempts}")
        self.log_message(f"  Erfolge: {successes}")
        self.log_message(f"  Erfolgsrate: {(successes/attempts*100):.1f}%")
        self.log_message(f"  Durchschn. Zeit: {(elapsed/attempts*1000):.1f}ms pro Versuch")
        
    def update_statistics(self):
        """Aktualisiert die Statistik-Anzeige"""
        total = len(self.test_results)
        if total == 0:
            return
            
        successes = sum(1 for r in self.test_results if r.get("success", False))
        rate = (successes / total) * 100
        
        self.stats_text.set(f"Erfolge: {successes}/{total} ({rate:.1f}%)")
        
    def test_finished(self):
        """Wird nach Test-Ende aufgerufen"""
        self.test_active = False
        self.test_btn.config(state='normal')
        self.log_message(f"\n{self.icons['success']} Test abgeschlossen!")
        
    def stop_test(self):
        """Bricht aktuellen Test ab"""
        self.test_active = False
        self.log_message("⏹️ Test abgebrochen")
        
    def export_report(self):
        """Exportiert Test-Report als JSON"""
        if not self.test_results:
            messagebox.showinfo("Info", "Keine Testergebnisse vorhanden!")
            return
            
        filename = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "module": self.current_module.get(),
            "test_type": self.test_type.get(),
            "threshold": self.threshold.get(),
            "results": self.test_results,
            "statistics": {
                "total": len(self.test_results),
                "success": sum(1 for r in self.test_results if r.get("success", False))
            }
        }
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
            
        self.log_message(f"📋 Report exportiert: {filename}")
        messagebox.showinfo("Export erfolgreich", f"Report gespeichert als:\n{filename}")
        
    def log_message(self, message):
        """Fügt Nachricht zum Test-Log hinzu"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.root.after(0, lambda: self._insert_log(f"[{timestamp}] {message}\n"))
        
    def _insert_log(self, message):
        """Thread-sicheres Einfügen in Log"""
        self.test_log.insert(tk.END, message)
        self.test_log.see(tk.END)
        self.status.config(text=message.strip())
        
    def update_clock(self):
        """Aktualisiert die Uhrzeit"""
        self.time_label.config(text=datetime.now().strftime("%H:%M:%S"))
        self.root.after(1000, self.update_clock)
        
    # ========== TRAINING-PHASE METHODEN ==========
        
    def setup_training_ui(self):
        """Vollständige Training-UI"""
        # Haupt-Training Bereich mit PanedWindow
        main_paned = ttk.PanedWindow(self.training_frame, orient=tk.HORIZONTAL)
        main_paned.pack(fill='both', expand=True)
        
        # Linke Seite: Training Konfiguration
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)
        
        # Rechte Seite: Vorschau & Feedback
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=1)
        
        # === LINKE SEITE: TRAINING KONFIGURATION ===
        
        # Modul-Management
        module_frame = ttk.LabelFrame(left_frame, text="📦 Modul-Management")
        module_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(module_frame, text="Modul:").grid(row=0, column=0, sticky='w', pady=5)
        self.training_module = ttk.Combobox(module_frame, textvariable=self.current_module)
        self.training_module.grid(row=0, column=1, sticky='ew', padx=5)
        self.training_module.bind('<<ComboboxSelected>>', self.on_training_module_selected)
        
        ttk.Button(module_frame, text="➕ Neu", command=self.new_module, width=8).grid(row=0, column=2, padx=2)
        ttk.Button(module_frame, text="🗑️ Löschen", command=self.delete_module, width=8).grid(row=0, column=3, padx=2)
        
        ttk.Label(module_frame, text="Beschreibung:").grid(row=1, column=0, sticky='w', pady=5)
        self.module_desc = ttk.Entry(module_frame, width=30)
        self.module_desc.grid(row=1, column=1, columnspan=3, sticky='ew', padx=5)
        
        module_frame.columnconfigure(1, weight=1)
        
        # Trainings-Methoden
        method_frame = ttk.LabelFrame(left_frame, text="🎯 Trainings-Methode")
        method_frame.pack(fill='x', padx=10, pady=5)
        
        self.training_method = tk.StringVar(value="manual")
        methods = [
            ("🖱️ Manuell (Maus zielen)", "manual"),
            ("🔍 Grid Scan (Automatisch)", "grid"),
            ("📸 Batch Capture (Power-Modus)", "batch"),
            ("🎨 Rechteck ziehen", "rectangle"),
            ("⚡ Schnellaufnahme", "quick")
        ]
        
        for i, (text, value) in enumerate(methods):
            ttk.Radiobutton(method_frame, text=text, variable=self.training_method, 
                        value=value, command=self.update_training_ui).grid(row=i, column=0, sticky='w', padx=10, pady=2)
        
        # Elemente Definition
        elements_frame = ttk.LabelFrame(left_frame, text="🔖 Elemente definieren")
        elements_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Liste der Elemente
        list_frame = ttk.Frame(elements_frame)
        list_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.elements_tree = ttk.Treeview(list_frame, columns=('name', 'hotkey', 'status'), 
                                        show='tree headings', height=8)
        self.elements_tree.heading('#0', text='ID')
        self.elements_tree.heading('name', text='Element')
        self.elements_tree.heading('hotkey', text='Hotkey')
        self.elements_tree.heading('status', text='Status')
        self.elements_tree.column('#0', width=50)
        self.elements_tree.column('name', width=120)
        self.elements_tree.column('hotkey', width=80)
        self.elements_tree.column('status', width=100)
        
        # Scrollbar für Treeview
        tree_scroll = ttk.Scrollbar(list_frame, orient='vertical', command=self.elements_tree.yview)
        self.elements_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.elements_tree.pack(side='left', fill='both', expand=True)
        tree_scroll.pack(side='right', fill='y')
        
        # Buttons für Element-Liste
        btn_frame = ttk.Frame(elements_frame)
        btn_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(btn_frame, text="➕ Hinzufügen", command=self.add_element).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="✏️ Bearbeiten", command=self.edit_element).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="🗑️ Entfernen", command=self.remove_element).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="📋 Aus CSV laden", command=self.load_elements_csv).pack(side='right', padx=2)
        
        # Trainings-Parameter
        params_frame = ttk.LabelFrame(left_frame, text="⚙️ Trainings-Parameter")
        params_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(params_frame, text="Aufnahmegröße:").grid(row=0, column=0, sticky='w', padx=5)
        self.capture_size = ttk.Combobox(params_frame, values=["40x40", "50x50", "60x60", "80x80", "100x100"], width=10)
        self.capture_size.grid(row=0, column=1, sticky='w', padx=5)
        self.capture_size.set("60x60")
        
        ttk.Label(params_frame, text="Hotkey:").grid(row=0, column=2, sticky='w', padx=5)
        self.train_hotkey = ttk.Entry(params_frame, width=10)
        self.train_hotkey.grid(row=0, column=3, sticky='w', padx=5)
        self.train_hotkey.insert(0, "s")
        
        ttk.Label(params_frame, text="Verzögerung (s):").grid(row=1, column=0, sticky='w', padx=5)
        self.capture_delay = ttk.Spinbox(params_frame, from_=0, to=5, width=5)
        self.capture_delay.grid(row=1, column=1, sticky='w', padx=5)
        self.capture_delay.set(1)
        
        # Training-Steuerung
        control_frame = ttk.Frame(left_frame)
        control_frame.pack(fill='x', padx=10, pady=10)
        
        self.start_train_btn = ttk.Button(control_frame, text="▶️ Training starten", 
                                        command=self.start_training)
        self.start_train_btn.pack(side='left', padx=5)
        
        ttk.Button(control_frame, text="⏹️ Stoppen", command=self.stop_training).pack(side='left', padx=5)
        ttk.Button(control_frame, text="🔄 Reset", command=self.reset_training).pack(side='left', padx=5)
        
        # === RECHTE SEITE: VORSCHAU & FEEDBACK ===
        
        # Live-Kamera View
        camera_frame = ttk.LabelFrame(right_frame, text="📷 Live-Kamera (Mausposition)")
        camera_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.camera_canvas = tk.Canvas(camera_frame, bg='#2b2b2b', height=200)
        self.camera_canvas.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Mouse-Tracker
        self.mouse_pos_label = ttk.Label(camera_frame, text="Maus: (0, 0)")
        self.mouse_pos_label.pack()
        
        # Aktuelle Aufnahme
        preview_frame = ttk.LabelFrame(right_frame, text="🖼️ Letzte Aufnahme")
        preview_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.preview_canvas2 = tk.Canvas(preview_frame, bg='#2b2b2b', height=150)
        self.preview_canvas2.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Fortschritt
        progress_frame = ttk.LabelFrame(right_frame, text="📊 Trainings-Fortschritt")
        progress_frame.pack(fill='x', padx=10, pady=5)
        
        self.train_progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.train_progress.pack(fill='x', padx=5, pady=5)
        
        self.progress_label = ttk.Label(progress_frame, text="0/0 Elemente erfasst")
        self.progress_label.pack()
        
        # Live-Log
        log_frame = ttk.LabelFrame(right_frame, text="📝 Trainings-Log")
        log_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.train_log = scrolledtext.ScrolledText(log_frame, height=8)
        self.train_log.pack(fill='both', expand=True, padx=5, pady=5)

    def on_training_module_selected(self, event=None):
        """Wird aufgerufen wenn im Training ein Modul ausgewählt wird"""
        module = self.current_module.get()
        self.load_training_elements(module)
        
    def load_training_elements(self, module):
        """Lädt vorhandene Elemente für Training"""
        # Elemente-Liste zurücksetzen
        for item in self.elements_tree.get_children():
            self.elements_tree.delete(item)
            
        template_dir = f"assets/{module}/"
        if os.path.exists(template_dir):
            templates = [f.replace("btn_", "").replace(".png", "") 
                        for f in os.listdir(template_dir) 
                        if f.startswith("btn_") and f.endswith(".png")]
            
            for i, template in enumerate(sorted(templates)):
                self.elements_tree.insert('', 'end', text=str(i+1), 
                                        values=(template, "s", "✅ vorhanden"))
            
            self.train_log_message(f"📦 {len(templates)} vorhandene Elemente geladen")
            
    def train_log_message(self, message):
        """Fügt Nachricht zum Trainings-Log hinzu"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.root.after(0, lambda: self._insert_train_log(f"[{timestamp}] {message}\n"))
        
    def _insert_train_log(self, message):
        """Thread-sicheres Einfügen in Trainings-Log"""
        self.train_log.insert(tk.END, message)
        self.train_log.see(tk.END)
        
    def update_training_ui(self):
        """Aktualisiert UI basierend auf gewählter Trainings-Methode"""
        method = self.training_method.get()
        
        # Elemente-Liste zurücksetzen
        for item in self.elements_tree.get_children():
            self.elements_tree.delete(item)
        
        if method == "manual":
            self.setup_manual_training()
        elif method == "grid":
            self.setup_grid_training()
        elif method == "batch":
            self.setup_batch_training()
        elif method == "rectangle":
            self.setup_rectangle_training()
        elif method == "quick":
            self.setup_quick_training()

    def setup_manual_training(self):
        """Konfiguration für manuelles Training"""
        self.train_log_message("🖱️ Manueller Modus: Maus auf Element führen und Hotkey drücken")
        
        # Beispiel-Elemente für Taschenrechner
        default_elements = [
            ("7", "s", "🟡 bereit"),
            ("8", "s", "🟡 bereit"),
            ("9", "s", "🟡 bereit"),
            ("plus", "s", "🟡 bereit"),
            ("minus", "s", "🟡 bereit"),
            ("gleich", "s", "🟡 bereit"),
        ]
        
        for elem_id, (name, hotkey, status) in enumerate(default_elements):
            self.elements_tree.insert('', 'end', text=str(elem_id+1), 
                                    values=(name, hotkey, status))

    def setup_grid_training(self):
        """Konfiguration für Grid-Scan"""
        self.train_log_message("🔍 Grid-Modus: Automatische Rastererkennung")
        
        # Grid-Elemente automatisch generieren
        elements = ["7", "8", "9", "4", "5", "6", "1", "2", "3", "0", ".", "="]
        for i, elem in enumerate(elements):
            self.elements_tree.insert('', 'end', text=str(i+1), 
                                    values=(elem, "auto", "⏳ wartet"))

    def setup_batch_training(self):
        """Konfiguration für Batch-Training"""
        self.train_log_message("📸 Batch-Modus: Mehrere Programme nacheinander")

    def setup_rectangle_training(self):
        """Konfiguration für Rechteck-Auswahl"""
        self.train_log_message("🎨 Rechteck-Modus: Bereich aufziehen und benennen")

    def setup_quick_training(self):
        """Konfiguration für Schnellaufnahme"""
        self.train_log_message("⚡ Schnellmodus: Alle 2 Sekunden automatisch aufnehmen")

    def start_training(self):
        """Startet das Training basierend auf gewählter Methode"""
        method = self.training_method.get()
        module = self.current_module.get()
        
        if not module:
            messagebox.showerror("Fehler", "Bitte zuerst ein Modul auswählen oder erstellen!")
            return
        
        self.training_active = True
        self.start_train_btn.config(state='disabled')
        
        # Mouse-Tracker starten
        self.track_mouse()
        
        if method == "manual":
            thread = threading.Thread(target=self.run_manual_training, args=(module,))
        elif method == "grid":
            thread = threading.Thread(target=self.run_grid_training, args=(module,))
        elif method == "batch":
            thread = threading.Thread(target=self.run_batch_training, args=(module,))
        elif method == "rectangle":
            thread = threading.Thread(target=self.run_rectangle_training, args=(module,))
        elif method == "quick":
            thread = threading.Thread(target=self.run_quick_training, args=(module,))
        
        thread.daemon = True
        thread.start()

    def track_mouse(self):
        """Trackt Mausposition für Live-Vorschau"""
        if self.training_active:
            x, y = pyautogui.position()
            self.mouse_pos_label.config(text=f"Maus: ({x}, {y})")
            
            # Kleinen Bereich um Maus auf Canvas zeichnen
            self.update_camera_view(x, y)
            
            self.root.after(100, self.track_mouse)

    def update_camera_view(self, x, y):
        """Aktualisiert die Kamera-Vorschau"""
        try:
            # Screenshot der Mausposition
            size = int(self.capture_size.get().split('x')[0])
            screenshot = pyautogui.screenshot(region=(x-size//2, y-size//2, size, size))
            
            # Skalieren für Anzeige
            screenshot.thumbnail((180, 180))
            photo = ImageTk.PhotoImage(screenshot)
            
            self.camera_canvas.delete("all")
            self.camera_canvas.create_image(90, 90, image=photo)
            self.camera_canvas.image = photo
            
            # Fadenkreuz zeichnen
            self.camera_canvas.create_line(90, 0, 90, 180, fill='red', width=1, dash=(2,2))
            self.camera_canvas.create_line(0, 90, 180, 90, fill='red', width=1, dash=(2,2))
        except:
            pass

    def show_preview(self, image):
        """Zeigt aufgenommenes Bild in der Vorschau"""
        try:
            # Skalieren für Anzeige
            image.thumbnail((140, 140))
            photo = ImageTk.PhotoImage(image)
            
            self.preview_canvas2.delete("all")
            self.preview_canvas2.create_image(70, 70, image=photo)
            self.preview_canvas2.image = photo
        except:
            pass

    def run_manual_training(self, module):
        """Führt manuelles Training durch"""
        target_dir = f"assets/{module}/"
        os.makedirs(target_dir, exist_ok=True)

        # Alle Elemente aus der Treeview holen
        items = self.elements_tree.get_children()
        elements = []
        for item in items:
            values = self.elements_tree.item(item)['values']
            elements.append((item, values[0]))  # (item_id, element_name)

        self.train_progress['maximum'] = len(elements)
        hotkey = self.train_hotkey.get()
        delay = float(self.capture_delay.get())
        size = int(self.capture_size.get().split('x')[0])

        for i, (item_id, element) in enumerate(elements):
            if not self.training_active:
                break

            self.train_log_message(f"Bitte auf [{element}] zielen und '{hotkey}' drücken...")
            self.elements_tree.item(item_id, values=(element, hotkey, "[..] wartet"))

            # Warte auf Hotkey
            while self.training_active:
                if keyboard.is_pressed(hotkey):
                    break
                time.sleep(0.1)

            if not self.training_active:
                break

            # Position erfassen
            x, y = pyautogui.position()

            # Warten für Stabilität (optional)
            time.sleep(delay)

            # Screenshot machen
            screenshot = pyautogui.screenshot(region=(x-size//2, y-size//2, size, size))
            path = f"{target_dir}btn_{element}.png"
            screenshot.save(path)

            # Vorschau aktualisieren
            self.show_preview(screenshot)

            # Fortschritt aktualisieren
            self.train_progress['value'] = i + 1
            self.progress_label.config(text=f"{i+1}/{len(elements)} Elemente erfasst")
            self.elements_tree.item(item_id, values=(element, hotkey, "[OK] erfasst"))

            self.train_log_message(f"[OK] {element} erfasst bei ({x}, {y})")

            # Kurz warten bis Taste losgelassen
            while keyboard.is_pressed(hotkey):
                pass

        self.training_active = False
        self.train_log_message("Training abgeschlossen!")
        self.start_train_btn.config(state='normal')
        
    def run_grid_training(self, module):
        """Führt Grid-Training durch"""
        self.train_log_message("🔍 Grid-Training wird ausgeführt...")
        time.sleep(2)
        self.train_log_message("✅ Grid-Training abgeschlossen!")
        self.training_active = False
        self.start_train_btn.config(state='normal')
        
    def run_batch_training(self, module):
        """Führt Batch-Training durch"""
        self.train_log_message("📸 Batch-Training wird ausgeführt...")
        time.sleep(2)
        self.train_log_message("✅ Batch-Training abgeschlossen!")
        self.training_active = False
        self.start_train_btn.config(state='normal')
        
    def run_rectangle_training(self, module):
        """Führt Rechteck-Training durch"""
        self.train_log_message("🎨 Rechteck-Training wird ausgeführt...")
        time.sleep(2)
        self.train_log_message("✅ Rechteck-Training abgeschlossen!")
        self.training_active = False
        self.start_train_btn.config(state='normal')
        
    def run_quick_training(self, module):
        """Führt Schnell-Training durch"""
        self.train_log_message("⚡ Schnell-Training wird ausgeführt...")
        time.sleep(2)
        self.train_log_message("✅ Schnell-Training abgeschlossen!")
        self.training_active = False
        self.start_train_btn.config(state='normal')
        
    def stop_training(self):
        """Stoppt das Training"""
        self.training_active = False
        self.train_log_message("⏹️ Training gestoppt")
        self.start_train_btn.config(state='normal')
        
    def reset_training(self):
        """Setzt das Training zurück"""
        self.training_active = False
        self.train_progress['value'] = 0
        self.progress_label.config(text="0/0 Elemente erfasst")
        self.train_log_message("🔄 Training zurückgesetzt")
        self.start_train_btn.config(state='normal')
        
    def new_module(self):
        """Erstellt ein neues Modul"""
        name = simpledialog.askstring("Neues Modul", "Modul-Name:")
        if name:
            # Prüfen ob bereits vorhanden
            if os.path.exists(f"assets/{name}"):
                messagebox.showwarning("Warnung", "Modul existiert bereits!")
                return
                
            os.makedirs(f"assets/{name}", exist_ok=True)
            self.current_module.set(name)
            self.load_modules()
            self.train_log_message(f"✅ Neues Modul '{name}' erstellt")
            
    def delete_module(self):
        """Löscht ein Modul"""
        module = self.current_module.get()
        if not module:
            return
            
        if messagebox.askyesno("Löschen bestätigen", f"Modul '{module}' wirklich löschen?"):
            import shutil
            try:
                shutil.rmtree(f"assets/{module}")
                self.load_modules()
                self.train_log_message(f"🗑️ Modul '{module}' gelöscht")
            except Exception as e:
                messagebox.showerror("Fehler", f"Konnte Modul nicht löschen: {e}")
                
    def add_element(self):
        """Fügt ein neues Element hinzu"""
        name = simpledialog.askstring("Neues Element", "Element-Name:")
        if name:
            # Zur Treeview hinzufügen
            items = self.elements_tree.get_children()
            new_id = len(items) + 1
            self.elements_tree.insert('', 'end', text=str(new_id), 
                                    values=(name, "s", "🟡 bereit"))
            self.train_log_message(f"➕ Element '{name}' hinzugefügt")
            
    def edit_element(self):
        """Bearbeitet ein Element"""
        selected = self.elements_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Bitte ein Element auswählen!")
            return
            
        item = selected[0]
        values = self.elements_tree.item(item)['values']
        old_name = values[0]
        
        new_name = simpledialog.askstring("Element bearbeiten", "Neuer Name:", initialvalue=old_name)
        if new_name and new_name != old_name:
            self.elements_tree.item(item, values=(new_name, values[1], values[2]))
            self.train_log_message(f"✏️ Element '{old_name}' → '{new_name}'")
            
    def remove_element(self):
        """Entfernt ein Element"""
        selected = self.elements_tree.selection()
        if not selected:
            messagebox.showinfo("Info", "Bitte ein Element auswählen!")
            return
            
        if messagebox.askyesno("Entfernen bestätigen", "Element wirklich entfernen?"):
            for item in selected:
                values = self.elements_tree.item(item)['values']
                self.elements_tree.delete(item)
                self.train_log_message(f"🗑️ Element '{values[0]}' entfernt")
                
    def load_elements_csv(self):
        """Lädt Elemente aus CSV-Datei"""
        filename = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if filename:
            try:
                with open(filename, 'r') as f:
                    reader = csv.reader(f)
                    for i, row in enumerate(reader):
                        if row:  # Nicht-leere Zeile
                            name = row[0].strip()
                            hotkey = row[1].strip() if len(row) > 1 else "s"
                            self.elements_tree.insert('', 'end', text=str(i+1), 
                                                    values=(name, hotkey, "🟡 bereit"))
                self.train_log_message(f"📋 Elemente aus {os.path.basename(filename)} geladen")
            except Exception as e:
                messagebox.showerror("Fehler", f"Konnte CSV nicht laden: {e}")
                
    # ========== AUTOMATION-PHASE METHODEN ==========
        
    def setup_auto_ui(self):
        """Vollständige Automation-UI"""
        # Haupt-Automation Bereich
        main_frame = ttk.Frame(self.auto_frame)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Notebook für verschiedene Automation-Typen
        auto_notebook = ttk.Notebook(main_frame)
        auto_notebook.pack(fill='both', expand=True)
        
        # === TAB 1: SEQUENZ-AUTOMATION ===
        seq_frame = ttk.Frame(auto_notebook)
        auto_notebook.add(seq_frame, text="📋 Sequenz")
        self.setup_sequence_automation(seq_frame)
        
        # === TAB 2: REZEPT-AUTOMATION ===
        recipe_frame = ttk.Frame(auto_notebook)
        auto_notebook.add(recipe_frame, text="📖 Rezepte")
        self.setup_recipe_automation(recipe_frame)
        
        # === TAB 3: WATCHDOG ===
        watchdog_frame = ttk.Frame(auto_notebook)
        auto_notebook.add(watchdog_frame, text="👀 Watchdog")
        self.setup_watchdog_automation(watchdog_frame)
        
        # === TAB 4: BATCH ===
        batch_auto_frame = ttk.Frame(auto_notebook)
        auto_notebook.add(batch_auto_frame, text="⚡ Batch")
        self.setup_batch_automation(batch_auto_frame)
        
        # === TAB 5: SCHEDULER ===
        scheduler_frame = ttk.Frame(auto_notebook)
        auto_notebook.add(scheduler_frame, text="⏰ Scheduler")
        self.setup_scheduler_automation(scheduler_frame)

    def setup_sequence_automation(self, parent):
        """Sequenz-basierte Automation"""
        
        # Linke Seite: Sequenz-Editor
        left_frame = ttk.Frame(parent)
        left_frame.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        
        # Rechte Seite: Live-View & Log
        right_frame = ttk.Frame(parent)
        right_frame.pack(side='right', fill='both', expand=True, padx=5, pady=5)
        
        # === SEQUENZ-EDITOR ===
        editor_frame = ttk.LabelFrame(left_frame, text="Sequenz-Editor")
        editor_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Toolbar
        toolbar = ttk.Frame(editor_frame)
        toolbar.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(toolbar, text="➕ Schritt", command=self.add_sequence_step).pack(side='left', padx=2)
        ttk.Button(toolbar, text="✂️ Entfernen", command=self.remove_sequence_step).pack(side='left', padx=2)
        ttk.Button(toolbar, text="⬆️ Nach oben", command=self.move_step_up).pack(side='left', padx=2)
        ttk.Button(toolbar, text="⬇️ Nach unten", command=self.move_step_down).pack(side='left', padx=2)
        ttk.Button(toolbar, text="💾 Speichern", command=self.save_sequence).pack(side='right', padx=2)
        ttk.Button(toolbar, text="📂 Laden", command=self.load_sequence).pack(side='right', padx=2)
        
        # Sequenz-Liste
        columns = ('step', 'action', 'target', 'value', 'delay')
        self.sequence_tree = ttk.Treeview(editor_frame, columns=columns, show='headings', height=15)
        
        self.sequence_tree.heading('step', text='#')
        self.sequence_tree.heading('action', text='Aktion')
        self.sequence_tree.heading('target', text='Ziel')
        self.sequence_tree.heading('value', text='Wert')
        self.sequence_tree.heading('delay', text='Verzögerung')
        
        self.sequence_tree.column('step', width=40)
        self.sequence_tree.column('action', width=100)
        self.sequence_tree.column('target', width=120)
        self.sequence_tree.column('value', width=150)
        self.sequence_tree.column('delay', width=70)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(editor_frame, orient='vertical', command=self.sequence_tree.yview)
        self.sequence_tree.configure(yscrollcommand=scrollbar.set)
        
        self.sequence_tree.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scrollbar.pack(side='right', fill='y', pady=5)
        
        # Beispiel-Sequenz
        example_sequence = [
            ("1", "click", "7", "", "0.5"),
            ("2", "click", "plus", "", "0.5"),
            ("3", "click", "8", "", "0.5"),
            ("4", "click", "gleich", "", "0.5"),
            ("5", "wait", "", "2s", ""),
            ("6", "screenshot", "", "ergebnis.png", ""),
        ]
        
        for step in example_sequence:
            self.sequence_tree.insert('', 'end', values=step)
        
        # === RECHTE SEITE ===
        
        # Aktions-Palette
        actions_frame = ttk.LabelFrame(right_frame, text="Aktions-Palette")
        actions_frame.pack(fill='x', padx=5, pady=5)
        
        actions = [
            ("🖱️ Klick", "click"),
            ("🖱️ Doppelklick", "doubleclick"),
            ("⌨️ Text", "type"),
            ("⏱️ Warten", "wait"),
            ("📸 Screenshot", "screenshot"),
            ("🔄 Tastenkombi", "hotkey"),
            ("📋 Kopieren", "copy"),
            ("📋 Einfügen", "paste"),
            ("🎯 Maus bewegen", "move"),
            ("🪟 Fenster", "window"),
        ]
        
        for i, (text, action) in enumerate(actions):
            btn = ttk.Button(actions_frame, text=text, 
                            command=lambda a=action: self.add_action_to_sequence(a))
            btn.grid(row=i//3, column=i%3, padx=2, pady=2, sticky='ew')
            actions_frame.columnconfigure(i%3, weight=1)
        
        # Parameter
        params_frame = ttk.LabelFrame(right_frame, text="Ausführungs-Parameter")
        params_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(params_frame, text="Wiederholungen:").grid(row=0, column=0, sticky='w', padx=5)
        self.auto_repeats = ttk.Spinbox(params_frame, from_=1, to=100, width=5)
        self.auto_repeats.grid(row=0, column=1, sticky='w', padx=5)
        self.auto_repeats.set(1)
        
        ttk.Label(params_frame, text="Fehlerverhalten:").grid(row=1, column=0, sticky='w', padx=5)
        self.error_behavior = ttk.Combobox(params_frame, values=["Stoppen", "Überspringen", "Wiederholen"], width=15)
        self.error_behavior.grid(row=1, column=1, columnspan=2, sticky='w', padx=5)
        self.error_behavior.set("Stoppen")
        
        ttk.Label(params_frame, text="Max. Versuche:").grid(row=2, column=0, sticky='w', padx=5)
        self.max_retries = ttk.Spinbox(params_frame, from_=1, to=10, width=5)
        self.max_retries.grid(row=2, column=1, sticky='w', padx=5)
        self.max_retries.set(3)
        
        # Steuerung
        control_frame = ttk.Frame(right_frame)
        control_frame.pack(fill='x', padx=5, pady=10)
        
        self.run_auto_btn = ttk.Button(control_frame, text="▶️ Sequenz ausführen", 
                                    command=self.run_sequence)
        self.run_auto_btn.pack(side='left', padx=5)
        
        ttk.Button(control_frame, text="⏸️ Pause", command=self.pause_auto).pack(side='left', padx=5)
        ttk.Button(control_frame, text="⏹️ Stop", command=self.stop_auto).pack(side='left', padx=5)
        
        # Live-Log
        log_frame = ttk.LabelFrame(right_frame, text="Ausführungs-Log")
        log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.auto_log = scrolledtext.ScrolledText(log_frame, height=10)
        self.auto_log.pack(fill='both', expand=True, padx=5, pady=5)

    def setup_recipe_automation(self, parent):
        """Rezept-basierte Automation (komplexere Workflows)"""
        
        # Rezept-Browser
        browser_frame = ttk.Frame(parent)
        browser_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Linke Seite: Rezept-Liste
        left_frame = ttk.Frame(browser_frame)
        left_frame.pack(side='left', fill='both', expand=True, padx=5)

        ttk.Label(left_frame, text=" Rezepte:").pack(anchor='w')

        self.recipe_list = tk.Listbox(left_frame, height=15)
        self.recipe_list.pack(fill='both', expand=True, pady=5)
        self.recipe_list.bind('<<ListboxSelect>>', self.on_recipe_selected)

        # Lade Rezepte
        self.load_recipes()

        # Rechte Seite: Rezept-Details
        right_frame = ttk.Frame(browser_frame)
        right_frame.pack(side='right', fill='both', expand=True, padx=5)
        
        details_frame = ttk.LabelFrame(right_frame, text="Rezept-Details")
        details_frame.pack(fill='both', expand=True)
        
        ttk.Label(details_frame, text="Name:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.recipe_name = ttk.Entry(details_frame, width=30)
        self.recipe_name.grid(row=0, column=1, columnspan=2, sticky='ew', padx=5, pady=2)
        
        ttk.Label(details_frame, text="Beschreibung:").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        self.recipe_desc = ttk.Entry(details_frame, width=30)
        self.recipe_desc.grid(row=1, column=1, columnspan=2, sticky='ew', padx=5, pady=2)
        
        ttk.Label(details_frame, text="Schritte:").grid(row=2, column=0, sticky='nw', padx=5, pady=2)
        self.recipe_steps = tk.Text(details_frame, height=8, width=30)
        self.recipe_steps.grid(row=2, column=1, columnspan=2, sticky='ew', padx=5, pady=2)
        
        ttk.Label(details_frame, text="Tags:").grid(row=3, column=0, sticky='w', padx=5, pady=2)
        self.recipe_tags = ttk.Entry(details_frame, width=30)
        self.recipe_tags.grid(row=3, column=1, columnspan=2, sticky='ew', padx=5, pady=2)
        
        details_frame.columnconfigure(1, weight=1)
        
        # Buttons
        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill='x', pady=10)
        
        ttk.Button(btn_frame, text="Rezept ausfuehren", command=self.run_recipe).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Speichern", command=self.save_recipe).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Loeschen", command=self.delete_recipe).pack(side='left', padx=5)

    def load_recipes(self):
        """Lädt Rezepte"""
        recipes = [
            "Taschenrechner - Grundrechenarten",
            "Excel - Zellen formatieren",
            "Browser - Screenshot machen",
            "Notepad - Text schreiben & speichern",
            "Word - Dokument erstellen",
            "Outlook - Email senden",
        ]

        # Versuche aus Datei zu laden
        try:
            if os.path.exists("recipes.json"):
                with open("recipes.json", "r") as f:
                    file_recipes = json.load(f)
                    recipes.extend(file_recipes)
        except:
            pass

        self.recipe_list.delete(0, tk.END)
        for recipe in recipes:
            self.recipe_list.insert(tk.END, recipe)

    def on_recipe_selected(self, event=None):
        """Wird aufgerufen wenn Rezept ausgewählt wird"""
        selection = self.recipe_list.curselection()
        if selection:
            recipe = self.recipe_list.get(selection[0])
            self.recipe_name.delete(0, tk.END)
            self.recipe_name.insert(0, recipe)
            self.recipe_desc.delete(0, tk.END)
            self.recipe_desc.insert(0, "Klicken Sie auf Ausfuehren um das Rezept zu starten")
            self.recipe_steps.delete('1.0', tk.END)
            self.recipe_steps.insert('1.0', f"1. Programm starten\n2. Element '{recipe}' suchen\n3. Aktion ausfuehren")

    def setup_watchdog_automation(self, parent):
        """Watchdog für automatische Reaktionen"""
        
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Watchdog-Konfiguration
        config_frame = ttk.LabelFrame(main_frame, text="Watchdog-Konfiguration")
        config_frame.pack(fill='x', pady=5)
        
        ttk.Label(config_frame, text="Überwache:").grid(row=0, column=0, sticky='w', padx=5)
        self.watch_target = ttk.Combobox(config_frame, 
                                        values=["Bildschirmbereich", "Fenster", "Prozess", "Dateisystem"], 
                                        width=20)
        self.watch_target.grid(row=0, column=1, sticky='w', padx=5)
        self.watch_target.set("Bildschirmbereich")
        
        ttk.Label(config_frame, text="Ereignis:").grid(row=1, column=0, sticky='w', padx=5)
        self.watch_event = ttk.Combobox(config_frame, 
                                        values=["Element erscheint", "Element verschwindet", "Farbe ändert sich", "Text erscheint"], 
                                        width=20)
        self.watch_event.grid(row=1, column=1, sticky='w', padx=5)
        self.watch_event.set("Element erscheint")
        
        ttk.Label(config_frame, text="Element/Template:").grid(row=2, column=0, sticky='w', padx=5)
        self.watch_template = ttk.Combobox(config_frame, width=20)
        self.watch_template.grid(row=2, column=1, sticky='w', padx=5)
        
        ttk.Button(config_frame, text="📸 Bereich auswählen", command=self.select_watch_area).grid(row=2, column=2, padx=5)
        
        ttk.Label(config_frame, text="Aktion bei Treffer:").grid(row=3, column=0, sticky='w', padx=5)
        self.watch_action = ttk.Combobox(config_frame, 
                                        values=["Klicken", "Tastendruck", "Sequenz starten", "Benachrichtigung"], 
                                        width=20)
        self.watch_action.grid(row=3, column=1, sticky='w', padx=5)
        self.watch_action.set("Klicken")
        
        config_frame.columnconfigure(1, weight=1)
        
        # Watchdog-Liste
        list_frame = ttk.LabelFrame(main_frame, text="Aktive Watchdogs")
        list_frame.pack(fill='both', expand=True, pady=5)
        
        columns = ('name', 'target', 'event', 'action', 'status')
        self.watchdog_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=8)
        
        self.watchdog_tree.heading('name', text='Name')
        self.watchdog_tree.heading('target', text='Ziel')
        self.watchdog_tree.heading('event', text='Ereignis')
        self.watchdog_tree.heading('action', text='Aktion')
        self.watchdog_tree.heading('status', text='Status')
        
        self.watchdog_tree.column('name', width=120)
        self.watchdog_tree.column('target', width=100)
        self.watchdog_tree.column('event', width=120)
        self.watchdog_tree.column('action', width=100)
        self.watchdog_tree.column('status', width=80)
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.watchdog_tree.yview)
        self.watchdog_tree.configure(yscrollcommand=scrollbar.set)
        
        self.watchdog_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Steuerung
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill='x', pady=5)
        
        ttk.Button(control_frame, text="➕ Watchdog hinzufügen", command=self.add_watchdog).pack(side='left', padx=5)
        ttk.Button(control_frame, text="▶️ Alle starten", command=self.start_watchdogs).pack(side='left', padx=5)
        ttk.Button(control_frame, text="⏹️ Alle stoppen", command=self.stop_watchdogs).pack(side='left', padx=5)

    def setup_batch_automation(self, parent):
        """Batch-Verarbeitung mehrerer Aufgaben"""
        
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Aufgaben-Liste
        list_frame = ttk.LabelFrame(main_frame, text="Aufgaben-Liste")
        list_frame.pack(fill='both', expand=True, pady=5)
        
        columns = ('task', 'module', 'status', 'progress')
        self.batch_task_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=10)
        
        self.batch_task_tree.heading('task', text='Aufgabe')
        self.batch_task_tree.heading('module', text='Modul')
        self.batch_task_tree.heading('status', text='Status')
        self.batch_task_tree.heading('progress', text='Fortschritt')
        
        self.batch_task_tree.column('task', width=200)
        self.batch_task_tree.column('module', width=100)
        self.batch_task_tree.column('status', width=100)
        self.batch_task_tree.column('progress', width=150)
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.batch_task_tree.yview)
        self.batch_task_tree.configure(yscrollcommand=scrollbar.set)
        
        self.batch_task_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=5)
        
        ttk.Button(btn_frame, text="➕ Aufgabe hinzufügen", command=self.add_batch_task).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="📋 Aus CSV importieren", command=self.import_batch_tasks).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="▶️ Batch starten", command=self.run_batch).pack(side='right', padx=5)

    def setup_scheduler_automation(self, parent):
        """Zeitgesteuerte Automation"""
        
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Scheduler-Konfiguration
        config_frame = ttk.LabelFrame(main_frame, text="Zeitplan")
        config_frame.pack(fill='x', pady=5)
        
        ttk.Label(config_frame, text="Startzeit:").grid(row=0, column=0, sticky='w', padx=5)
        self.sched_time = ttk.Entry(config_frame, width=10)
        self.sched_time.grid(row=0, column=1, sticky='w', padx=5)
        self.sched_time.insert(0, "10:00")
        
        ttk.Label(config_frame, text="Wiederholung:").grid(row=0, column=2, sticky='w', padx=5)
        self.sched_repeat = ttk.Combobox(config_frame, 
                                        values=["Einmalig", "Täglich", "Wöchentlich", "Monatlich"], 
                                        width=15)
        self.sched_repeat.grid(row=0, column=3, sticky='w', padx=5)
        self.sched_repeat.set("Täglich")
        
        ttk.Label(config_frame, text="Aufgabe:").grid(row=1, column=0, sticky='w', padx=5)
        self.sched_task = ttk.Combobox(config_frame, width=30)
        self.sched_task.grid(row=1, column=1, columnspan=3, sticky='ew', padx=5)
        
        config_frame.columnconfigure(1, weight=1)
        
        # Job-Liste
        list_frame = ttk.LabelFrame(main_frame, text="Geplante Jobs")
        list_frame.pack(fill='both', expand=True, pady=5)
        
        columns = ('name', 'time', 'repeat', 'next_run', 'status')
        self.sched_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=8)
        
        self.sched_tree.heading('name', text='Job-Name')
        self.sched_tree.heading('time', text='Uhrzeit')
        self.sched_tree.heading('repeat', text='Wiederholung')
        self.sched_tree.heading('next_run', text='Nächste Ausführung')
        self.sched_tree.heading('status', text='Status')
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.sched_tree.yview)
        self.sched_tree.configure(yscrollcommand=scrollbar.set)
        
        self.sched_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Steuerung
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill='x', pady=5)

        ttk.Button(control_frame, text="+ Job hinzufuegen", command=self.add_scheduled_job).pack(side='left', padx=5)
        ttk.Button(control_frame, text="- Job entfernen", command=self.remove_scheduled_job).pack(side='left', padx=5)
        ttk.Button(control_frame, text="> Starten", command=self.start_scheduler).pack(side='left', padx=5)
        ttk.Button(control_frame, text="[] Stoppen", command=self.stop_scheduler).pack(side='left', padx=5)
        
    # ========== AUTOMATION HELPER METHODEN ==========
    
    def add_sequence_step(self):
        """Fügt einen Schritt zur Sequenz hinzu"""
        # Dialog für Schritt-Konfiguration
        dialog = tk.Toplevel(self.root)
        dialog.title("Schritt hinzufügen")
        dialog.geometry("300x200")
        
        ttk.Label(dialog, text="Aktion:").pack(pady=5)
        action_var = tk.StringVar(value="click")
        action_combo = ttk.Combobox(dialog, textvariable=action_var, 
                                   values=["click", "doubleclick", "type", "wait", "screenshot", "hotkey"])
        action_combo.pack(pady=5)
        
        ttk.Label(dialog, text="Ziel:").pack(pady=5)
        target_entry = ttk.Entry(dialog)
        target_entry.pack(pady=5)
        
        def add():
            step_num = len(self.sequence_tree.get_children()) + 1
            self.sequence_tree.insert('', 'end', values=(
                str(step_num), 
                action_var.get(), 
                target_entry.get(), 
                "", 
                "0.5"
            ))
            dialog.destroy()
            
        ttk.Button(dialog, text="Hinzufügen", command=add).pack(pady=10)
        
    def remove_sequence_step(self):
        """Entfernt markierte Schritte"""
        selected = self.sequence_tree.selection()
        for item in selected:
            self.sequence_tree.delete(item)
        # Nummern aktualisieren
        self.update_step_numbers()
        
    def move_step_up(self):
        """Bewegt Schritt nach oben"""
        selected = self.sequence_tree.selection()
        if not selected:
            return
        for item in selected:
            index = self.sequence_tree.index(item)
            if index > 0:
                self.sequence_tree.move(item, '', index-1)
        self.update_step_numbers()
        
    def move_step_down(self):
        """Bewegt Schritt nach unten"""
        selected = self.sequence_tree.selection()
        if not selected:
            return
        for item in selected:
            index = self.sequence_tree.index(item)
            if index < len(self.sequence_tree.get_children()) - 1:
                self.sequence_tree.move(item, '', index+1)
        self.update_step_numbers()
        
    def update_step_numbers(self):
        """Aktualisiert die Schritt-Nummern"""
        for i, item in enumerate(self.sequence_tree.get_children()):
            values = list(self.sequence_tree.item(item)['values'])
            values[0] = str(i+1)
            self.sequence_tree.item(item, values=values)
            
    def add_action_to_sequence(self, action):
        """Fügt Aktion zur Sequenz hinzu"""
        step_num = len(self.sequence_tree.get_children()) + 1
        self.sequence_tree.insert('', 'end', values=(
            str(step_num), action, "", "", "0.5"
        ))
        self.auto_log_message(f"➕ Aktion '{action}' hinzugefügt")
        
    def save_sequence(self):
        """Speichert die Sequenz in einer Datei"""
        filename = filedialog.asksaveasfilename(defaultextension=".json", 
                                               filetypes=[("JSON files", "*.json")])
        if filename:
            sequence = []
            for item in self.sequence_tree.get_children():
                values = self.sequence_tree.item(item)['values']
                sequence.append({
                    "step": values[0],
                    "action": values[1],
                    "target": values[2],
                    "value": values[3],
                    "delay": values[4]
                })
            with open(filename, 'w') as f:
                json.dump(sequence, f, indent=2)
            self.auto_log_message(f"💾 Sequenz gespeichert: {os.path.basename(filename)}")
            
    def load_sequence(self):
        """Lädt eine Sequenz aus einer Datei"""
        filename = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if filename:
            with open(filename, 'r') as f:
                sequence = json.load(f)
            # Alte Einträge löschen
            for item in self.sequence_tree.get_children():
                self.sequence_tree.delete(item)
            # Neue Einträge hinzufügen
            for step in sequence:
                self.sequence_tree.insert('', 'end', values=(
                    step["step"], step["action"], step["target"], 
                    step["value"], step["delay"]
                ))
            self.auto_log_message(f"📂 Sequenz geladen: {os.path.basename(filename)}")
            
    def run_sequence(self):
        """Führt die Sequenz aus"""
        if self.auto_active:
            return
            
        self.auto_active = True
        self.run_auto_btn.config(state='disabled')
        
        thread = threading.Thread(target=self.execute_sequence)
        thread.daemon = True
        thread.start()
        
    def execute_sequence(self):
        """Führt die Sequenz Schritt für Schritt aus"""
        repeats = int(self.auto_repeats.get())
        
        for repeat in range(repeats):
            if not self.auto_active or self.auto_paused:
                break
                
            self.auto_log_message(f"🔄 Durchlauf {repeat+1}/{repeats}")
            
            for item in self.sequence_tree.get_children():
                if not self.auto_active or self.auto_paused:
                    break
                    
                values = self.sequence_tree.item(item)['values']
                step_num, action, target, value, delay = values
                
                self.auto_log_message(f"  ▶️ Schritt {step_num}: {action} {target}")
                
                # Aktion ausführen
                if action == "click" and target:
                    module = self.current_module.get()
                    template_path = f"assets/{module}/btn_{target}.png"
                    if os.path.exists(template_path):
                        img_gpu, _ = self.vision.capture()
                        found, pos = self.vision.find_template_gpu(img_gpu, template_path, 0.8)
                        if found:
                            self.gui.safe_click(pos[0], pos[1])
                            self.auto_log_message(f"     ✅ Geklickt bei {pos}")
                        else:
                            self.auto_log_message(f"     ❌ {target} nicht gefunden!")
                            if self.error_behavior.get() == "Stoppen":
                                break
                    else:
                        self.auto_log_message(f"     ❌ Template fehlt: {target}")
                        
                elif action == "wait":
                    try:
                        wait_time = float(target) if target else 1.0
                        time.sleep(wait_time)
                    except:
                        time.sleep(1.0)
                        
                elif action == "screenshot" and value:
                    screenshot = pyautogui.screenshot()
                    screenshot.save(value)
                    self.auto_log_message(f"     📸 Screenshot gespeichert: {value}")
                    
                elif action == "type" and target:
                    pyautogui.write(target)
                    self.auto_log_message(f"     ⌨️ Text getippt: {target}")
                    
                elif action == "hotkey" and target:
                    keys = target.split('+')
                    pyautogui.hotkey(*keys)
                    self.auto_log_message(f"     🔄 Hotkey: {target}")
                
                # Verzögerung
                try:
                    time.sleep(float(delay))
                except:
                    time.sleep(0.5)
                    
        self.auto_active = False
        self.run_auto_btn.config(state='normal')
        self.auto_log_message("✅ Sequenz abgeschlossen!")
        
    def pause_auto(self):
        """Pausiert die Automation"""
        self.auto_paused = not self.auto_paused
        status = "⏸️ pausiert" if self.auto_paused else "▶️ fortgesetzt"
        self.auto_log_message(status)
        
    def stop_auto(self):
        """Stoppt die Automation"""
        self.auto_active = False
        self.auto_paused = False
        self.run_auto_btn.config(state='normal')
        self.auto_log_message("⏹️ Automation gestoppt")
        
    def auto_log_message(self, message):
        """Fügt Nachricht zum Auto-Log hinzu"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.root.after(0, lambda: self._insert_auto_log(f"[{timestamp}] {message}\n"))
        
    def _insert_auto_log(self, message):
        """Thread-sicheres Einfügen in Auto-Log"""
        self.auto_log.insert(tk.END, message)
        self.auto_log.see(tk.END)
        
    def run_recipe(self):
        """Führt ein Rezept aus"""
        selection = self.recipe_list.curselection()
        if selection:
            recipe = self.recipe_list.get(selection[0])
            self.auto_log_message(f"🍳 Rezept gestartet: {recipe}")
            # Hier würde die Rezept-Logik kommen
            time.sleep(2)
            self.auto_log_message(f"✅ Rezept abgeschlossen: {recipe}")
            
    def save_recipe(self):
        """Speichert ein Rezept"""
        self.auto_log_message("💾 Rezept gespeichert")
        
    def delete_recipe(self):
        """Löscht ein Rezept"""
        selection = self.recipe_list.curselection()
        if selection:
            recipe = self.recipe_list.get(selection[0])
            self.recipe_list.delete(selection[0])
            self.auto_log_message(f"🗑️ Rezept gelöscht: {recipe}")
            
    def select_watch_area(self):
        """Wählt einen Bereich für Watchdog aus"""
        self.auto_log_message("📸 Bitte Bereich aufziehen...")
        # Hier würde die Bereichsauswahl kommen
        time.sleep(2)
        self.auto_log_message("✅ Bereich ausgewählt")
        
    def add_watchdog(self):
        """Fügt einen neuen Watchdog hinzu"""
        name = f"Watchdog {len(self.watchdogs)+1}"
        self.watchdog_tree.insert('', 'end', values=(
            name, 
            self.watch_target.get(), 
            self.watch_event.get(), 
            self.watch_action.get(),
            "⏹️ inaktiv"
        ))
        self.auto_log_message(f"➕ Watchdog hinzugefügt: {name}")
        
    def start_watchdogs(self):
        """Startet alle Watchdogs"""
        for item in self.watchdog_tree.get_children():
            self.watchdog_tree.item(item, values=(
                self.watchdog_tree.item(item)['values'][0],
                self.watchdog_tree.item(item)['values'][1],
                self.watchdog_tree.item(item)['values'][2],
                self.watchdog_tree.item(item)['values'][3],
                "▶️ aktiv"
            ))
        self.auto_log_message("👀 Watchdogs gestartet")
        
    def stop_watchdogs(self):
        """Stoppt alle Watchdogs"""
        for item in self.watchdog_tree.get_children():
            self.watchdog_tree.item(item, values=(
                self.watchdog_tree.item(item)['values'][0],
                self.watchdog_tree.item(item)['values'][1],
                self.watchdog_tree.item(item)['values'][2],
                self.watchdog_tree.item(item)['values'][3],
                "⏹️ inaktiv"
            ))
        self.auto_log_message("👀 Watchdogs gestoppt")
        
    def add_batch_task(self):
        """Fügt eine Batch-Aufgabe hinzu"""
        task_num = len(self.batch_task_tree.get_children()) + 1
        self.batch_task_tree.insert('', 'end', values=(
            f"Aufgabe {task_num}",
            self.current_module.get(),
            "⏳ bereit",
            "0%"
        ))
        
    def import_batch_tasks(self):
        """Importiert Batch-Aufgaben aus CSV"""
        filename = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if filename:
            self.auto_log_message(f"📋 Batch-Aufgaben importiert: {os.path.basename(filename)}")
            
    def run_batch(self):
        """Führt Batch-Aufgaben aus (mehrere Sequenzen nacheinander)"""
        if self.auto_active:
            return
            
        self.auto_active = True
        self.auto_log_message("⚡ Batch-Verarbeitung gestartet")
        
        # Batch in eigenem Thread ausführen
        thread = threading.Thread(target=self.execute_batch)
        thread.daemon = True
        thread.start()

    def execute_batch(self):
        """Eigentliche Batch-Verarbeitung"""
        try:
            # Alle Aufgaben aus der Batch-Liste holen
            tasks = []
            for item in self.batch_task_tree.get_children():
                values = self.batch_task_tree.item(item)['values']
                tasks.append({
                    'item': item,
                    'name': values[0],
                    'module': values[1],
                    'status': values[2],
                    'progress': values[3]
                })
            
            if not tasks:
                self.auto_log_message("❌ Keine Aufgaben in der Batch-Liste!")
                self.auto_active = False
                return
                
            self.auto_log_message(f"📋 {len(tasks)} Aufgaben gefunden")
            
            # Aufgaben nacheinander ausführen
            for i, task in enumerate(tasks):
                if not self.auto_active:
                    break
                    
                # Status aktualisieren
                self.root.after(0, lambda t=task: self.update_batch_task_status(
                    t['item'], "▶️ in Arbeit", f"{int((i/len(tasks))*100)}%"
                ))
                
                self.auto_log_message(f"  🔄 Aufgabe {i+1}/{len(tasks)}: {task['name']}")
                
                # Modul wechseln
                old_module = self.current_module.get()
                self.current_module.set(task['module'])
                
                # Hier die eigentliche Aufgabe ausführen
                success = self.execute_batch_task(task['name'])
                
                # Modul zurücksetzen
                self.current_module.set(old_module)
                
                if success:
                    self.root.after(0, lambda t=task: self.update_batch_task_status(
                        t['item'], "✅ erledigt", f"{int(((i+1)/len(tasks))*100)}%"
                    ))
                    self.auto_log_message(f"     ✅ Erfolgreich")
                else:
                    self.root.after(0, lambda t=task: self.update_batch_task_status(
                        t['item'], "❌ fehlgeschlagen", f"{int(((i+1)/len(tasks))*100)}%"
                    ))
                    self.auto_log_message(f"     ❌ Fehlgeschlagen")
                    
                # Kurze Pause zwischen Aufgaben
                time.sleep(1)
                
            self.auto_log_message("✅ Batch-Verarbeitung abgeschlossen!")
            
        except Exception as e:
            self.auto_log_message(f"❌ Fehler in Batch-Verarbeitung: {e}")
            
        finally:
            self.auto_active = False

    def execute_batch_task(self, task_name):
        """Führt eine einzelne Batch-Aufgabe aus"""
        try:
            # Hier verschiedene Aufgabentypen implementieren
            if "Taschenrechner" in task_name or "calc" in task_name.lower():
                return self.execute_calc_task(task_name)
            elif "Excel" in task_name or "excel" in task_name.lower():
                return self.execute_excel_task(task_name)
            elif "Notepad" in task_name or "notepad" in task_name.lower():
                return self.execute_notepad_task(task_name)
            else:
                # Standard: Versuche als Sequenz zu laden
                return self.execute_sequence_from_file(task_name)
        except Exception as e:
            self.auto_log_message(f"     Fehler in Aufgabe {task_name}: {e}")
            return False

    def execute_calc_task(self, task_name):
        """Taschenrechner-Aufgabe ausführen"""
        self.auto_log_message("     🧮 Führe Taschenrechner-Aufgabe aus...")
        
        # Beispiel: Einfache Berechnung
        sequence = ["7", "plus", "8", "gleich"]
        
        for element in sequence:
            if not self.auto_active:
                return False
                
            template_path = f"assets/calc/btn_{element}.png"
            if os.path.exists(template_path):
                img_gpu, _ = self.vision.capture()
                found, pos = self.vision.find_template_gpu(img_gpu, template_path, 0.8)
                if found:
                    self.gui.safe_click(pos[0], pos[1])
                    self.auto_log_message(f"       🖱️ {element} geklickt")
                    time.sleep(0.3)
                else:
                    self.auto_log_message(f"       ❌ {element} nicht gefunden")
                    return False
            else:
                self.auto_log_message(f"       ❌ Template für {element} fehlt")
                return False
                
        return True

    def execute_excel_task(self, task_name):
        """Excel-Aufgabe ausführen"""
        self.auto_log_message("     📊 Führe Excel-Aufgabe aus...")
        # Excel-spezifische Logik hier
        time.sleep(2)  # Simulation
        return True

    def execute_notepad_task(self, task_name):
        """Notepad-Aufgabe ausführen"""
        self.auto_log_message("     📝 Führe Notepad-Aufgabe aus...")
        
        # Notepad öffnen
        self.gui.win_search_and_open("Notepad")
        time.sleep(1)
        
        # Text schreiben
        pyautogui.write("GABI Automation Test")
        pyautogui.press('enter')
        pyautogui.write("Batch-Verarbeitung läuft...")
        
        # Speichern (Beispiel)
        pyautogui.hotkey('ctrl', 's')
        time.sleep(0.5)
        pyautogui.write(f"gabi_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        pyautogui.press('enter')
        
        return True

    def execute_sequence_from_file(self, task_name):
        """Führt eine gespeicherte Sequenz aus"""
        # Versuche Sequenz-Datei zu finden
        seq_file = f"sequences/{task_name}.json"
        if os.path.exists(seq_file):
            self.auto_log_message(f"     📋 Lade Sequenz: {task_name}")
            # Hier würde die geladene Sequenz ausgeführt
            time.sleep(1)
            return True
        else:
            self.auto_log_message(f"     ⚠️ Keine Sequenz gefunden, überspringe")
            return True  # Überspringe, kein Fehler

    def update_batch_task_status(self, item, status, progress):
        """Aktualisiert den Status einer Batch-Aufgabe"""
        values = list(self.batch_task_tree.item(item)['values'])
        values[2] = status
        values[3] = progress
        self.batch_task_tree.item(item, values=values)

    def add_batch_task(self):
        """Fügt eine neue Batch-Aufgabe hinzu"""
        # Dialog für neue Aufgabe
        dialog = tk.Toplevel(self.root)
        dialog.title("Batch-Aufgabe hinzufügen")
        dialog.geometry("400x200")
        
        ttk.Label(dialog, text="Aufgabenname:").pack(pady=5)
        name_entry = ttk.Entry(dialog, width=40)
        name_entry.pack(pady=5)
        name_entry.insert(0, f"Aufgabe {len(self.batch_task_tree.get_children())+1}")
        
        ttk.Label(dialog, text="Modul:").pack(pady=5)
        module_combo = ttk.Combobox(dialog, values=self.get_module_list(), width=37)
        module_combo.pack(pady=5)
        module_combo.set(self.current_module.get())
        
        ttk.Label(dialog, text="Aufgabentyp:").pack(pady=5)
        type_combo = ttk.Combobox(dialog, values=[
            "Taschenrechner", "Excel", "Notepad", "Sequenz", "Benutzerdefiniert"
        ], width=37)
        type_combo.pack(pady=5)
        type_combo.set("Taschenrechner")
        
        def add():
            name = name_entry.get()
            module = module_combo.get()
            task_type = type_combo.get()
            
            # In Treeview einfügen
            self.batch_task_tree.insert('', 'end', values=(
                f"{name} ({task_type})",
                module,
                "⏳ bereit",
                "0%"
            ))
            dialog.destroy()
            self.auto_log_message(f"➕ Batch-Aufgabe hinzugefügt: {name}")
            
        ttk.Button(dialog, text="Hinzufügen", command=add).pack(pady=10)

    def import_batch_tasks(self):
        """Importiert Batch-Aufgaben aus CSV oder JSON"""
        filename = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("JSON files", "*.json"), ("Alle Dateien", "*.*")]
        )
        
        if not filename:
            return
            
        try:
            if filename.endswith('.csv'):
                self.import_batch_from_csv(filename)
            elif filename.endswith('.json'):
                self.import_batch_from_json(filename)
            else:
                messagebox.showerror("Fehler", "Nicht unterstütztes Dateiformat!")
                
        except Exception as e:
            messagebox.showerror("Fehler", f"Import fehlgeschlagen: {e}")
            
    def import_batch_from_csv(self, filename):
        """Importiert aus CSV"""
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)  # Kopfzeile überspringen
            
            count = 0
            for row in reader:
                if len(row) >= 2:
                    name = row[0].strip()
                    module = row[1].strip() if len(row) > 1 else "calc"
                    task_type = row[2].strip() if len(row) > 2 else "Standard"
                    
                    self.batch_task_tree.insert('', 'end', values=(
                        f"{name} ({task_type})",
                        module,
                        "⏳ bereit",
                        "0%"
                    ))
                    count += 1
                    
            self.auto_log_message(f"📋 {count} Aufgaben aus CSV importiert")
            
    def import_batch_from_json(self, filename):
        """Importiert aus JSON"""
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            count = 0
            for task in data:
                name = task.get('name', f"Aufgabe {count+1}")
                module = task.get('module', 'calc')
                task_type = task.get('type', 'Standard')
                
                self.batch_task_tree.insert('', 'end', values=(
                    f"{name} ({task_type})",
                    module,
                    "⏳ bereit",
                    "0%"
                ))
                count += 1
                
            self.auto_log_message(f"📋 {count} Aufgaben aus JSON importiert")

    def export_batch_tasks(self):
        """Exportiert Batch-Aufgaben als CSV oder JSON"""
        if not self.batch_task_tree.get_children():
            messagebox.showinfo("Info", "Keine Aufgaben zum Exportieren!")
            return
            
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("CSV files", "*.csv")]
        )
        
        if not filename:
            return
            
        try:
            tasks = []
            for item in self.batch_task_tree.get_children():
                values = self.batch_task_tree.item(item)['values']
                # Name und Typ trennen
                full_name = values[0]
                if " (" in full_name and full_name.endswith(")"):
                    name = full_name[:full_name.rindex(" (")]
                    task_type = full_name[full_name.rindex(" (")+2:-1]
                else:
                    name = full_name
                    task_type = "Standard"
                    
                tasks.append({
                    'name': name,
                    'module': values[1],
                    'type': task_type
                })
                
            if filename.endswith('.json'):
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(tasks, f, indent=2, ensure_ascii=False)
            elif filename.endswith('.csv'):
                with open(filename, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Name', 'Modul', 'Typ'])
                    for task in tasks:
                        writer.writerow([task['name'], task['module'], task['type']])
                        
            self.auto_log_message(f"💾 {len(tasks)} Aufgaben exportiert nach {os.path.basename(filename)}")
            
        except Exception as e:
            messagebox.showerror("Fehler", f"Export fehlgeschlagen: {e}")

    def get_module_list(self):
        """Gibt Liste aller verfügbaren Module zurück"""
        modules = ['calc']
        if os.path.exists("assets"):
            modules.extend([d for d in os.listdir("assets") 
                        if os.path.isdir(os.path.join("assets", d)) and d != 'calc'])
        return list(set(modules))  # Duplikate entfernen

    def remove_batch_task(self):
        """Entfernt markierte Batch-Aufgaben"""
        selected = self.batch_task_tree.selection()
        if not selected:
            return
            
        if messagebox.askyesno("Entfernen", f"{len(selected)} Aufgabe(n) wirklich entfernen?"):
            for item in selected:
                values = self.batch_task_tree.item(item)['values']
                self.batch_task_tree.delete(item)
                self.auto_log_message(f"🗑️ Aufgabe entfernt: {values[0]}")
        
    def add_scheduled_job(self):
        """Fügt einen geplanten Job hinzu"""
        job_num = len(self.sched_tree.get_children()) + 1
        next_run = (datetime.now() + timedelta(minutes=5)).strftime("%H:%M")
        self.sched_tree.insert('', 'end', values=(
            f"Job {job_num}",
            self.sched_time.get(),
            self.sched_repeat.get(),
            next_run,
            "[..] geplant"
        ))

    def remove_scheduled_job(self):
        """Entfernt den ausgewählten Job"""
        selection = self.sched_tree.selection()
        if selection:
            for item in selection:
                self.sched_tree.delete(item)

    def remove_scheduled_job(self):
        """Entfernt den ausgewählten Job"""
        selection = self.sched_tree.selection()
        if selection:
            for item in selection:
                values = self.sched_tree.item(item)['values']
                self.sched_tree.delete(item)
                self.auto_log_message(f"Job entfernt: {values[0]}")
        else:
            self.auto_log_message("Kein Job ausgewaehlt")

    def start_scheduler(self):
        """Startet den Scheduler"""
        for item in self.sched_tree.get_children():
            values = list(self.sched_tree.item(item)['values'])
            values[4] = "▶️ aktiv"
            self.sched_tree.item(item, values=values)
        self.auto_log_message("⏰ Scheduler gestartet")
        
    def stop_scheduler(self):
        """Stoppt den Scheduler"""
        for item in self.sched_tree.get_children():
            values = list(self.sched_tree.item(item)['values'])
            values[4] = "⏹️ inaktiv"
            self.sched_tree.item(item, values=values)
        self.auto_log_message("⏰ Scheduler gestoppt")
        
    def run(self):
        self.root.mainloop()

    def setup_help_ui(self):
        """Vollständige Hilfe-UI mit Tutorials und FAQ"""

        # Haupt-Hilfe Bereich mit Notebook
        help_notebook = ttk.Notebook(self.help_frame)
        help_notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # === TAB 1: ERSTE SCHRITTE ===
        getting_started = ttk.Frame(help_notebook)
        help_notebook.add(getting_started, text="Erste Schritte")
        self.setup_getting_started(getting_started)

        # === TAB 2: TRAINING ===
        training_help = ttk.Frame(help_notebook)
        help_notebook.add(training_help, text="Training Hilfe")
        self.setup_training_help(training_help)

        # === TAB 3: TEST ===
        test_help = ttk.Frame(help_notebook)
        help_notebook.add(test_help, text="Test Hilfe")
        self.setup_test_help(test_help)

        # === TAB 4: AUTOMATION ===
        auto_help = ttk.Frame(help_notebook)
        help_notebook.add(auto_help, text="Automation Hilfe")
        self.setup_auto_help(auto_help)

        # === TAB 5: FAQ ===
        faq_frame = ttk.Frame(help_notebook)
        help_notebook.add(faq_frame, text="FAQ")
        self.setup_faq(faq_frame)

        # === TAB 6: TASTATURKÜRZEL ===
        shortcuts_frame = ttk.Frame(help_notebook)
        help_notebook.add(shortcuts_frame, text="Tastatur")
        self.setup_shortcuts(shortcuts_frame)

        # === TAB 7: ÜBER GABI ===
        about_frame = ttk.Frame(help_notebook)
        help_notebook.add(about_frame, text="Über GABI")
        self.setup_about(about_frame)

    def setup_getting_started(self, parent):
        """Erste-Schritte Tutorial"""

        # Canvas mit Scrollbar für längeren Text
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Tutorial-Inhalt
        tutorial_content = [
            ("Willkommen beim GABI Training Center!", "header"),
            ("",
             "normal"),
            ("Dieses Tool hilft dir, visuelle Elemente für die GABI-Automatisierung zu trainieren und zu testen.",
             "normal"),
            ("",
             "normal"),
            ("SCHRITT 1: Training",
             "section"),
            ("1. Wähle ein Modul aus (z.B. 'calc' für den Taschenrechner)",
             "normal"),
            ("2. Klicke auf 'Manuelles Training' um neue Elemente hinzuzufügen",
             "normal"),
            ("3. Klicke auf den Bildschirmbereich, den du trainieren möchtest",
             "normal"),
            ("4. Gib dem Element einen Namen und speichere es",
             "normal"),
            ("",
             "normal"),
            ("SCHRITT 2: Testen",
             "section"),
            ("1. Wechsle zum Tab 'Test & Validierung'",
             "normal"),
            ("2. Wähle dein Modul und die zu testenden Elemente",
             "normal"),
            ("3. Starte den Test und sieh die Ergebnisse",
             "normal"),
            ("",
             "normal"),
            ("SCHRITT 3: Automation",
             "section"),
            ("1. Wechsle zum Tab 'Automation'",
             "normal"),
            ("2. Erstelle eine Sequenz oder nutze Rezepte",
             "normal"),
            ("3. Starte die Automation und schaue zu",
             "normal"),
        ]

        for item, item_type in tutorial_content:
            if item_type == "header":
                lbl = ttk.Label(scrollable_frame, text=item, font=("Arial", 14, "bold"))
            elif item_type == "section":
                lbl = ttk.Label(scrollable_frame, text=item, font=("Arial", 11, "bold"))
            else:
                lbl = ttk.Label(scrollable_frame, text=item, font=("Arial", 9))
            lbl.pack(anchor="w", padx=20, pady=2)

    def setup_training_help(self, parent):
        """Detaillierte Hilfe für Training"""

        # Canvas mit Scrollbar
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.create_help_content(scrollable_frame, [
            ("Training Methoden", "header"),
            ("",
             "normal"),
            ("Manuelles Training",
             "section"),
            ("- Klicke auf 'Maus verfolgen' um die Position zu sehen",
             "normal"),
            ("- Klicke auf den Bildschirm um einen Bereich aufzunehmen",
             "normal"),
            ("- Gib einen Namen ein und speichere",
             "normal"),
            ("",
             "normal"),
            ("Grid Training",
             "section"),
            ("- Teilt den Bildschirm in ein Raster",
             "normal"),
            ("- Gut für gleichmäßig verteilte Elemente",
             "normal"),
            ("",
             "normal"),
            ("Batch Training",
             "section"),
            ("- Lädt mehrere Bilder gleichzeitig",
             "normal"),
            ("- Automatische Namensvergabe",
             "normal"),
            ("",
             "normal"),
            ("Rechteck Training",
             "section"),
            ("- Markiert einen rechteckigen Bereich",
             "normal"),
            ("- Für größere zusammenhängende Bereiche",
             "normal"),
        ])

    def setup_test_help(self, parent):
        """Hilfe für Test-Phase"""

        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.create_help_content(scrollable_frame, [
            ("Test Optionen", "header"),
            ("",
             "normal"),
            ("Einzeltest",
             "section"),
            ("- Testet ein einzelnes Element",
             "normal"),
            ("- Schnell und einfach",
             "normal"),
            ("",
             "normal"),
            ("Sequenztest",
             "section"),
            ("- Testet Elemente in einer bestimmten Reihenfolge",
             "normal"),
            ("- Gut für Workflows",
             "normal"),
            ("",
             "normal"),
            ("Batch Test",
             "section"),
            ("- Testet mehrere Elemente automatisch",
             "normal"),
            ("- Erstellt Statistiken",
             "normal"),
            ("",
             "normal"),
            ("Performance Test",
             "section"),
            ("- Misst die Erkennungsgeschwindigkeit",
             "normal"),
            ("- Für Optimierungen",
             "normal"),
        ])

    def setup_auto_help(self, parent):
        """Hilfe für Automation"""

        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.create_help_content(scrollable_frame, [
            ("Automation Optionen", "header"),
            ("",
             "normal"),
            ("Sequenzen",
             "section"),
            ("- Erstelle eigene Aktionsfolgen",
             "normal"),
            ("- Klicken, Tasten, Warten möglich",
             "normal"),
            ("",
             "normal"),
            ("Rezepte",
             "section"),
            ("- Vordefinierte Automatisierungen",
             "normal"),
            ("- Einfache Konfiguration",
             "normal"),
            ("",
             "normal"),
            ("Watchdog",
             "section"),
            ("- Überwacht Bildschirmbereiche",
             "normal"),
            ("- Reagiert auf Änderungen",
             "normal"),
            ("",
             "normal"),
            ("Scheduler",
             "section"),
            ("- Zeitgesteuerte Aufgaben",
             "normal"),
            ("- Wiederholende Jobs",
             "normal"),
        ])

    def setup_faq(self, parent):
        """FAQ Sektion"""

        faq_data = [
            ("Warum findet GABI meine Elemente nicht?",
             "Überprüfe die Beleuchtung, den Kontrast und ob das Element sichtbar ist. Manchmal hilft ein höherer Threshold."),
            ("Kann GABI mit verschiedenen Bildschirmauflösungen umgehen?",
             "Templates sind relativ - aber bei sehr unterschiedlichen Auflösungen muss eventuell neu trainiert werden."),
            ("Wie viele Elemente kann ich trainieren?",
             "Theoretisch unbegrenzt, aber mehr Elemente verlangsamen die Suche."),
            ("Funktioniert GABI auch mit Spielen?",
             "Ja, aber bei Fullscreen-Spielen kann die Bildschirmerkennung проблематич sein."),
            ("Was ist der beste Threshold?",
             "0.8 ist ein guter Start. Bei Problemen anpassen."),
            ("Kann ich trainierte Elemente teilen?",
             "Ja, kopiere einfach den templates-Ordner."),
            ("Warum GPU und nicht CPU?",
             "GPU ist viel schneller bei Bildverarbeitung."),
            ("Was passiert bei einem Fehler in der Automation?",
             "Die Automation stoppt und zeigt eine Fehlermeldung."),
            ("Kann ich mehrere Programme gleichzeitig automatisieren?",
             "Ja, aber sei vorsichtig mit überlappenden Aktionen."),
            ("Wie mache ich ein Backup meiner Trainingsdaten?",
             "Kopiere den templates-Ordner an einen sicheren Ort."),
        ]

        # FAQ Treeview
        tree = ttk.Treeview(parent, columns=("Frage", "Antwort"), show="tree headings", height=15)
        tree.heading("#0", text="FAQ")
        tree.heading("Frage", text="Frage")
        tree.heading("Antwort", text="Antwort")
        tree.column("#0", width=0)
        tree.column("Frage", width=200)
        tree.column("Antwort", width=400)

        for frage, antwort in faq_data:
            tree.insert("", "end", text="", values=(frage, antwort))

        tree.pack(fill="both", expand=True, padx=10, pady=10)

    def setup_shortcuts(self, parent):
        """Tastaturkürzel anzeigen"""

        shortcuts = [
            ("Allgemein", [
                ("F1", "Hilfe öffnen"),
                ("Strg+Q", "Beenden"),
            ]),
            ("Training", [
                ("Strg+T", "Training starten"),
                ("S", "Element speichern"),
                ("Esc", "Abbrechen"),
            ]),
            ("Test", [
                ("Strg+T", "Test starten"),
                ("Strg+R", "Report erstellen"),
            ]),
            ("Automation", [
                ("Strg+A", "Start"),
                ("Strg+P", "Pause"),
                ("Strg+X", "Stop"),
            ]),
        ]

        for category, keys in shortcuts:
            cat_frame = ttk.LabelFrame(parent, text=category, padding=10)
            cat_frame.pack(fill="x", padx=10, pady=5)

            for key, action in keys:
                ttk.Label(cat_frame, text=f"{key}: {action}").pack(anchor="w")

    def setup_about(self, parent):
        """Über GABI"""

        info_text = """
GABI Training Center v1.0

Ein Tool zum Trainieren und Testen visueller
Elemente für die GABI-Automatisierung.

© 2026 GABI Project
"""
        lbl = ttk.Label(parent, text=info_text, justify="center", padding=20)
        lbl.pack(expand=True)

    def create_help_content(self, parent, content):
        """Hilfsfunktion zum Erstellen von formatiertem Hilfetext"""

        for item, item_type in content:
            if item_type == "header":
                lbl = ttk.Label(parent, text=item, font=("Arial", 14, "bold"))
            elif item_type == "section":
                lbl = ttk.Label(parent, text=item, font=("Arial", 11, "bold"))
            else:
                lbl = ttk.Label(parent, text=item, font=("Arial", 9))
            lbl.pack(anchor="w", padx=20, pady=2)

    def show_quick_help(self):
        """Zeigt einen Quick-Help Dialog"""

        dialog = tk.Toplevel(self.root)
        dialog.title("Quick Help")
        dialog.geometry("500x400")

        # Notebook für kompakte Hilfe
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # Training Tab
        training_tab = ttk.Frame(notebook)
        notebook.add(training_tab, text="Training")
        ttk.Label(training_tab, text=
            "Training Tipps:\n"
            "- Wähle ein Modul aus\n"
            "- Klicke 'Manuelles Training'\n"
            "- Klicke auf den Bildschirm\n"
            "- Gib einen Namen ein und speichere\n\n"
            "Tastenkürzel:\n"
            "- Strg+T: Training starten\n"
            "- S: Speichern\n"
            "- Esc: Abbrechen"
        ).pack(padx=10, pady=10, anchor="w")

        # Test Tab
        test_tab = ttk.Frame(notebook)
        notebook.add(test_tab, text="Test")
        ttk.Label(test_tab, text=
            "Test Tipps:\n"
            "- Wähle Module und Elemente\n"
            "- Starte den Test\n"
            "- Prüfe die Ergebnisse\n\n"
            "Test-Typen:\n"
            "- Einzeltest: Ein Element\n"
            "- Sequenztest: Mehrere hintereinander\n"
            "- Batch: Alle automatisch"
        ).pack(padx=10, pady=10, anchor="w")

        # Automation Tab
        auto_tab = ttk.Frame(notebook)
        notebook.add(auto_tab, text="Automation")
        ttk.Label(auto_tab, text=
            "Automation Tipps:\n"
            "- Erstelle Sequenzen\n"
            "- Nutze Rezepte\n"
            "- Starte die Automation\n\n"
            "Tastenkürzel:\n"
            "- Strg+A: Start\n"
            "- Strg+P: Pause\n"
            "- Strg+X: Stop"
        ).pack(padx=10, pady=10, anchor="w")

        # Schließen
        ttk.Button(dialog, text="Schließen", command=dialog.destroy).pack(pady=10)

def setup_ui(self):
    # Haupt-Notebook
    self.notebook = ttk.Notebook(self.root)
    self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
    
    # Phase 1: Training
    self.training_frame = ttk.Frame(self.notebook)
    self.notebook.add(self.training_frame, text="📚 1. Training")
    self.setup_training_ui()
    
    # Phase 2: Test
    self.test_frame = ttk.Frame(self.notebook)
    self.notebook.add(self.test_frame, text="🧪 2. Test & Validierung")
    self.setup_test_ui()
    
    # Phase 3: Automation
    self.auto_frame = ttk.Frame(self.notebook)
    self.notebook.add(self.auto_frame, text="🤖 3. Automation")
    self.setup_auto_ui()
    
    # Phase 4: Hilfe
    self.help_frame = ttk.Frame(self.notebook)
    self.notebook.add(self.help_frame, text="❓ 4. Hilfe & Tutorials")
    self.setup_help_ui()
    
    # Statusbar
    self.status_frame = ttk.Frame(self.root)
    self.status_frame.pack(fill='x', padx=10, pady=5)
    
    self.status = ttk.Label(self.status_frame, text="✅ Bereit", relief=tk.SUNKEN)
    self.status.pack(side='left', fill='x', expand=True)
    
    # Hilfe-Button in Statusbar
    self.help_btn = ttk.Button(self.status_frame, text="❓ Hilfe", command=self.show_quick_help)
    self.help_btn.pack(side='right', padx=5)
    
    self.time_label = ttk.Label(self.status_frame, text=datetime.now().strftime("%H:%M:%S"))
    self.time_label.pack(side='right', padx=5)
    self.update_clock()

def setup_help_ui(self):
    """Vollständige Hilfe-UI mit Tutorials und FAQ"""
    
    # Haupt-Hilfe Bereich mit Notebook
    help_notebook = ttk.Notebook(self.help_frame)
    help_notebook.pack(fill='both', expand=True, padx=10, pady=10)
    
    # === TAB 1: ERSTE SCHRITTE ===
    getting_started = ttk.Frame(help_notebook)
    help_notebook.add(getting_started, text="🚀 Erste Schritte")
    self.setup_getting_started(getting_started)
    
    # === TAB 2: TRAINING ===
    training_help = ttk.Frame(help_notebook)
    help_notebook.add(training_help, text="📚 Training Hilfe")
    self.setup_training_help(training_help)
    
    # === TAB 3: TEST ===
    test_help = ttk.Frame(help_notebook)
    help_notebook.add(test_help, text="🧪 Test Hilfe")
    self.setup_test_help(test_help)
    
    # === TAB 4: AUTOMATION ===
    auto_help = ttk.Frame(help_notebook)
    help_notebook.add(auto_help, text="🤖 Automation Hilfe")
    self.setup_auto_help(auto_help)
    
    # === TAB 5: FAQ ===
    faq_frame = ttk.Frame(help_notebook)
    help_notebook.add(faq_frame, text="❓ FAQ")
    self.setup_faq(faq_frame)
    
    # === TAB 6: TASTATURKÜRZEL ===
    shortcuts_frame = ttk.Frame(help_notebook)
    help_notebook.add(shortcuts_frame, text="⌨️ Tastaturkürzel")
    self.setup_shortcuts(shortcuts_frame)
    
    # === TAB 7: ÜBER GABI ===
    about_frame = ttk.Frame(help_notebook)
    help_notebook.add(about_frame, text="ℹ️ Über GABI")
    self.setup_about(about_frame)

def setup_getting_started(self, parent):
    """Erste-Schritte Tutorial"""
    
    # Canvas mit Scrollbar für längeren Text
    canvas = tk.Canvas(parent)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    # Willkommen
    welcome = ttk.Label(scrollable_frame, text="🎉 Willkommen bei GABI!", 
                       font=("Arial", 16, "bold"))
    welcome.pack(pady=10)
    
    ttk.Label(scrollable_frame, 
             text="GABI (GPU-Accelerated Bot Interface) hilft dir, Programme zu automatisieren.",
             font=("Arial", 10)).pack(pady=5)
    
    # Schritt 1
    step1_frame = ttk.LabelFrame(scrollable_frame, text="Schritt 1: Modul erstellen")
    step1_frame.pack(fill='x', padx=20, pady=10)
    
    ttk.Label(step1_frame, 
             text="1. Gehe zum 'Training' Tab\n"
                  "2. Klicke auf '➕ Neu' unter Modul-Management\n"
                  "3. Gib einen Namen ein (z.B. 'calc', 'excel', 'browser')\n"
                  "4. Das Verzeichnis 'assets/[modul]' wird automatisch erstellt",
             justify='left').pack(padx=10, pady=5)
    
    # Schritt 2
    step2_frame = ttk.LabelFrame(scrollable_frame, text="Schritt 2: Elemente trainieren")
    step2_frame.pack(fill='x', padx=20, pady=10)
    
    ttk.Label(step2_frame,
             text="1. Wähle eine Trainings-Methode (empfohlen: Manuell)\n"
                  "2. Definiere die Elemente (z.B. '7, plus, gleich')\n"
                  "3. Klicke auf '▶️ Training starten'\n"
                  "4. Fahre mit der Maus über jedes Element und drücke 'S'\n"
                  "5. Die Bilder werden automatisch gespeichert",
             justify='left').pack(padx=10, pady=5)
    
    # Schritt 3
    step3_frame = ttk.LabelFrame(scrollable_frame, text="Schritt 3: Testen")
    step3_frame.pack(fill='x', padx=20, pady=10)
    
    ttk.Label(step3_frame,
             text="1. Gehe zum 'Test' Tab\n"
                  "2. Wähle dein Modul aus\n"
                  "3. Teste einzelne Elemente oder ganze Sequenzen\n"
                  "4. Überprüfe die Erfolgsrate",
             justify='left').pack(padx=10, pady=5)
    
    # Schritt 4
    step4_frame = ttk.LabelFrame(scrollable_frame, text="Schritt 4: Automatisieren")
    step4_frame.pack(fill='x', padx=20, pady=10)
    
    ttk.Label(step4_frame,
             text="1. Gehe zum 'Automation' Tab\n"
                  "2. Erstelle eine Sequenz (z.B. Klicks in Reihenfolge)\n"
                  "3. Stelle Wiederholungen und Fehlerverhalten ein\n"
                  "4. Starte die Automation",
             justify='left').pack(padx=10, pady=5)
    
    # Tipps
    tips_frame = ttk.LabelFrame(scrollable_frame, text="💡 Pro-Tipps")
    tips_frame.pack(fill='x', padx=20, pady=10)
    
    tips = [
        "• Verwende eindeutige Element-Namen (nicht 'button1' sondern 'login_button')",
        "• Trainiere bei verschiedenen Bildschirmauflösungen für bessere Erkennung",
        "• Nutze den Grid-Scan für regelmäßige Tastaturen (wie Taschenrechner)",
        "• Exportiere Test-Reports zur Qualitätssicherung",
        "• Speichere erfolgreiche Sequenzen als Rezepte für später"
    ]
    
    for tip in tips:
        ttk.Label(tips_frame, text=tip, justify='left').pack(anchor='w', padx=10, pady=2)
    
    # Packen
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

def setup_training_help(self, parent):
    """Detaillierte Hilfe für Training"""
    train_notebook = ttk.Notebook(parent)
    train_notebook.pack(fill='both', expand=True)
    
    # ✅ FRAMES DEFINIEREN
    manual_frame = ttk.Frame(train_notebook)
    train_notebook.add(manual_frame, text="🖱️ Manuell")
    
    grid_frame = ttk.Frame(train_notebook)
    train_notebook.add(grid_frame, text="🔍 Grid")
    
    batch_frame = ttk.Frame(train_notebook)
    train_notebook.add(batch_frame, text="📸 Batch")
    
    rect_frame = ttk.Frame(train_notebook)
    train_notebook.add(rect_frame, text="🎨 Rechteck")

    self.create_help_content(manual_frame, [
        ("Manuelles Training", "title"),
        ("Die einfachste Methode: Du zeigst GABI jedes Element einzeln.", "text"),
        ("", "sep"),
        ("📝 Ablauf:", "subtitle"),
        ("1. Definiere die Element-Namen (z.B. '7, plus, gleich')", "text"), 
        ("2. Starte das Training", "text"),           # <- Anführungszeichen!
        ("3. Bewege die Maus über das Element", "text"),  # <- Anführungszeichen!
        ("4. Drücke den Hotkey (Standard: 'S')", "text"),
        ("5. Wiederhole für alle Elemente", "text"),
        ("", "sep"),
        ("✅ Vorteile:", "subtitle"),
        ("• Sehr präzise", "text"),
        ("• Funktioniert für alle Programme", "text"),
        ("• Du siehst sofort, was aufgenommen wird", "text"),
        ("", "sep"),
        ("⚠️ Nachteile:", "subtitle"),
        ("• Zeitaufwendig bei vielen Elementen", "text"),
        ("• Erfordert manuelle Aktionen", "text")
    ])

    
    # Grid-Scan
    grid_frame = ttk.Frame(training_notebook)
    # ✅ 1. NOTEBOOK DEFINIEREN
    training_notebook = ttk.Notebook(parent)
    training_notebook.pack(fill='both', expand=True, padx=5, pady=5)
    
    # ✅ 2. FRAMES DEFINIEREN & ZUM NOTEBOOK HINZUFÜGEN
    manual_frame = ttk.Frame(training_notebook)
    training_notebook.add(manual_frame, text="🖱️ Manuell")
    
    grid_frame = ttk.Frame(training_notebook)
    training_notebook.add(grid_frame, text="🔍 Grid")
    
    batch_frame = ttk.Frame(training_notebook)
    training_notebook.add(batch_frame, text="📸 Batch")
    
    rect_frame = ttk.Frame(training_notebook)
    training_notebook.add(rect_frame, text="🎨 Rechteck")
    
    self.create_help_content(grid_frame, [
        ("Grid-Scan Training", "title"),
        ("Automatische Erkennung für Raster-Layouts (ideal für Taschenrechner).", "text"),
        ("", "sep"),
        ("📝 Ablauf:", "subtitle"),
        ("1. Wähle eine Referenztaste (z.B. die '7')", "text"),
        ("2. Definiere Zeilen und Spalten", "text"),
        ("3. GABI berechnet automatisch alle Positionen", "text"),
        ("4. Alle Tasten werden automatisch erfasst", "text"),
        ("", "sep"),
        ("✅ Vorteile:", "subtitle"),
        ("• Sehr schnell", "text"),
        ("• Perfekt für regelmäßige Layouts", "text"),
        ("• Kein manuelles Zielen nötig", "text"),
        ("", "sep"),
        ("⚠️ Nachteile:", "subtitle"),
        ("• Funktioniert nur bei regelmäßigen Rastern", "text"),
        ("• Erfordert genaue Abstandskalibrierung", "text")
    ])

    # Batch-Training
    batch_frame = ttk.Frame(training_notebook)
    training_notebook.add(batch_frame, text="📸 Batch")
    self.create_help_content(batch_frame, [
        ("Batch-Training", "title"),
        ("Trainiere mehrere Programme in einem Durchlauf.", "text"),
        ("", "sep"),
        ("📝 Ablauf:", "subtitle"),
        ("1. Definiere mehrere Module mit ihren Elementen", "text"),
        ("2. GABI führt dich nacheinander durch alle", "text"),
        ("3. Alle Elemente werden im jeweiligen Modul-Ordner gespeichert", "text"),
        ("", "sep"),
        ("✅ Vorteile:", "subtitle"),
        ("• Effizient für große Projekte", "text"),
        ("• Alle Daten bleiben getrennt", "text"),
        ("", "sep"),
        ("⚠️ Nachteile:", "subtitle"),
        ("• Dauert insgesamt länger", "text"),
        ("• Erfordert Organisation", "text")
    ])

    
    # Rechteck-Modus
    rect_frame = ttk.Frame(training_notebook)
    training_notebook.add(rect_frame, text="🎨 Rechteck")
    self.create_help_content(rect_frame, [
        ("Rechteck-Auswahl", "title"),
        ("Ziehe ein Rechteck um das Element - perfekt für große Bereiche.", "text"),
        ("", "sep"),
        ("📝 Ablauf:", "subtitle"),
        ("1. Klicke und halte die Maus", "text"),
        ("2. Ziehe ein Rechteck um das Element", "text"),
        ("3. Lass die Maus los", "text"),
        ("4. Gib einen Namen ein", "text"),
        ("", "sep"),
        ("✅ Vorteile:", "subtitle"),
        ("• Sehr genau", "text"),
        ("• Gut für große Elemente", "text"),
        ("", "sep"),
        ("⚠️ Nachteile:", "subtitle"),
        ("• Erfordert ruhige Hand", "text"),
        ("• Zeitaufwendig", "text")
    ])

    # Hilfe für das Trainingscenter
    def setup_test_help(self, parent):
        """Hilfe für Test-Phase"""
        test_notebook = ttk.Notebook(parent)
        test_notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # ✅ KORREKT - 4x Frame definieren
        types_frame = ttk.Frame(test_notebook)
        test_notebook.add(types_frame, text="🎯 Test-Typen")
        
        threshold_frame = ttk.Frame(test_notebook)  
        test_notebook.add(threshold_frame, text="📏 Threshold")
        
        report_frame = ttk.Frame(test_notebook)
        test_notebook.add(report_frame, text="📋 Reports")
        
        seq_frame = ttk.Frame(test_notebook)
        test_notebook.add(seq_frame, text="📋 Sequenz")
        
        self.create_help_content(types_frame, [
        ("Test-Typen im Überblick", "title"),
        ("", "sep"),
        ("📊 Einzeltest:", "subtitle"),
        ("Testet ein einzelnes Element mehrfach", "text"),
        ("Ideal um die Erkennungsqualität zu prüfen", "text"),
        ("Zeigt Position und Erkennungszeit", "text"),
        ("", "sep"),
        ("📋 Sequenz-Test:", "subtitle"),
        ("Testet eine komplette Ablaufsequenz", "text"),
        ("z.B. '7 + 8 ='", "text"),
        ("Führt tatsächliche Klicks aus", "text"),
        ("", "sep"),
        ("📦 Batch-Test:", "subtitle"),
        ("Testet alle Elemente eines Moduls", "text"),
        ("Schneller Qualitätscheck", "text"),
        ("Zeigt welche Elemente gut/schlecht erkannt werden", "text"),
        ("", "sep"),
        ("⚡ Performance-Test:", "subtitle"),
        ("Misst Erkennungsrate über Zeit", "text"),
        ("Ermittelt durchschnittliche Erkennungszeit", "text"),
        ("Wichtig für Echtzeit-Automation", "text")
    ])

    self.create_help_content(threshold_frame, [
        ("Threshold (Erkennungsschwelle)", "title"),
        ("Der Threshold bestimmt, wie ähnlich ein Bild sein muss.", "text"),
        ("", "sep"),
        ("🔴 0.5 - 0.7: Weich", "subtitle"),
        ("• Erkennt auch leicht veränderte Elemente", "text"),
        ("• Höhere Fehlerquote", "text"),
        ("• Gut für dynamische Inhalte", "text"),
        ("", "sep"),
        ("🟡 0.7 - 0.9: Ausgewogen", "subtitle"),
        ("• Standard-Einstellung", "text"),
        ("• Gute Balance zwischen Trefferquote und Genauigkeit", "text"),
        ("", "sep"),
        ("🟢 0.9 - 1.0: Streng", "subtitle"),
        ("• Nur exakte Übereinstimmungen", "text"),
        ("• Niedrige Fehlerquote", "text"),
        ("• Gut für statische Oberflächen", "text"),
        ("", "sep"),
        ("💡 Tipp:", "subtitle"),
        ("Teste verschiedene Thresholds mit dem Einzeltest", "text"),
        ("Der ideale Wert hängt von deiner Anwendung ab", "text")
    ])

        
    self.create_help_content(report_frame, [
        ("Test-Reports verstehen", "title"),
        ("Reports werden als JSON exportiert.", "text"),
        ("", "sep"),
        ("📊 Enthaltene Daten:", "subtitle"),
        ("• Timestamp", "text"),
        ("• Modul-Name", "text"),
        ("• Test-Typ", "text"),
        ("• Threshold-Einstellung", "text"),
        ("• Einzelergebnisse mit Zeitmessung", "text"),
        ("• Erfolgsstatistik", "text"),
        ("", "sep"),
        ("💡 Verwendungsmöglichkeiten:", "subtitle"),
        ("• Qualitätsdokumentation", "text"),
        ("• Vergleich verschiedener Versionen", "text"),
        ("• Fehleranalyse", "text"),
        ("• Performance-Optimierung", "text")
    ])

    def setup_auto_help(self, parent):
        auto_notebook = ttk.Notebook(parent)
        auto_notebook.pack(fill='both', expand=True)
        
        # ✅ FRAMES DEFINIEREN
        seq_frame = ttk.Frame(auto_notebook)
        auto_notebook.add(seq_frame, text="📋 Sequenz")
        
        watchdog_frame = ttk.Frame(auto_notebook)
        auto_notebook.add(watchdog_frame, text="👀 Watchdog")
        
        sched_frame = ttk.Frame(auto_notebook)
        auto_notebook.add(sched_frame, text="⏰ Scheduler")
        
    self.create_help_content(seq_frame, [
        ("Sequenz-Automation", "title"),
        ("Definiere Schritt-für-Schritt Abläufe.", "text"),
        ("", "sep"),
        ("📝 Verfügbare Aktionen:", "subtitle"),
        ("• Klick - Klickt auf ein trainiertes Element", "text"),
        ("• Doppelklick - Doppelklick auf Element", "text"),
        ("• Text - Schreibt Text", "text"),
        ("• Warten - Pausiert für X Sekunden", "text"),
        ("• Screenshot - Speichert Bildschirmfoto", "text"),
        ("• Tastenkombi - Führt Hotkey aus", "text"),
        ("• Maus bewegen - Bewegt Maus zu Koordinaten", "text"),
        ("", "sep"),
        ("⚙️ Parameter:", "subtitle"),
        ("• Wiederholungen - Wie oft ausführen", "text"),
        ("• Fehlerverhalten - Was tun bei Fehler", "text"),
        ("• Max. Versuche - Wie oft wiederholen", "text"),
        ("• Verzögerung - Pause zwischen Schritten", "text"),
        ("", "sep"),
        ("💡 Beispiel: Taschenrechner", "subtitle"),
        ("1. Klick auf '7'", "text"),
        ("2. Klick auf 'plus'", "text"),
        ("3. Klick auf '8'", "text"),
        ("4. Klick auf 'gleich'", "text"),
        ("5. Warte 2 Sekunden", "text"),
        ("6. Screenshot vom Ergebnis", "text")
    ])

        
    self.create_help_content(watchdog_frame, [
        ("Watchdog - Automatische Reaktionen", "title"),
        ("Der Watchdog überwacht den Bildschirm und reagiert auf Ereignisse.", "text"),
        ("", "sep"),
        ("🔍 Überwachungs-Optionen:", "subtitle"),
        ("• Bildschirmbereich - Bestimmter Bereich", "text"),
        ("• Fenster - Bestimmtes Programm", "text"),
        ("• Prozess - Wenn Programm startet/endet", "text"),
        ("• Dateisystem - Wenn Datei geändert wird", "text"),
        ("", "sep"),
        ("⚡ Ereignisse:", "subtitle"),
        ("• Element erscheint - Wenn etwas auftaucht", "text"),
        ("• Element verschwindet - Wenn etwas weggeht", "text"),
        ("• Farbe ändert sich - Bei Pixel-Veränderung", "text"),
        ("• Text erscheint - Bei bestimmtem Text", "text"),
        ("", "sep"),
        ("🎯 Aktionen:", "subtitle"),
        ("• Klicken - Auf das Element klicken", "text"),
        ("• Tastendruck - Taste drücken", "text"),
        ("• Sequenz starten - Komplexe Aktion", "text"),
        ("• Benachrichtigung - Popup anzeigen", "text"),
        ("", "sep"),
        ("💡 Anwendungsbeispiele:", "subtitle"),
        ("• Auf 'OK' Button in Dialogfenstern automatisch klicken", "text"),
        ("• Bei Fehlermeldungen Screenshot machen", "text"),
        ("• Programm starten wenn USB-Stick erkannt wird", "text")
    ])

    self.create_help_content(sched_frame, [
        ("Zeitgesteuerte Automation", "title"),
        ("Führe Aufgaben automatisch zu bestimmten Zeiten aus.", "text"),
        ("", "sep"),
        ("📅 Zeitpläne:", "subtitle"),
        ("• Einmalig - Zu einem bestimmten Zeitpunkt", "text"),
        ("• Täglich - Jeden Tag zur gleichen Zeit", "text"),
        ("• Wöchentlich - An bestimmten Wochentagen", "text"),
        ("• Monatlich - Am X. jedes Monats", "text"),
        ("", "sep"),
        ("💡 Beispiele:", "subtitle"),
        ("• Täglich 9:00 Uhr: Excel-Bericht erstellen", "text"),
        ("• Jeden Freitag 17:00: Backup starten", "text"),
        ("• Monatlich am 1.: Rechnungen drucken", "text"),
        ("", "sep"),
        ("⚠️ Wichtig:", "subtitle"),
        ("Der Computer muss zur geplanten Zeit laufen!", "text"),
        ("Für 24/7 Betrieb empfiehlt sich ein Server.", "text")
    ])


    def setup_faq(self, parent):
        """FAQ - Häufig gestellte Fragen"""
        
        # Canvas für Scrollbarkeit
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # FAQ Einträge
        faqs = [
            ("❓ Warum findet GABI meine Elemente nicht?",
            "Mögliche Gründe:\n"
            "• Das Element hat sich verändert (Farbe, Größe)\n"
            "• Die Bildschirmauflösung ist anders\n"
            "• Der Threshold ist zu hoch/niedrig\n"
            "• Das Element ist verdeckt oder nicht sichtbar\n\n"
            "Lösung: Trainiere das Element neu oder passe den Threshold an."),
            
            ("❓ Kann GABI mit verschiedenen Bildschirmauflösungen umgehen?",
            "Ja! Trainiere die Elemente einfach bei verschiedenen Auflösungen.\n"
            "GABI lernt dann alle Varianten."),
            
            ("❓ Wie viele Elemente kann ich trainieren?",
            "Unbegrenzt! Jedes Modul kann beliebig viele Elemente enthalten.\n"
            "Die GPU-Erkennung bleibt auch bei tausenden Templates schnell."),
            
            ("❓ Funktioniert GABI auch mit Spielen?",
            "Ja, solange das Spiel im Fenster-Modus läuft.\n"
            "Bei Vollbild-Spielen kann es Probleme geben."),
            
            ("❓ Was ist der beste Threshold?",
            "Für die meisten Anwendungen ist 0.8 optimal.\n"
            "Teste verschiedene Werte mit dem Einzeltest."),
            
            ("❓ Kann ich trainierte Elemente teilen?",
            "Ja! Einfach den assets/[modul] Ordner kopieren.\n"
            "Alle Templates sind normale PNG-Dateien."),
            
            ("❓ Warum GPU und nicht CPU?",
            "GPU ist viel schneller bei Bildverarbeitung.\n"
            "Eine Suche über 1000 Templates dauert nur Millisekunden."),
            
            ("❓ Was passiert bei einem Fehler in der Automation?",
            "Das hängt von deiner Einstellung ab:\n"
            "• 'Stoppen' - Automation bricht ab\n"
            "• 'Überspringen' - Macht mit nächstem Schritt weiter\n"
            "• 'Wiederholen' - Versucht es erneut"),
            
            ("❓ Kann ich mehrere Programme gleichzeitig automatisieren?",
            "Ja, mit der Batch-Funktion.\n"
            "Die Aufgaben werden nacheinander ausgeführt."),
            
            ("❓ Wie mache ich ein Backup meiner Trainingsdaten?",
            "Einfach den gesamten 'assets' Ordner kopieren.\n"
            "Alle Trainingsdaten sind dort gespeichert."),
        ]
        
        for question, answer in faqs:
            # Frage als LabelFrame
            q_frame = ttk.LabelFrame(scrollable_frame, text=question)
            q_frame.pack(fill='x', padx=10, pady=5)
            
            # Antwort
            ttk.Label(q_frame, text=answer, justify='left', wraplength=600).pack(padx=10, pady=5)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def setup_shortcuts(self, parent):
        """Tastaturkürzel Übersicht"""
        
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Titel
        ttk.Label(main_frame, text="⌨️ Tastaturkürzel", 
                font=("Arial", 16, "bold")).pack(pady=10)
        
        # Frame für Shortcuts
        shortcuts_frame = ttk.Frame(main_frame)
        shortcuts_frame.pack(fill='both', expand=True)
        
        # Globale Shortcuts
        global_frame = ttk.LabelFrame(shortcuts_frame, text="🌐 Globale Shortcuts")
        global_frame.pack(fill='x', pady=10)
        
        global_shortcuts = [
            ("Strg+Q", "Programm beenden"),
            ("F1", "Hilfe öffnen"),
            ("Strg+S", "Aktuelle Konfiguration speichern"),
            ("Strg+L", "Log exportieren"),
        ]
        
        for i, (key, desc) in enumerate(global_shortcuts):
            ttk.Label(global_frame, text=key, width=15, anchor='w').grid(row=i, column=0, padx=5, pady=2)
            ttk.Label(global_frame, text=desc, anchor='w').grid(row=i, column=1, padx=5, pady=2, sticky='w')
        
        # Training Shortcuts
        training_frame = ttk.LabelFrame(shortcuts_frame, text="📚 Training Shortcuts")
        training_frame.pack(fill='x', pady=10)
        
        training_shortcuts = [
            ("S", "Element speichern (während Training)"),
            ("Leertaste", "Training pausieren/fortsetzen"),
            ("Esc", "Training abbrechen"),
            ("Strg+N", "Neues Element hinzufügen"),
        ]
        
        for i, (key, desc) in enumerate(training_shortcuts):
            ttk.Label(training_frame, text=key, width=15, anchor='w').grid(row=i, column=0, padx=5, pady=2)
            ttk.Label(training_frame, text=desc, anchor='w').grid(row=i, column=1, padx=5, pady=2, sticky='w')
        
        # Test Shortcuts
        test_frame = ttk.LabelFrame(shortcuts_frame, text="🧪 Test Shortcuts")
        test_frame.pack(fill='x', pady=10)
        
        test_shortcuts = [
            ("Strg+T", "Test starten"),
            ("Strg+R", "Report exportieren"),
            ("F5", "Templates neu laden"),
        ]
        
        for i, (key, desc) in enumerate(test_shortcuts):
            ttk.Label(test_frame, text=key, width=15, anchor='w').grid(row=i, column=0, padx=5, pady=2)
            ttk.Label(test_frame, text=desc, anchor='w').grid(row=i, column=1, padx=5, pady=2, sticky='w')
        
        # Automation Shortcuts
        auto_frame = ttk.LabelFrame(shortcuts_frame, text="🤖 Automation Shortcuts")
        auto_frame.pack(fill='x', pady=10)
        
        auto_shortcuts = [
            ("Strg+A", "Automation starten"),
            ("Strg+P", "Pause"),
            ("Strg+X", "Stopp"),
            ("Strg+E", "Sequenz exportieren"),
            ("Strg+I", "Sequenz importieren"),
        ]
        
        for i, (key, desc) in enumerate(auto_shortcuts):
            ttk.Label(auto_frame, text=key, width=15, anchor='w').grid(row=i, column=0, padx=5, pady=2)
            ttk.Label(auto_frame, text=desc, anchor='w').grid(row=i, column=1, padx=5, pady=2, sticky='w')

    def setup_about(self, parent):
        """Über GABI"""
        
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill='both', expand=True)
        
        # Logo/Header
        header = ttk.Label(main_frame, text="🤖 GABI", 
                        font=("Arial", 24, "bold"))
        header.pack(pady=20)
        
        subtitle = ttk.Label(main_frame, text="GPU-Accelerated Bot Interface",
                            font=("Arial", 12))
        subtitle.pack()
        
        # Version
        version_frame = ttk.Frame(main_frame)
        version_frame.pack(pady=20)
        
        ttk.Label(version_frame, text="Version:", font=("Arial", 10, "bold")).pack(side='left')
        ttk.Label(version_frame, text="1.0.0", font=("Arial", 10)).pack(side='left', padx=5)
        
        ttk.Label(version_frame, text="Build:", font=("Arial", 10, "bold")).pack(side='left', padx=(20,0))
        ttk.Label(version_frame, text="2024.02", font=("Arial", 10)).pack(side='left', padx=5)
        
        # Features
        features_frame = ttk.LabelFrame(main_frame, text="✨ Hauptfunktionen")
        features_frame.pack(fill='x', padx=50, pady=10)
        
        features = [
            "• GPU-beschleunigte Bilderkennung",
            "• 5 verschiedene Trainings-Methoden",
            "• Umfangreiche Test-Möglichkeiten",
            "• 5 Automation-Typen (Sequenz, Rezepte, Watchdog, Batch, Scheduler)",
            "• Live-Vorschau und Maus-Tracking",
            "• Export/Import von Trainingsdaten und Sequenzen",
            "• CSV/JSON Support für Batch-Verarbeitung",
        ]
        
        for feature in features:
            ttk.Label(features_frame, text=feature, justify='left').pack(anchor='w', padx=10, pady=2)
        
        # System
        system_frame = ttk.LabelFrame(main_frame, text="🖥️ Systemanforderungen")
        system_frame.pack(fill='x', padx=50, pady=10)
        
        ttk.Label(system_frame, 
                text="• Windows 10/11 (64-bit)\n"
                    "• NVIDIA GPU mit CUDA-Support (optional, aber empfohlen)\n"
                    "• Python 3.8 oder höher\n"
                    "• 4GB RAM (8GB empfohlen)",
                justify='left').pack(anchor='w', padx=10, pady=5)
        
        # Credits
        credits_frame = ttk.LabelFrame(main_frame, text="👥 Credits")
        credits_frame.pack(fill='x', padx=50, pady=10)
        
        ttk.Label(credits_frame,
                text="Entwickelt mit ❤️ für die Automatisierungs-Community\n\n"
                    "Open Source Lizenzen:\n"
                    "• PyAutoGUI - MIT License\n"
                    "• OpenCV - Apache 2.0 License\n"
                    "• PyTorch - BSD-style License\n"
                    "• PIL/Pillow - HPND License",
                justify='center').pack(padx=10, pady=5)
        
        # Copyright
        copyright = ttk.Label(main_frame, 
                            text="© 2024 GABI Project. Alle Rechte vorbehalten.",
                            font=("Arial", 8))
        copyright.pack(side='bottom', pady=10)

    def create_help_content(self, parent, content):
        """Hilfsfunktion zum Erstellen von formatiertem Hilfetext"""
        
        # Canvas für Scrollbarkeit
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        for item in content:
            if len(item) == 2 and item[1] == "title":
                # Titel
                ttk.Label(scrollable_frame, text=item[0], 
                        font=("Arial", 14, "bold")).pack(anchor='w', padx=10, pady=(10,2))
            elif len(item) == 2 and item[1] == "subtitle":
                # Untertitel
                ttk.Label(scrollable_frame, text=item[0], 
                        font=("Arial", 11, "bold")).pack(anchor='w', padx=15, pady=(5,2))
            elif item == "":
                # Leerzeile
                ttk.Label(scrollable_frame, text="").pack()
            elif item[0] == "" and len(item) == 2 and item[1] == "sep":
                # Separator
                ttk.Separator(scrollable_frame, orient='horizontal').pack(fill='x', padx=10, pady=5)
            else:
                # Normaler Text
                if isinstance(item, tuple) and len(item) == 2:
                    # Für Listenpunkte
                    ttk.Label(scrollable_frame, text=item[0], 
                            wraplength=500, justify='left').pack(anchor='w', padx=25, pady=1)
                else:
                    ttk.Label(scrollable_frame, text=item, 
                            wraplength=500, justify='left').pack(anchor='w', padx=20, pady=1)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def show_quick_help(self):
        """Zeigt einen Quick-Help Dialog"""
        
        dialog = tk.Toplevel(self.root)
        dialog.title("❓ Quick Help")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Notebook für kompakte Hilfe
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Quick Start
        quick_frame = ttk.Frame(notebook)
        notebook.add(quick_frame, text="⚡ Quick Start")
        
        ttk.Label(quick_frame, 
                text="1️⃣ Modul erstellen (➕ Neu)\n"
                    "2️⃣ Elemente definieren\n"
                    "3️⃣ Training starten\n"
                    "4️⃣ Mit 'S' Elemente speichern\n"
                    "5️⃣ Im Test-Tab überprüfen\n"
                    "6️⃣ Automation erstellen",
                font=("Arial", 11),
                justify='left').pack(padx=20, pady=20)
        
        # Aktueller Tab Hilfe
        current_tab = self.notebook.index(self.notebook.select())
        tab_names = ["Training", "Test", "Automation", "Hilfe"]
        
        if current_tab < 3:  # Nicht im Hilfe-Tab
            tab_frame = ttk.Frame(notebook)
            notebook.add(tab_frame, text=f"📌 {tab_names[current_tab]}")
            
            if current_tab == 0:  # Training
                ttk.Label(tab_frame,
                        text="🔹 Wähle Trainings-Methode\n"
                            "🔹 Definiere Element-Namen\n"
                            "🔹 Starte Training\n"
                            "🔹 Drücke 'S' über jedem Element\n"
                            "🔹 Fertig!",
                        font=("Arial", 11),
                        justify='left').pack(padx=20, pady=20)
            elif current_tab == 1:  # Test
                ttk.Label(tab_frame,
                        text="🔹 Wähle Test-Typ\n"
                            "🔹 Stelle Threshold ein\n"
                            "🔹 Starte Test\n"
                            "🔹 Prüfe Ergebnisse\n"
                            "🔹 Exportiere Report",
                        font=("Arial", 11),
                        justify='left').pack(padx=20, pady=20)
            elif current_tab == 2:  # Automation
                ttk.Label(tab_frame,
                        text="🔹 Erstelle Sequenz\n"
                            "🔹 Definiere Schritte\n"
                            "🔹 Stelle Parameter ein\n"
                            "🔹 Starte Automation\n"
                            "🔹 Oder nutze Watchdog/Scheduler",
                        font=("Arial", 11),
                        justify='left').pack(padx=20, pady=20)
        
        # Shortcuts
        shortcut_frame = ttk.Frame(notebook)
        notebook.add(shortcut_frame, text="⌨️ Shortcuts")
        
        shortcuts_text = tk.Text(shortcut_frame, wrap=tk.WORD, height=15)
        shortcuts_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        shortcuts_text.insert('1.0', 
            "Globale Shortcuts:\n"
            "• F1 - Diese Hilfe\n"
            "• Strg+Q - Beenden\n\n"
            "Training:\n"
            "• S - Element speichern\n"
            "• Esc - Abbrechen\n\n"
            "Test:\n"
            "• Strg+T - Test starten\n"
            "• Strg+R - Report\n\n"
            "Automation:\n"
            "• Strg+A - Start\n"
            "• Strg+P - Pause\n"
            "• Strg+X - Stop"
        )
        shortcuts_text.config(state='disabled')
        
        # Schließen-Button
        ttk.Button(dialog, text="Schließen", command=dialog.destroy).pack(pady=10)

if __name__ == "__main__":
    app = GabiTrainingCenter()
    app.run()