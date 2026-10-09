# Film an authentic demo

Founders: film a short **30–45 second demo** showing the physical Raspberry Pi/camera assembly, one real interaction and the resulting feedback. No connected camera/GPIO device was available during cleanup, and no build photo/video was found. The README currently uses original UI artwork and labeled CAD renders; these are not evidence of hardware operation.

## Shot list

1. **0–8 seconds:** show the actual enclosure/build, Pi, USB camera, LED/resistor and speaker. Keep labels, serial numbers, Wi-Fi/router details, addresses and other people out of frame.
2. **8–15 seconds:** show the two-action page and press one mode once. Use your own image with consent, or photograph an outfit on a mannequin and disclose that choice. Keep API keys, access tokens, browser developer tools and terminal environment out of frame.
3. **15–35 seconds:** show capture/processing LED behavior, the returned score/verdict and audible speech. Label the speech “AI-generated styling feedback.” Keep real latency visible or label any removed waiting time.
4. **35–45 seconds:** finish with the physical build and verdict together. State “Pi 4 + [exact camera], [OS], software [clean commit]”; describe any mocked component explicitly.

Use a phone for the physical overview so you do not occupy the same USB camera that the application captures. Record horizontally, with a plain background and no reflective private screens. Pick the strongest reviewed frame showing physical hardware as the README image. Preserve raw clips locally in ignored `demo-private/`.

## Local checks and recording commands

Before filming, verify wiring, follow [setup](../SETUP_RASPBERRY_PI.md) and record the actual revision/OS locally:

```bash
mkdir -p demo-private
chmod 700 demo-private
git rev-parse --short HEAD
cat /etc/os-release
v4l2-ctl --list-devices
python tests/scripts/camera_test.py
GPIOZERO_PIN_FACTORY=lgpio python src/main.py
```

Run device enumeration outside the recording: its output can include identifiers. Do not include private test captures or `.env` in exported footage. Optional USB camera footage, **with the app stopped** (only if the camera supports the selected size/rate):

```bash
ffmpeg -f v4l2 -framerate 30 -video_size 640x480 -i /dev/video0 -t 8 -an demo-private/camera-check.mp4
```

This clip proves that camera capture path only; a phone clip must show the integrated app interaction. Install local editing/inspection tools on your workstation if needed (`ffmpeg`, `ffprobe`, `exiftool`). Copy the phone clip to `demo-private/raw-demo.mp4` and trim a single clear segment; substitute the actual timings:

```bash
ffmpeg -ss 0 -i demo-private/raw-demo.mp4 -t 45 -map_metadata -1 -c:v libx264 -pix_fmt yuv420p -c:a aac demo-private/review-demo.mp4
ffprobe -v quiet -show_format -show_streams demo-private/review-demo.mp4
exiftool -a -G1 -s demo-private/review-demo.mp4
```

Review the full video and audio for faces/consent, names, addresses, screens, clothing labels/identifiers, reflections, spoken private information and metadata. Removing container metadata does not redact visible pixels or speech. Crop/blur or re-film unwanted details. Do not publish automatically after a metadata check.

After review, create a muted short GIF and still frame locally:

```bash
ffmpeg -i demo-private/review-demo.mp4 -ss 8 -t 8 -an -map_metadata -1 -vf "fps=8,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" demo-private/demo.gif
ffmpeg -ss 2 -i demo-private/review-demo.mp4 -frames:v 1 -map_metadata -1 demo-private/build.jpg
exiftool -a -G1 -s demo-private/build.jpg
```

Inspect the GIF/still as well. Copy only reviewed exports into `docs/assets/`, then link the GIF or a manually uploaded video from README. Include a caption with exact hardware, clean Git revision, filming date and what worked. New demo media/links have not been created or uploaded during this cleanup. Generated visuals must never substitute for physical evidence.
