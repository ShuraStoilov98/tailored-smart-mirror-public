from flask import Flask, request, jsonify, send_from_directory, send_file
import pathlib
import os
import json
import base64
from dotenv import load_dotenv
from openai import OpenAI

# Helpers
from led_helper import StatusLED
from audio_helper import AudioPlayer

# Start the project
print("Smart mirror project ready 🚀")

# Initialize Flask app
app = Flask(__name__, static_folder="static", static_url_path="/static")

# ----------------------------
# Paths / Directories
# ----------------------------
BASE_DIR = pathlib.Path(__file__).resolve().parent

IMAGE_INPUT_DATA_DIR = (BASE_DIR / "image_input").resolve()
TEXT_OUTPUT_DATA_DIR = (BASE_DIR / "output" / "text").resolve()
AUDIO_OUTPUT_DATA_DIR = (BASE_DIR / "output" / "audio").resolve()

IMAGE_INPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)
TEXT_OUTPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_OUTPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

input_image_file_name = IMAGE_INPUT_DATA_DIR / "image.jpg"
output_text_file_name = TEXT_OUTPUT_DATA_DIR / "result.json"
output_audio_file_name = AUDIO_OUTPUT_DATA_DIR / "result.mp3"
filler_audio_file_name = AUDIO_OUTPUT_DATA_DIR / "filler.mp3"

# ----------------------------
# OpenAI setup
# ----------------------------
ENV_PATH = BASE_DIR.parent / "secrets" / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)
api_key = os.getenv("OPENAI_API_KEY", "")
if not api_key:
    raise RuntimeError("Missing OPENAI_API_KEY. Put it in your .env file or environment variables.")

client = OpenAI(api_key=api_key)

# Vision-capable model for image->text(JSON
image_to_text_model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")

# Text->speech model
text_to_audio_model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
audio_voice = os.getenv("OPENAI_TTS_VOICE", "alloy")

# ----------------------------
# Output schemas (stringified)
# Keep decide + rate same structure to simplify UI.
# ----------------------------
REVIEW_SCHEMA = """{
  "overall_score": 0,
  "verdict": "",
  "suits_user": false,
  "fit_score": 0,
  "proportion_score": 0,
  "color_harmony_score": 0,
  "style_score": 0,
  "quality_cues_score": 0,
  "occasion_guess": "",
  "key_strengths": [],
  "key_issues": [],
  "quick_improvements": [],
  "reasoning_long": "",
  "reasoning_short": ""
}"""

# ----------------------------
# Prompts
# ----------------------------
def build_image_to_text_decide_prompt(output_schema: str) -> str:
    """
    Decide prompt: user is wearing ONE new item (or a clearly highlighted main item).
    Output: JSON only, purchase recommendation based solely on the photo.
    """
    return f"""
You are a fashion assistant. The user provided ONE photo of themselves wearing a clothing item they are considering buying.

TASK:
- Analyze ONLY what is visible in the photo (no web browsing, no guessing about the user's preferences, wardrobe, budget, or brand unless clearly visible).
- Evaluate whether the user should buy the item based on: fit, proportions, how flattering it is on their body, color harmony with their visible features (skin/hair), style impact, versatility inferred from the item itself, and visible quality cues.
- Output ONLY valid JSON that matches this exact schema (same keys, no extra keys): {output_schema}

OUTPUT RULES:
- JSON only (no markdown, no commentary).
- Integers only for all *_score fields and overall_score.
- Score ranges:
  - overall_score: 0 to 100
  - all *_score: 1 to 10
- Arrays: max 4 items each, concise phrases.
- verdict must be exactly one of: "buy", "maybe", "skip"
- suits_user must be true/false based on the photo (fit + harmony + overall effect).
- reasoning_long: max 240 characters, one paragraph, practical and direct.
- reasoning_short: max 60 characters.

SCORING GUIDANCE (use the photo):
- fit_score: how well the garment fits (too tight/loose, pulling, bunching, shoulder seams, waist placement).
- proportion_score: whether it balances the user's silhouette (length, rise/waist position, sleeve/hem placement).
- color_harmony_score: how the color works with the user's visible coloring (contrast, washing out, clashes).
- style_score: how strong/coherent the style looks on the user (modern, intentional, cohesive).
- quality_cues_score: visible fabric/structure cues (sheen, drape, wrinkles, puckering seams, cheap-looking hardware, lining).

VERDICT LOGIC:
- "buy" if overall_score >= 78 and key_issues are minor/fixable.
- "maybe" if overall_score between 60-77 or needs tailoring/styling to shine.
- "skip" if overall_score < 60 or major fit/flattery issues.

Return ONLY the JSON object.
""".strip()


