# Tailored Smart Mirror

A Christmas 2025 buildathon prototype: press **Rate my outfit** or **Decide on item**, capture a photo with a Raspberry Pi, and hear a short styling verdict. Built to connect a physical camera, a simple web interface and AI feedback in one tangible interaction.

<p>
  <img src="docs/assets/original-interface.png" width="220" alt="Original two-action Tailored interface artwork">
  <img src="docs/assets/Top_plate_with_logo_v2.png" width="290" alt="Original top enclosure plate CAD preview">
  <img src="docs/assets/Bottom_plate_v2.png" width="290" alt="Original bottom enclosure plate CAD preview">
</p>

**Interface artwork and enclosure CAD renders.** A physical build demo is being prepared; see [Demo](docs/Demo.md).

## How it works

```mermaid
flowchart LR
    Browser[Two-action browser UI] -->|authenticated POST| Pi[Flask controller on Raspberry Pi 4]
    Camera[USB / V4L2 camera] -->|single JPEG| Pi
    Pi -->|photo + mode prompt| Vision[OpenAI vision model]
    Vision -->|validated JSON verdict| Pi
    Pi -->|short spoken script| TTS[OpenAI text-to-speech]
    TTS -->|MP3| Pi
    Pi --> Speaker[OS-selected speaker]
    Pi --> LED[BCM23 status LED]
    Pi -->|score + verdict| Browser
```

The two modes share a review schema so the UI and spoken feedback stay consistent. The LED flashes during capture, blinks during analysis and returns to steady on afterward. OpenCV takes a single frame rather than running a continuous camera stream; pygame plays speech through the operating system's selected speaker. Editable enclosure designs accompany the software.

## Project status

The prototype was developed during the Christmas 2025 buildathon, with enclosure designs added in January 2026. Automated tests use simulated hardware and provider responses; the current revision still needs an end-to-end check on the physical Pi with a live AI account.

The app uses a USB/V4L2 camera and an OS-selected speaker. CSI cameras, microphone input, streaming and multi-user operation are not supported. Styling scores are subjective AI feedback. Photos are sent to OpenAI, and requests require internet access and an account with access to the configured models.

## Run it

Use a Raspberry Pi 4, USB/V4L2 camera, speaker, status LED with resistor, suitable power supply and network access. Follow [Pi setup](SETUP_RASPBERRY_PI.md) and [wiring](docs/Wiring.md). The setup guide targets 64-bit Raspberry Pi OS Trixie with Python 3.13; automated checks cover Python 3.12 and 3.13.

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements-hardware.lock
mkdir -p secrets
cp .env.example secrets/.env
# Edit secrets/.env with your own API key.
GPIOZERO_PIN_FACTORY=lgpio python src/main.py
```

Open `http://127.0.0.1:8080` on the Pi, or use the SSH tunnel in the setup guide. Each action captures and submits a photo, displays a verdict and plays AI-generated speech. The server binds loopback, disables the debugger and requires a per-run browser token for API routes. Inputs are deleted after each request; only the latest speech is kept in ignored `runtime/` until shutdown. Do not photograph anyone without consent.

For offline checks on Linux/Python 3.12:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m unittest discover -s tests -p 'test_*.py' -v
```

## Source and credit

| Path | Responsibility |
| --- | --- |
| `src/main.py` | Flask routes, prompts, image validation/capture, AI review and speech |
| `src/led_helper.py`, `src/audio_helper.py` | Device indicators and playback |
| `src/static/` | Original Tailored interface and artwork; system fonts used now |
| `tests/` | Synthetic regression tests and manual hardware checks |
| `BoM for 3D printed parts/` | Original STL, editable 3MF and logo SVG/DXF |

Original contributors are credited in Git history. The original MIT copyright is Alexander Stoilov (2025). See [asset provenance and credits](docs/Attribution.md) and [LICENSE](LICENSE).
