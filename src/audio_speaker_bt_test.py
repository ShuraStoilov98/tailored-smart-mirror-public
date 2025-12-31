import subprocess
import sys

mp3_file = "test.mp3"  # put your mp3 in the same folder

try:
    subprocess.run(
        ["mpg123", mp3_file],
        check=True
    )
except subprocess.CalledProcessError as e:
    print("Playback failed:", e)
    sys.exit(1)
