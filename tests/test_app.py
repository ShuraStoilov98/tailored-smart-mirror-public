"""Offline regression checks; synthetic images and fake hardware/provider only."""
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from smart_mirror import create_app
from smart_mirror import controller, images, provider
from smart_mirror.errors import InvalidReview
from smart_mirror.prompts import REVIEW_SCHEMA


def sample_review(mode="rate"):
    review = json.loads(REVIEW_SCHEMA)
    review.update(overall_score=75, verdict="tweak" if mode == "rate" else "maybe",
                  suits_user=True, reasoning_short="Try a shorter hem.")
    for key in review:
        if key.endswith("_score") and key != "overall_score":
            review[key] = 7
    return review


def synthetic_image():
    stream = io.BytesIO()
    image = Image.new("RGB", (16, 16), "blue")
    exif = Image.Exif()
    exif[270] = "synthetic private metadata"
    image.save(stream, "PNG", exif=exif)
    return base64.b64encode(stream.getvalue()).decode("ascii")


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.hardware = Mock()
        self.client = Mock()
        self.app = create_app({"TESTING": True, "DATA_DIR": self.directory,
                                    "ACCESS_TOKEN": "synthetic-test-token"},
                                   hardware=self.hardware, client=self.client)
        self.http = self.app.test_client()
        self.headers = {"X-Mirror-Token": "synthetic-test-token"}

    def post(self, body):
        return self.http.post("/api/cmd", json=body, headers=self.headers)

    def test_index_health_and_no_store(self):
        page = self.http.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'synthetic-test-token', page.data)
        self.assertIn(b'AI-generated', page.data)
        self.assertEqual(page.headers["Cache-Control"], "no-store")
        self.assertEqual(self.http.get("/health").data, b"ok")

    def test_auth_guards_capture_and_audio(self):
        self.assertEqual(self.http.post("/api/cmd", json={"cmd": "rate"}).status_code, 401)
        self.assertEqual(self.http.get("/api/audio/result.mp3").status_code, 401)
        self.hardware.led.flash_fast.assert_not_called()

    def test_untrusted_host_and_origin(self):
        self.assertEqual(self.http.get("/", headers={"Host": "attacker.example"}).status_code, 400)
        response = self.http.post("/api/cmd", json={"cmd": "rate"},
                                 headers={**self.headers, "Origin": "https://attacker.example"})
        self.assertEqual(response.status_code, 403)

    def test_malformed_bodies(self):
        for body in ([], None, {"cmd": 12}, {"cmd": "shell"}, {"cmd": "rate", "path": "/private"}):
            with self.subTest(body=body):
                self.assertEqual(self.post(body).status_code, 400)
        self.assertEqual(self.http.post("/api/cmd", data="{", content_type="application/json",
                                        headers=self.headers).status_code, 400)

    def test_size_limit_before_hardware(self):
        self.app.config["MAX_CONTENT_LENGTH"] = 50
        self.assertEqual(self.post({"cmd": "rate", "image_base64": "a" * 100}).status_code, 413)
        self.hardware.led.flash_fast.assert_not_called()

    def test_bad_upload_never_opens_camera(self):
        for fields in ({"image_base64": "bad!"}, {"image_base64": 4},
                       {"image_data_url": "data:text/html;base64,AAAA"},
                       {"image_base64": ""}, {"image_base64": "AAAA", "image_data_url": "x"}):
            with self.subTest(fields=fields), patch.object(controller, "capture_image") as capture:
                self.assertEqual(self.post({"cmd": "rate", **fields}).status_code, 400)
                capture.assert_not_called()
                self.assertFalse(list(self.directory.iterdir()))

    def test_image_normalization_discards_metadata(self):
        path = self.directory / "input.jpg"
        images.decode_and_save_image_from_request({"image_base64": synthetic_image()}, path)
        with Image.open(path) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertFalse(image.getexif())

    def test_pixel_bomb_rejected(self):
        with patch.object(images, "MAX_IMAGE_PIXELS", 100):
            self.assertEqual(self.post({"cmd": "rate", "image_base64": synthetic_image()}).status_code, 400)

    def test_success_upload_skips_camera_and_plays_audio(self):
        def tts(path, *args):
            path.write_bytes(b"synthetic-audio")
        for mode in ("rate", "decide"):
            with self.subTest(mode=mode), \
                 patch.object(controller, "capture_image") as capture, \
                 patch.object(provider, "image_to_json_review", return_value=json.dumps(sample_review(mode))), \
                 patch.object(provider, "conduct_text_to_speech", side_effect=tts):
                response = self.post({"cmd": mode, "image_base64": synthetic_image()})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json["ok"])
                self.assertEqual((self.directory / "result.mp3").stat().st_mode & 0o777, 0o600)
                self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
                self.assertNotIn("raw_text_path", response.json)
                capture.assert_not_called()
                self.assertFalse((self.directory / "camera_capture.jpg").exists())
                audio = self.http.get(response.json["audio_url"], headers=self.headers)
                self.assertEqual(audio.data, b"synthetic-audio")
                audio.close()
        self.hardware.audio.play.assert_called()
        self.hardware.led.always_on.assert_called()

    def test_invalid_provider_output_is_not_spoken_or_returned(self):
        for text in ('{"private": "synthetic-sensitive-data"}', '[]', 'null', 'unstructured reply'):
            with self.subTest(text=text), patch.object(provider, "image_to_json_review", return_value=text), \
                 patch.object(provider, "conduct_text_to_speech") as tts:
                response = self.post({"cmd": "rate", "image_base64": synthetic_image()})
                self.assertEqual(response.status_code, 502)
                self.assertNotIn(text.encode(), response.data)
                tts.assert_not_called()
                self.assertFalse(list(self.directory.iterdir()))
                self.hardware.audio.stop.assert_called()

    def test_provider_failure_preserves_previous_audio_and_releases_lock(self):
        (self.directory / "result.mp3").write_bytes(b"old-private-audio")
        with patch.object(provider, "image_to_json_review", side_effect=RuntimeError("synthetic-sensitive-data")):
            for _ in range(2):
                response = self.post({"cmd": "rate", "image_base64": synthetic_image()})
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(b"synthetic-sensitive-data", response.data)
                self.assertEqual((self.directory / "result.mp3").read_bytes(), b"old-private-audio")
                self.assertEqual(len(list(self.directory.iterdir())), 1)

    def test_partial_tts_failure_cleans_audio(self):
        def fail(path, *args):
            path.write_bytes(b"partial")
            raise RuntimeError("synthetic-sensitive-data")
        with patch.object(provider, "image_to_json_review", return_value=json.dumps(sample_review())), \
             patch.object(provider, "conduct_text_to_speech", side_effect=fail):
            self.assertEqual(self.post({"cmd": "rate", "image_base64": synthetic_image()}).status_code, 503)
            self.assertFalse(list(self.directory.iterdir()))

    def test_concurrent_requests_and_audio_are_busy(self):
        entered, release = threading.Event(), threading.Event()
        def blocking_review(*args):
            entered.set()
            release.wait(timeout=5)
            raise InvalidReview()
        with patch.object(provider, "image_to_json_review", side_effect=blocking_review):
            worker = threading.Thread(target=lambda: self.app.test_client().post(
                "/api/cmd", json={"cmd": "rate", "image_base64": synthetic_image()}, headers=self.headers))
            worker.start()
            try:
                self.assertTrue(entered.wait(timeout=5))
                self.assertEqual(self.post({"cmd": "decide"}).status_code, 409)
                self.assertEqual(self.http.get("/api/audio/result.mp3", headers=self.headers).status_code, 409)
            finally:
                release.set()
                worker.join(timeout=5)
            self.assertFalse(worker.is_alive())

    def test_missing_key_requires_no_hardware(self):
        app = create_app({"TESTING": True, "API_KEY": "", "DATA_DIR": self.directory,
                               "ACCESS_TOKEN": "synthetic-test-token"})
        with patch.object(controller, "Hardware") as hardware:
            response = app.test_client().post("/api/cmd", json={"cmd": "rate"}, headers=self.headers)
            self.assertEqual(response.status_code, 503)
            hardware.assert_not_called()

    def test_cleanup_failure_still_releases_command_lock(self):
        self.hardware.led.always_on.side_effect = RuntimeError("LED unavailable")
        with patch.object(provider, "image_to_json_review", side_effect=InvalidReview()):
            for _ in range(2):
                self.assertEqual(self.post({"cmd": "rate", "image_base64": synthetic_image()}).status_code, 502)

    def test_close_releases_hardware_and_removes_audio(self):
        (self.directory / "result.mp3").write_bytes(b"synthetic-audio")
        self.app.extensions["mirror_close"]()
        self.hardware.close.assert_called_once()
        self.client.close.assert_called_once()
        self.assertFalse(list(self.directory.iterdir()))

    def test_close_failure_still_removes_private_files(self):
        (self.directory / "result.mp3").write_bytes(b"synthetic-audio")
        self.hardware.close.side_effect = RuntimeError("driver failed")
        with self.assertRaises(RuntimeError):
            self.app.extensions["mirror_close"]()
        self.assertFalse(list(self.directory.iterdir()))

    def test_unicode_token_is_unauthorized_not_server_error(self):
        response = self.http.post("/api/cmd", json={"cmd": "rate"},
                                  headers={"X-Mirror-Token": "synthetic-café-token"})
        self.assertEqual(response.status_code, 401)

    def test_bad_upload_preserves_previous_result_and_does_not_touch_hardware(self):
        (self.directory / "result.mp3").write_bytes(b"previous-result")
        self.assertEqual(self.post({"cmd": "rate", "image_base64": "bad!"}).status_code, 400)
        self.assertEqual((self.directory / "result.mp3").read_bytes(), b"previous-result")
        self.hardware.audio.stop.assert_not_called()
        self.hardware.led.always_on.assert_not_called()

    def test_partial_tts_is_never_published(self):
        (self.directory / "result.mp3").write_bytes(b"previous-result")
        def fail(path, *args):
            path.write_bytes(b"partial")
            self.assertEqual((self.directory / "result.mp3").read_bytes(), b"previous-result")
            raise RuntimeError("failed")
        with patch.object(provider, "image_to_json_review", return_value=json.dumps(sample_review())), \
             patch.object(provider, "conduct_text_to_speech", side_effect=fail):
            self.assertEqual(self.post({"cmd": "rate", "image_base64": synthetic_image()}).status_code, 503)
        self.assertEqual((self.directory / "result.mp3").read_bytes(), b"previous-result")
        self.assertEqual(len(list(self.directory.iterdir())), 1)

    def test_audio_response_is_stable_after_later_replacement(self):
        audio_path = self.directory / "result.mp3"
        audio_path.write_bytes(b"first-result")
        response = self.http.get("/api/audio/result.mp3", headers=self.headers)
        audio_path.write_bytes(b"second-result")
        self.assertEqual(response.data, b"first-result")
        response.close()

    def test_shutdown_is_idempotent_and_rejects_new_analysis(self):
        close = self.app.extensions["mirror_close"]
        close()
        close()
        self.hardware.close.assert_called_once()
        self.client.close.assert_called_once()
        self.assertEqual(self.post({"cmd": "rate"}).status_code, 503)
        self.hardware.led.flash_fast.assert_not_called()

    def test_security_policy_uses_external_scripts_and_styles(self):
        response = self.http.get("/")
        self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
        self.assertNotIn(b"onclick=", response.data)
        self.assertNotIn(b"<style>", response.data)
        for path in ("/static/js/mirror.js", "/static/css/mirror.css"):
            asset = self.http.get(path)
            self.assertEqual(asset.status_code, 200)
            asset.close()

    def test_oversized_json_has_a_json_error(self):
        self.app.config["MAX_CONTENT_LENGTH"] = 50
        response = self.post({"cmd": "rate", "image_base64": "a" * 100})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json["error"], "Request is too large")

    def test_audio_read_failure_is_generic(self):
        with patch.object(self.app.extensions["mirror_controller"], "read_audio",
                          side_effect=PermissionError("synthetic-private-path")):
            response = self.http.get("/api/audio/result.mp3", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"synthetic-private-path", response.data)

    def test_shutdown_waits_for_in_flight_work(self):
        entered, release, closing = threading.Event(), threading.Event(), threading.Event()
        def blocking_review(*args):
            entered.set()
            release.wait(timeout=5)
            raise InvalidReview()
        def shutdown():
            closing.set()
            self.app.extensions["mirror_close"]()
        with patch.object(provider, "image_to_json_review", side_effect=blocking_review):
            worker = threading.Thread(target=lambda: self.app.test_client().post(
                "/api/cmd", json={"cmd": "rate", "image_base64": synthetic_image()}, headers=self.headers))
            worker.start()
            closer = threading.Thread(target=shutdown)
            try:
                self.assertTrue(entered.wait(timeout=5))
                closer.start()
                self.assertTrue(closing.wait(timeout=5))
                self.hardware.close.assert_not_called()
            finally:
                release.set()
                worker.join(timeout=5)
                if closer.ident is not None:
                    closer.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertFalse(closer.is_alive())
        self.hardware.close.assert_called_once()
        self.client.close.assert_called_once()

    def test_playback_failure_preserves_previous_successful_audio(self):
        (self.directory / "result.mp3").write_bytes(b"previous-result")
        self.hardware.audio.play.side_effect = RuntimeError("speaker failed")
        def tts(path, *args):
            path.write_bytes(b"complete-new-audio")
        with patch.object(provider, "image_to_json_review", return_value=json.dumps(sample_review())), \
             patch.object(provider, "conduct_text_to_speech", side_effect=tts):
            self.assertEqual(self.post({"cmd": "rate", "image_base64": synthetic_image()}).status_code, 503)
        self.assertEqual((self.directory / "result.mp3").read_bytes(), b"previous-result")
        self.assertEqual(len(list(self.directory.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
