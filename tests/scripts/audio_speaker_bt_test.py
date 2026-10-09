"""Play a locally generated result through the OS-selected speaker."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from audio_helper import AudioPlayer

if __name__ == "__main__":
    audio = AudioPlayer()
    try:
        audio.play(Path(__file__).resolve().parents[2] / "runtime" / "result.mp3")
        input("Press Enter to stop playback. ")
    finally:
        audio.close()
