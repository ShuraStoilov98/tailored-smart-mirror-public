"""Environment defaults and validated controller settings."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import secrets

SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = SRC_DIR.parent


def default_config() -> dict:
    return {
        "MAX_CONTENT_LENGTH": 8 * 1024 * 1024,
        "TRUSTED_HOSTS": ["localhost", "127.0.0.1", "[::1]"],
        "ACCESS_TOKEN": secrets.token_urlsafe(32),
        "DATA_DIR": PROJECT_DIR / "runtime",
        "API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "VISION_MODEL": os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini"),
        "TTS_MODEL": os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
        "TTS_VOICE": os.getenv("OPENAI_TTS_VOICE", "alloy"),
        "CAMERA_INDEX": os.getenv("MIRROR_CAMERA_INDEX", "0"),
        "LED_PIN": os.getenv("MIRROR_LED_PIN", "23"),
    }


def _integer(config: dict, name: str, minimum: int, maximum: int) -> int:
    value = config[name]
    if type(value) not in (str, int):
        raise ValueError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


@dataclass(frozen=True)
class MirrorSettings:
    data_dir: Path
    api_key: str = field(repr=False)
    vision_model: str
    tts_model: str
    tts_voice: str
    camera_index: int
    led_pin: int

    @classmethod
    def from_config(cls, config: dict):
        for key in ("VISION_MODEL", "TTS_MODEL", "TTS_VOICE", "ACCESS_TOKEN"):
            if not isinstance(config[key], str) or not config[key].strip():
                raise ValueError(f"{key} must be a nonempty string")
        if not isinstance(config["API_KEY"], str):
            raise ValueError("API_KEY must be a string")
        config["CAMERA_INDEX"] = _integer(config, "CAMERA_INDEX", 0, 255)
        config["LED_PIN"] = _integer(config, "LED_PIN", 0, 27)
        config["MAX_CONTENT_LENGTH"] = _integer(config, "MAX_CONTENT_LENGTH", 1, 8 * 1024 * 1024)
        # Reject empty paths: they would place private output in the project root.
        if not isinstance(config["DATA_DIR"], (str, Path)) or not str(config["DATA_DIR"]).strip():
            raise ValueError("DATA_DIR must be a nonempty directory path")
        config["DATA_DIR"] = Path(config["DATA_DIR"]).absolute()
        return cls(config["DATA_DIR"], config["API_KEY"], config["VISION_MODEL"],
                   config["TTS_MODEL"], config["TTS_VOICE"],
                   config["CAMERA_INDEX"], config["LED_PIN"])
