from gpu_screenshot import GPUScreenshot
from gui_controller import get_gui_controller
import time

def solve_math():
    vision = GPUScreenshot()
    gui = get_gui_controller()
    
    # Aufgabe: 7 + 8 =
    sequence = ["7", "plus", "8", "gleich"]
    
    for step in sequence:
        print(f"🔍 Suche Taste: {step}")
        img_gpu, _ = vision.capture()
        found, coords = vision.find_template_gpu(img_gpu, f"assets/calc/btn_{step}.png")
        
        if found:
            x, y = coords
            print(f"🖱️ Klicke {step} bei ({x}, {y})")
            gui.safe_click(x, y)
            time.sleep(0.5)

if __name__ == "__main__":
    solve_math()