# Raspberry Pi setup

This guide targets a Raspberry Pi 4, USB/V4L2 camera and GPIO23 status LED, using **Raspberry Pi OS Trixie, 64-bit, Python 3.13**. Hardware dependencies require Python 3.12 or newer; a stock Bookworm/Python 3.11 install cannot use the supplied locks unchanged. The full setup still needs testing on the physical build. Pi 5, 32-bit OS and CSI/libcamera support are not covered.

Raspberry Pi's [OS documentation](https://www.raspberrypi.com/documentation/computers/os.html) identifies Trixie as the current base and recommends virtual environments for pip installations. Keep the original boot media intact if testing a newer image.

## Prepare the Pi

Use Raspberry Pi Imager to flash a **separate** microSD card with the desktop 64-bit OS; configure your own login, hostname, Wi-Fi and SSH locally. Do not commit those details. Verify the SSH host key against the Pi/router's trusted information rather than automatically accepting a changed key. Development can use a local terminal or VS Code Remote SSH.

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip python3-lgpio v4l-utils libsdl2-2.0-0 libsdl2-mixer-2.0-0
python3 --version
uname -m
```

Expect Python 3.13 and `aarch64` on this OS image. Clone the project and enter its root directory:

```bash
git clone https://github.com/ShuraStoilov98/tailored-smart-mirror-public.git
cd tailored-smart-mirror-public
```

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements-hardware.lock
python -m pip check
mkdir -p secrets
chmod 700 secrets
cp .env.example secrets/.env
chmod 600 secrets/.env
```

The system-site-packages flag makes the OS-provided `lgpio` backend available. Python packages in the lock take precedence; maintain OS packages, the kernel and the audio stack with APT. Direct dependencies are listed in `requirements.txt` and `requirements-hardware.txt`; the lock files pin their transitive dependencies.

Edit `secrets/.env` locally. Supply an OpenAI key with access to the configured vision/TTS models, and set a provider-side spending limit. Environment variables override file values. Defaults retain the project's `gpt-4o-mini`, `gpt-4o-mini-tts` and `alloy`; check availability in your account. Only the direct launch reads this file; an imported app factory uses environment variables or explicit configuration. No credentials are needed for offline tests.

## Devices and permissions

Power off before wiring the LED. See [Wiring](docs/Wiring.md). Use `MIRROR_LED_PIN` for a BCM pin and `MIRROR_CAMERA_INDEX` for a numeric OpenCV device index.

```bash
v4l2-ctl --list-devices
v4l2-ctl --device /dev/video0 --list-formats-ext
groups
ls -l /dev/video0 /dev/gpiochip*
```

If the device permissions require them, add your login to the `video` and `gpio` groups, then log out and back in:

```bash
sudo usermod -aG video,gpio "$USER"
```

Run the app as your login, without sudo. Use `GPIOZERO_PIN_FACTORY=lgpio` to select the OS GPIO backend. USB UVC cameras use V4L2 and do not require a legacy camera enable step. A different camera index may be needed if multiple `/dev/video*` nodes exist.

Select the speaker as the desktop's default audio output. Pair a Bluetooth speaker through the desktop Bluetooth/audio controls first; pygame does not perform pairing. An SSH-only session may lack access to the desktop user's audio session; start the app in the same user's desktop terminal for the first test.

## Run and access

```bash
source .venv/bin/activate
GPIOZERO_PIN_FACTORY=lgpio python src/main.py
```

Open `http://127.0.0.1:8080` locally. For a laptop browser, forward loopback from your own Pi hostname/login:

```bash
ssh -N -L 8080:127.0.0.1:8080 YOUR_PI_USER@YOUR_PI_HOST
```

Open the same URL on the laptop. If port 8080 is in use locally, choose another local port, e.g. `8081:127.0.0.1:8080`. The page receives a temporary token; refresh after restarting the server. API clients must obtain that token from the local page and send `X-Mirror-Token`. Never place the token in a URL or public recording.

Keep one application process for the single camera/speaker. There is no installed service or multi-worker configuration. Start manually and stop with Ctrl+C; managed service/audio integration requires hardware testing first. Do not expose the Flask development server directly on a LAN or the internet.

A click captures a photo, invokes vision, validates the review and generates/plays speech. Failure returns a generic message and cleans up indicators/files. `/health` checks HTTP responsiveness only, not hardware or provider availability. No continuous stream is served. Runtime photos are deleted after a request; the latest successful MP3 remains local until a complete replacement or orderly shutdown. Each request uses a private temporary directory; a failed upload or provider call leaves the previous successful speech intact. Shutdown waits for active analysis and closes the API client and devices. Abrupt termination may leave files in ignored `runtime/`; clear them locally after reviewing retention needs. OpenAI receives photos and spoken text; `store=False` avoids storing the Responses object but does not promise zero provider retention. See [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data).

## Check each component

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/scripts/led_test.py
python tests/scripts/camera_test.py
# After an actual successful analysis has generated runtime/result.mp3:
python tests/scripts/audio_speaker_bt_test.py
```

The camera check saves a private local JPEG; the audio check plays your latest result. Stop LED/audio checks with Ctrl+C or the requested Enter key. These are manual device checks, excluded from automated test discovery. A synthetic test pass does not prove the physical devices work.

For camera failure, confirm USB enumeration/permissions and format support. For GPIO failure, confirm `python3-lgpio` is visible inside the venv and group access. For speech failure, verify your audio session/output; for provider failure, verify the local key, account/model access and connection. Errors intentionally omit raw provider details and local paths. Do not share screenshots containing keys or terminal configuration.
