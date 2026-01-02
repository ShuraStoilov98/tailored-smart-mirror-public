import subprocess
import sys

mp3_file = "result.mp3"  # The mp3 needs to be in the same folder

try:
    subprocess.run(
        ["mpg123", mp3_file],
        check=True
    )
except subprocess.CalledProcessError as e:
    print("Playback failed:", e)
    sys.exit(1)
