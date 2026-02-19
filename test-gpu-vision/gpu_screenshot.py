# gpu_screenshot.py
import torch
import numpy as np
from PIL import Image
import pyautogui
import cv2

class GPUScreenshot:
    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"[GPU] Screenshot auf: {self.device}")
    
    def capture(self):
        """Macht Screenshot und lädt ihn auf GPU"""
        screenshot = pyautogui.screenshot()
        img_np = np.array(screenshot)
        img_gpu = torch.from_numpy(img_np).to(self.device)
        return img_gpu, img_np
    
    def find_template_gpu(self, screenshot_gpu, template_path, threshold=0.8):
        """Findet ein Template auf dem Screenshot mittels GPU-Beschleunigung"""
        import torch.nn.functional as F
        
        # 1. Template laden
        template = cv2.imread(template_path)
        if template is None:
            print(f"❌ Fehler: Template {template_path} konnte nicht geladen werden.")
            return False, None
        
        # 2. Template auf GPU laden
        template_gpu = torch.from_numpy(template).to(self.device)
        
        # 3. Berechnung der Korrelation auf der GPU (Convolution)
        # Wir wandeln in Float um und bringen die Dimensionen in (B, C, H, W)
        correlation = F.conv2d(
            screenshot_gpu.permute(2, 0, 1).unsqueeze(0).float(),
            template_gpu.permute(2, 0, 1).unsqueeze(0).float()
        )
        
        # 4. Ergebnis zurück auf CPU zur Auswertung mit OpenCV
        res = correlation.cpu().numpy()[0][0]
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= threshold:
            # Wir berechnen die MITTE des gefundenen Objekts für den Klick
            h, w = template.shape[:2]
            center_x = int(max_loc[0] + w // 2)
            center_y = int(max_loc[1] + h // 2)
            return True, (center_x, center_y)
        else:
            return False, None