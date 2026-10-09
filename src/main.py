"""Local smart-mirror controller: one camera, one LED, one audio player."""
import base64
import binascii
import io
import json
import os
from pathlib import Path
import secrets
from threading import Lock
import warnings

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request, send_file
from openai import OpenAI
from PIL import Image, ImageOps, UnidentifiedImageError

BASE_DIR = Path(__file__).resolve().parent
Image.MAX_IMAGE_PIXELS = 12_000_000

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


class InvalidImage(ValueError):
    """An uploaded image failed validation."""


class InvalidReview(ValueError):
    """The provider returned a review outside the expected contract."""


def decode_and_save_image_from_request(body: dict, out_path: Path) -> bool:
    """Validate JPEG/PNG data, normalize to JPEG and discard EXIF metadata."""
    fields = [key for key in ("image_data_url", "image_base64") if key in body]
    if not fields:
        return False
    if len(fields) != 1 or not isinstance(body[fields[0]], str):
        raise InvalidImage("Provide one base64 image string.")
    encoded = body[fields[0]]
    if fields[0] == "image_data_url":
        header, separator, encoded = encoded.partition(",")
        if not separator or header not in {"data:image/jpeg;base64", "data:image/png;base64"}:
            raise InvalidImage("Only JPEG and PNG data URLs are accepted.")
    try:
        raw = base64.b64decode(encoded, validate=True)
        if not raw or len(raw) > 6 * 1024 * 1024:
            raise InvalidImage("Image is empty or too large.")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise InvalidImage("Only JPEG and PNG images are accepted.")
                image.load()
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                normalized.info.clear()
                normalized.save(out_path, format="JPEG", quality=90)
    except (binascii.Error, UnidentifiedImageError, OSError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidImage("Invalid or oversized JPEG/PNG image.") from exc
    return True


def image_to_json_review(image_path: Path, prompt: str, client, model: str) -> str:
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    response = client.responses.create(
        model=model,
        store=False,
        max_output_tokens=1200,
        input=[{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}"},
        ]}],
    )
    return (response.output_text or "").strip()


def validate_review(text: str, mode: str) -> dict:
    """Reject malformed/provider-invented fields before rendering or speaking."""
    try:
        review = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidReview("Invalid review JSON.") from exc
    schema = json.loads(REVIEW_SCHEMA)
    if not isinstance(review, dict) or set(review) != set(schema):
        raise InvalidReview("Unexpected review fields.")
    for key in schema:
        value = review[key]
        if key.endswith("_score"):
            minimum, maximum = (0, 100) if key == "overall_score" else (1, 10)
            if type(value) is not int or not minimum <= value <= maximum:
                raise InvalidReview("Invalid review score.")
        elif key == "suits_user":
            if type(value) is not bool:
                raise InvalidReview("Invalid suitability value.")
        elif isinstance(schema[key], list):
            if not isinstance(value, list) or len(value) > 4 or any(
                not isinstance(item, str) or len(item) > 160 for item in value
            ):
                raise InvalidReview("Invalid review list.")
        else:
            maximum = {"reasoning_long": 240, "reasoning_short": 60}.get(key, 160)
            if not isinstance(value, str) or len(value) > maximum:
                raise InvalidReview("Invalid review text.")
    verdicts = {"buy", "maybe", "skip"} if mode == "decide" else {"wear", "tweak", "avoid"}
    if review["verdict"] not in verdicts:
        raise InvalidReview("Invalid verdict.")
    return review


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


def conduct_text_to_speech(output_path: Path, input_text: str, client, config) -> None:
    with client.audio.speech.with_streaming_response.create(
        model=config["TTS_MODEL"], voice=config["TTS_VOICE"], input=input_text,
        instructions=build_text_to_audio_prompt(), response_format="mp3",
    ) as response:
        response.stream_to_file(str(output_path))


def capture_image_from_camera_for_analysis(image_dir: Path, camera_index=0, warmup_frames=5):
    """Read a USB/V4L2 camera; release it even if capture or writing fails."""
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


class Hardware:
    """Allocate devices only when an authenticated capture request needs them."""
    def __init__(self, pin):
        from led_helper import StatusLED
        from audio_helper import AudioPlayer

        self.led = StatusLED(pin=pin)
        try:
            self.audio = AudioPlayer()
        except Exception:
            self.led.close()
            raise

    def close(self):
        try:
            self.audio.close()
        finally:
            self.led.close()


