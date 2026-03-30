# test_opencv_webcam_fixed.py
import cv2
import time

cap = cv2.VideoCapture(0)

# Warte auf die Kamera-Initialisierung
time.sleep(2)

# Lese mehrere Frames, bis ein nicht-schwarzes Bild kommt
for i in range(10):
    ret, frame = cap.read()
    if ret:
        print(f"Frame {i}: min={frame.min()}, max={frame.max()}")
        if frame.max() > 0:
            print("✅ Bild hat Inhalt!")
            cv2.imwrite("test_webcam_ok.jpg", frame)
            break
    time.sleep(0.2)

cap.release()