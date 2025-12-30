import cv2

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    raise RuntimeError("Camera not opened")

ret, frame = cap.read()
cap.release()

if not ret:
    raise RuntimeError("Failed to grab frame")

cv2.imwrite("test_frame.jpg", frame)
print("Saved test_frame.jpg")
