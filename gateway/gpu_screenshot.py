# gpu_screenshot.py
import torch
import numpy as np
from PIL import Image
import pyautogui
import cv2

class GPUScreenshot:
    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"📸 GPU Screenshot auf: {self.device}")
    
    def capture(self):
        """Macht Screenshot und lädt ihn auf GPU"""
        # Screenshot mit PIL (schnell)
        screenshot = pyautogui.screenshot()
        
        # Zu numpy array
        img_np = np.array(screenshot)
        
        # Zu torch tensor auf GPU
        img_gpu = torch.from_numpy(img_np).to(self.device)
        
        return img_gpu, img_np
    
    def find_template_gpu(self, screenshot_gpu, template_path, threshold=0.8):
        """Findet Template mit GPU-Beschleunigung"""
        import torch.nn.functional as F
        
        # Template laden und auf GPU
        template = cv2.imread(template_path)
        template_gpu = torch.from_numpy(template).to(self.device)
        
        # Template Matching auf GPU
        correlation = F.conv2d(
            screenshot_gpu.permute(2,0,1).unsqueeze(0).float(),
            template_gpu.permute(2,0,1).unsqueeze(0).float()
        )
        
        max_val = correlation.max()
        max_pos = correlation.argmax()
        
        if max_val > threshold:
            return True, max_pos
        return False, None