def build_image_to_text_outfit_prompt(output_schema: str) -> str:
    """
    Rate prompt: user is wearing an outfit (multiple pieces).
    Output: JSON only, score + review, does it suit them.
    Same schema keys as decide for consistent downstream handling.
    """
    return f"""
You are a fashion assistant. The user provided ONE photo of themselves wearing an outfit.

TASK:
- Analyze ONLY what is visible in the photo (no web browsing, no guessing about the user's preferences, wardrobe, or brand unless clearly visible).
- Evaluate how well the outfit suits the user: fit, proportions, color harmony, style cohesion, and visible quality/finish.
- Output ONLY valid JSON that matches this exact schema (same keys, no extra keys): {output_schema}

OUTPUT RULES:
- JSON only (no markdown, no commentary).
- Integers only for all *_score fields and overall_score.
- Score ranges:
  - overall_score: 0 to 100
  - all *_score: 1 to 10
- Arrays: max 4 items each, concise phrases.
- verdict must be exactly one of: "wear", "tweak", "avoid"
- suits_user must be true/false based on the photo.
- reasoning_long: max 240 characters, one paragraph, practical and direct.
- reasoning_short: max 60 characters.

SCORING GUIDANCE (use the photo):
- fit_score: fit across the outfit (shoulders, waist, hems, bunching/pulling).
- proportion_score: balance of top/bottom volumes, lengths, waist placement, leg line.
- color_harmony_score: whether colors work with each other AND the user’s visible coloring.
- style_score: cohesion/intentionality (do pieces look like they belong together).
- quality_cues_score: visible construction/finish (drape, wrinkles, shine, footwear condition, obvious cheap cues).

VERDICT LOGIC:
- "wear" if overall_score >= 78.
- "tweak" if overall_score between 60-77 (good base, needs styling fixes).
- "avoid" if overall_score < 60.

Return ONLY the JSON object.
""".strip()


def build_text_to_audio_prompt() -> str:
    """
    Instructions for TTS: we are NOT asking for analysis here.
    We want a clear spoken delivery of the already-produced review.
    """
    return """
You are a voice stylist reading a fashion verdict to the user.
Speak clearly and naturally. Sound helpful, confident, and concise.
Avoid reading raw JSON. Do not mention scores as “underscore”.
Keep it under ~20 seconds when possible.
""".strip()


# ----------------------------
# Helpers
# ----------------------------
def ensure_parent_dir(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def decode_and_save_image_from_request(body: dict, out_path: pathlib.Path) -> bool:
    """
    Supports:
    - body["image_data_url"] = "data:image/png;base64,...."
    - body["image_base64"] = "...." (raw base64)
    If none present, returns False (caller can use existing file).
    """
    image_data_url = body.get("image_data_url")
    image_b64 = body.get("image_base64")

    if not image_data_url and not image_b64:
        return False

    if image_data_url:
        # Parse "data:image/png;base64,AAAA"
        try:
            header, b64data = image_data_url.split(",", 1)
        except ValueError:
            raise ValueError("Invalid image_data_url format.")
        image_bytes = base64.b64decode(b64data)
    else:
        image_bytes = base64.b64decode(image_b64)

    ensure_parent_dir(out_path)
    out_path.write_bytes(image_bytes)
    return True


def encode_image_to_data_url(image_path: pathlib.Path) -> str:
    """
    Returns data URL suitable for OpenAI vision input.
    """
    suffix = image_path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def image_to_json_review(image_path: pathlib.Path, prompt: str) -> str:
    """
    Calls vision model and returns the model's output_text (expected JSON string).
    """
    data_url = encode_image_to_data_url(image_path)

    response = client.responses.create(
        model=image_to_text_model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
    )
    return (response.output_text or "").strip()


def safe_parse_json(text: str) -> dict | None:
    """
    Attempts to parse JSON from model output.
    Returns dict or None.
    """
    try:
        return json.loads(text)
    except Exception:
        return None


def review_json_to_spoken_text(review: dict, mode: str) -> str:
    """
    Converts the JSON review into a short spoken script for TTS.
    """
    # Fallback defaults
    overall = review.get("overall_score")
    verdict = review.get("verdict", "")
    suits = review.get("suits_user")
    short = review.get("reasoning_short", "")
    strengths = review.get("key_strengths") or []
    issues = review.get("key_issues") or []
    fixes = review.get("quick_improvements") or []

    # Keep it brief and friendly for audio
    if mode == "decide":
        verdict_line = {
            "buy": "My verdict: buy it.",
            "maybe": "My verdict: maybe—close, but not perfect.",
            "skip": "My verdict: skip it.",
        }.get(verdict, f"My verdict is: {verdict}.")
    else:
        verdict_line = {
            "wear": "This outfit is a strong wear.",
            "tweak": "This outfit is good, but needs a tweak.",
            "avoid": "I’d avoid this outfit as-is.",
        }.get(verdict, f"My verdict is: {verdict}.")

    suit_line = ""
    if isinstance(suits, bool):
        suit_line = "It suits you well." if suits else "It doesn’t flatter you as much as it could."

    # Compact bullet-like speech without sounding robotic
    parts = []
    if isinstance(overall, int):
        parts.append(f"Score: {overall} out of 100.")
    parts.append(verdict_line)
    if suit_line:
        parts.append(suit_line)

    if short:
        parts.append(short)

    if strengths:
        parts.append(f"Best part: {strengths[0]}.")
    if issues:
        parts.append(f"Main issue: {issues[0]}.")
    if fixes:
        parts.append(f"Quick fix: {fixes[0]}.")

    # Final cleanup
    script = " ".join([p.strip() for p in parts if str(p).strip()])
    return script.strip()


def conduct_text_to_speech(output_path: pathlib.Path, input_text: str, audio_instructions: str) -> None:
    ensure_parent_dir(output_path)

    # Streaming to file
    with client.audio.speech.with_streaming_response.create(
        model=text_to_audio_model,
        voice=audio_voice,
        input=input_text,
        instructions=audio_instructions,
    ) as response:
        response.stream_to_file(str(output_path))


def capture_image_from_camera_for_analysis(
    image_dir: pathlib.Path,
    camera_index: int = 0,
    warmup_frames: int = 5,
):
    """
    Captures a single frame from the camera and saves it to filename.
    Returns the saved image path.
    """
    import cv2
    new_filename = image_dir / "camera_capture.jpg"

    ensure_parent_dir(new_filename)

    cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)

    if not cap.isOpened():
        raise RuntimeError("Camera not opened")

    # Warm up camera (important on Pi / USB cams)
    frame = None
    for _ in range(warmup_frames):
        ret, frame = cap.read()

    cap.release()

    if frame is None or not ret:
        raise RuntimeError("Failed to capture image from camera")

    if not cv2.imwrite(str(new_filename), frame):
        raise RuntimeError("Failed to write image to disk")

    return new_filename

