"""Single-frame USB/V4L2 camera capture."""
from pathlib import Path


def capture_image(image_dir: Path, camera_index=0, warmup_frames=5):
    """Read a USB/V4L2 camera; release it even if capture or writing fails."""
    if warmup_frames < 1:
        raise ValueError("warmup_frames must be positive")
    import cv2

    destination = image_dir / "camera_capture.jpg"
    cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
    try:
        if not cap.isOpened():
            raise RuntimeError("Camera unavailable")
        frame, ok = None, False
        for _ in range(warmup_frames):
            ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError("Camera capture failed")
        if not cv2.imwrite(str(destination), frame):
            raise RuntimeError("Camera image write failed")
        return destination
    finally:
        cap.release()


