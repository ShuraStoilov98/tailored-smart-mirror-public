"""Lazy OpenAI integration; no network calls or credentials needed at import."""
import base64
from pathlib import Path

from openai import OpenAI

from .errors import InvalidReview, MirrorUnavailable
from .prompts import (REVIEW_SCHEMA, build_image_to_text_decide_prompt,
                      build_image_to_text_outfit_prompt, build_text_to_audio_prompt)
from .review import validate_review


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


def conduct_text_to_speech(output_path: Path, input_text: str, client, config) -> None:
    with client.audio.speech.with_streaming_response.create(
        model=config["TTS_MODEL"], voice=config["TTS_VOICE"], input=input_text,
        instructions=build_text_to_audio_prompt(), response_format="mp3",
    ) as response:
        response.stream_to_file(str(output_path))


class OpenAIProvider:
    def __init__(self, settings, client=None):
        self.settings = settings
        self._client = client

    def prepare(self):
        if self._client is None:
            if not self.settings.api_key.strip():
                raise MirrorUnavailable("Set OPENAI_API_KEY locally before analysis")
            self._client = OpenAI(api_key=self.settings.api_key, timeout=45.0, max_retries=0)

    def review(self, image_path: Path, mode: str) -> dict:
        if mode not in {"rate", "decide"}:
            raise InvalidReview("Unknown review mode.")
        self.prepare()
        prompt_builder = (build_image_to_text_decide_prompt if mode == "decide"
                          else build_image_to_text_outfit_prompt)
        text = image_to_json_review(image_path, prompt_builder(REVIEW_SCHEMA),
                                    self._client, self.settings.vision_model)
        return validate_review(text, mode)

    def speak(self, text: str, destination: Path) -> None:
        self.prepare()
        conduct_text_to_speech(destination, text, self._client, {
            "TTS_MODEL": self.settings.tts_model, "TTS_VOICE": self.settings.tts_voice,
        })

    def close(self):
        client, self._client = self._client, None
        if client is not None:
            client.close()