def create_app(config=None, *, hardware=None, client=None):
    """Importable without a key or GPIO; inject fakes for offline tests."""
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.update(
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"],
        ACCESS_TOKEN=secrets.token_urlsafe(32),
        DATA_DIR=BASE_DIR.parent / "runtime",
        API_KEY=os.getenv("OPENAI_API_KEY", ""),
        VISION_MODEL=os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini"),
        TTS_MODEL=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
        TTS_VOICE=os.getenv("OPENAI_TTS_VOICE", "alloy"),
        CAMERA_INDEX=int(os.getenv("MIRROR_CAMERA_INDEX", "0")),
        LED_PIN=int(os.getenv("MIRROR_LED_PIN", "23")),
    )
    if config:
        app.config.update(config)
    command_lock = Lock()
    devices, provider = hardware, client
    output_audio = Path(app.config["DATA_DIR"]) / "result.mp3"

    @app.before_request
    def protect_api():
        if request.path.startswith("/api/"):
            supplied = request.headers.get("X-Mirror-Token", "")
            if not secrets.compare_digest(supplied, app.config["ACCESS_TOKEN"]):
                return jsonify(error="Unauthorized"), 401
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                return jsonify(error="Untrusted origin"), 403

    @app.after_request
    def privacy_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/health")
    def health():
        return "ok", 200

    @app.get("/")
    def index():
        return render_template_string(
            (BASE_DIR / "static" / "webface.html").read_text(encoding="utf-8"),
            access_token=app.config["ACCESS_TOKEN"],
        )

    @app.get("/api/audio/result.mp3")
    def get_audio():
        if not command_lock.acquire(blocking=False):
            return jsonify(error="Mirror is busy"), 409
        try:
            if not output_audio.exists():
                return jsonify(error="No audio generated yet"), 404
            return send_file(output_audio, mimetype="audio/mpeg")
        finally:
            command_lock.release()

    @app.post("/api/cmd")
    def cmd():
        nonlocal devices, provider
        if not request.is_json:
            return jsonify(error="Request must be JSON"), 400
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("cmd"), str):
            return jsonify(error="Provide a command object"), 400
        mode = body["cmd"].strip().lower()
        if mode not in {"rate", "decide"} or set(body) - {"cmd", "image_data_url", "image_base64"}:
            return jsonify(error="cmd must be 'rate' or 'decide'; unexpected fields are rejected"), 400
        if not command_lock.acquire(blocking=False):
            return jsonify(error="Mirror is busy"), 409
        image_path = output_audio.parent / "camera_capture.jpg"
        succeeded = False
        try:
            output_audio.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            output_audio.unlink(missing_ok=True)
            uploaded = decode_and_save_image_from_request(body, image_path)
            if provider is None:
                if not app.config["API_KEY"]:
                    return jsonify(error="Set OPENAI_API_KEY locally before analysis"), 503
                provider = OpenAI(api_key=app.config["API_KEY"], timeout=45.0, max_retries=0)
            if devices is None:
                devices = Hardware(app.config["LED_PIN"])
            devices.led.flash_fast(times=5)
            if not uploaded:
                image_path = capture_image_from_camera_for_analysis(
                    image_path.parent, camera_index=app.config["CAMERA_INDEX"]
                )
            devices.led.start_background_blink(interval=0.3)
            prompt = (build_image_to_text_outfit_prompt if mode == "rate"
                      else build_image_to_text_decide_prompt)(REVIEW_SCHEMA)
            text = image_to_json_review(image_path, prompt, provider, app.config["VISION_MODEL"])
            review = validate_review(text, mode)
            spoken = review_json_to_spoken_text(review, mode)
            conduct_text_to_speech(output_audio, spoken, provider, app.config)
            devices.audio.play(output_audio)
            succeeded = True
            return jsonify(ok=True, mode=mode, review=review, spoken_text=spoken,
                           audio_url="/api/audio/result.mp3")
        except InvalidImage as exc:
            return jsonify(error=str(exc)), 400
        except InvalidReview:
            return jsonify(error="The provider returned an invalid review; please retry"), 502
        except Exception:
            # Tracebacks/SDK errors may contain private data; do not return or log them.
            app.logger.error("Mirror analysis failed; check hardware and provider configuration")
            return jsonify(error="Analysis failed; check camera, speaker and provider configuration"), 503
        finally:
            cleanups = [lambda: image_path.unlink(missing_ok=True)]
            if not succeeded:
                cleanups.append(lambda: output_audio.unlink(missing_ok=True))
            if devices is not None:
                if not succeeded:
                    cleanups.append(devices.audio.stop)
                cleanups.append(devices.led.always_on)
            try:
                for cleanup in cleanups:
                    try:
                        cleanup()
                    except Exception:
                        app.logger.error("Mirror cleanup failed; check local device state")
            finally:
                command_lock.release()

    def close():
        try:
            if devices is not None:
                devices.close()
        finally:
            try:
                output_audio.unlink(missing_ok=True)
            finally:
                (output_audio.parent / "camera_capture.jpg").unlink(missing_ok=True)

    app.extensions["mirror_close"] = close
    return app


if __name__ == "__main__":
    os.umask(0o077)
    load_dotenv(BASE_DIR.parent / "secrets" / ".env", override=False)
    app = create_app()
    try:
        app.run(host="127.0.0.1", port=8080, debug=False, use_reloader=False, threaded=True)
    finally:
        app.extensions["mirror_close"]()
