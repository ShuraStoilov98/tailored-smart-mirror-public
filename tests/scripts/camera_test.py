"""Capture one local USB-camera frame; output stays in ignored runtime/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from main import capture_image_from_camera_for_analysis

if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[2] / "runtime"
    destination.mkdir(mode=0o700, exist_ok=True)
    capture_image_from_camera_for_analysis(destination)
    print("Saved runtime/camera_capture.jpg (private; do not commit)")