# ----------------------------
# Routes
# ----------------------------
@app.get("/health")
def health():
    return "ok", 200


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "webface.html")


@app.get("/api/audio/result.mp3")
def get_audio():
    if not output_audio_file_name.exists():
        return jsonify({"error": "No audio generated yet."}), 404
    return send_file(str(output_audio_file_name), mimetype="audio/mpeg")


@app.post("/api/cmd")
def cmd():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    body = request.get_json(force=True) or {}
    cmd_name = (body.get("cmd") or "").strip().lower()

    if cmd_name not in {"rate", "decide"}:
        return jsonify({"error": "cmd must be 'rate' or 'decide'"}), 400

    try:
        # Start fast LED flash for image capture
        led.flash_fast(times=5)

        # Call helper to capture image from camera
        input_image_file_name_new = capture_image_from_camera_for_analysis(IMAGE_INPUT_DATA_DIR)

        # Save image from request if provided, otherwise use existing file
        decode_and_save_image_from_request(body, input_image_file_name_new)

        # Start non-blocking LED + audio indicators
        led.stop() # Stop any prior LED activity
        led.start_background_blink(interval=0.3)
        audio_player.play(filler_audio_file_name)

        if not input_image_file_name_new.exists():
            return jsonify({"error": f"Missing input image at {str(input_image_file_name_new)}"}), 400

        # Build correct prompt per mode
        if cmd_name == "rate":
            prompt = build_image_to_text_outfit_prompt(REVIEW_SCHEMA)
            mode = "rate"
        else:
            prompt = build_image_to_text_decide_prompt(REVIEW_SCHEMA)
            mode = "decide"

        # Vision -> JSON review
        review_text = image_to_json_review(input_image_file_name, prompt)

        # Flash LED at medium speed to indicate analysis done
        led.stop() # Stop prior activity
        led.flash_medium(times=5)

        # Save raw output for debugging
        ensure_parent_dir(output_text_file_name)
        output_text_file_name.write_text(review_text, encoding="utf-8")

        review_json = safe_parse_json(review_text)

        # If the model returns non-JSON, still TTS it, but return an error field
        if review_json is None:
            spoken_text = review_text[:1200]  # avoid huge audio
            conduct_text_to_speech(output_audio_file_name, spoken_text, build_text_to_audio_prompt())
            return jsonify({
                "ok": False,
                "mode": mode,
                "error": "Model did not return valid JSON. Audio was generated from raw text.",
                "raw_text_path": str(output_text_file_name),
                "audio_url": "/api/audio/result.mp3",
                "raw_output": review_text
            }), 200

        # JSON -> Spoken script -> TTS
        spoken_text = review_json_to_spoken_text(review_json, mode=mode)
        conduct_text_to_speech(output_audio_file_name, spoken_text, build_text_to_audio_prompt())

        # Start non-blocking
        led.stop() # Stop prior activity
        led.start_background_blink(interval=0.3) 

        # Play the generated audio
        audio_player.stop()  # Stop any filler audio
        audio_player.play(output_audio_file_name)

        return jsonify({
            "ok": True,
            "mode": mode,
            "review": review_json,
            "spoken_text": spoken_text,
            "audio_url": "/api/audio/result.mp3",
            "raw_text_path": str(output_text_file_name)
        }), 200

    except Exception as e:
        app.logger.exception("Smart mirror project crashed")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Only initialize hardware in the child process
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        try:
            led = StatusLED(pin=23)
            led.always_on()
            audio_player = AudioPlayer()
            audio_player.stop()
        except Exception as e:
            app.logger.exception("Failed to initialize hardware")

    app.run(host="0.0.0.0", port=8080, debug=True)
