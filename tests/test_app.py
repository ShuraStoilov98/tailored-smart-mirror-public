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
import main


def sample_review(mode="rate"):
    review = json.loads(main.REVIEW_SCHEMA)
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
        self.app = main.create_app({"TESTING": True, "DATA_DIR": self.directory,
                                    "ACCESS_TOKEN": "synthetic-test-token"},
                                   hardware=self.hardware, client=Mock())
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
            with self.subTest(fields=fields), patch.object(main, "capture_image_from_camera_for_analysis") as capture:
                self.assertEqual(self.post({"cmd": "rate", **fields}).status_code, 400)
                capture.assert_not_called()
                self.assertFalse(list(self.directory.iterdir()))

    def test_image_normalization_discards_metadata(self):
        path = self.directory / "input.jpg"
        main.decode_and_save_image_from_request({"image_base64": synthetic_image()}, path)
        with Image.open(path) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertFalse(image.getexif())

    def test_pixel_bomb_rejected(self):
        with patch.object(main.Image, "MAX_IMAGE_PIXELS", 100):
            self.assertEqual(self.post({"cmd": "rate", "image_base64": synthetic_image()}).status_code, 400)

    def test_success_upload_skips_camera_and_plays_audio(self):
        def tts(path, *args):
            path.write_bytes(b"synthetic-audio")
        for mode in ("rate", "decide"):
            with self.subTest(mode=mode), \
                 patch.object(main, "capture_image_from_camera_for_analysis") as capture, \
                 patch.object(main, "image_to_json_review", return_value=json.dumps(sample_review(mode))), \
                 patch.object(main, "conduct_text_to_speech", side_effect=tts):
                response = self.post({"cmd": mode, "image_base64": synthetic_image()})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json["ok"])
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
            with self.subTest(text=text), patch.object(main, "image_to_json_review", return_value=text), \
                 patch.object(main, "conduct_text_to_speech") as tts:
                response = self.post({"cmd": "rate", "image_base64": synthetic_image()})
                self.assertEqual(response.status_code, 502)
                self.assertNotIn(text.encode(), response.data)
                tts.assert_not_called()
                self.assertFalse(list(self.directory.iterdir()))
                self.hardware.audio.stop.assert_called()

    def test_provider_failure_removes_previous_audio_and_releases_lock(self):
        (self.directory / "result.mp3").write_bytes(b"old-private-audio")
        with patch.object(main, "image_to_json_review", side_effect=RuntimeError("synthetic-sensitive-data")):
            for _ in range(2):
                response = self.post({"cmd": "rate", "image_base64": synthetic_image()})
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(b"synthetic-sensitive-data", response.data)
                self.assertFalse(list(self.directory.iterdir()))

    def test_partial_tts_failure_cleans_audio(self):
        def fail(path, *args):
            path.write_bytes(b"partial")
            raise RuntimeError("synthetic-sensitive-data")
        with patch.object(main, "image_to_json_review", return_value=json.dumps(sample_review())), \
             patch.object(main, "conduct_text_to_speech", side_effect=fail):
            self.assertEqual(self.post({"cmd": "rate", "image_base64": synthetic_image()}).status_code, 503)
            self.assertFalse(list(self.directory.iterdir()))

    def test_concurrent_requests_and_audio_are_busy(self):
        entered, release = threading.Event(), threading.Event()
        def blocking_review(*args):
            entered.set()
            release.wait(timeout=5)
            raise main.InvalidReview()
        with patch.object(main, "image_to_json_review", side_effect=blocking_review):
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
        app = main.create_app({"TESTING": True, "API_KEY": "", "DATA_DIR": self.directory,
                               "ACCESS_TOKEN": "synthetic-test-token"})
        with patch.object(main, "Hardware") as hardware:
            response = app.test_client().post("/api/cmd", json={"cmd": "rate"}, headers=self.headers)
            self.assertEqual(response.status_code, 503)
            hardware.assert_not_called()

    def test_cleanup_failure_still_releases_command_lock(self):
        self.hardware.led.always_on.side_effect = RuntimeError("LED unavailable")
        with patch.object(main, "image_to_json_review", side_effect=main.InvalidReview()):
            for _ in range(2):
                self.assertEqual(self.post({"cmd": "rate", "image_base64": synthetic_image()}).status_code, 502)

    def test_close_releases_hardware_and_removes_audio(self):
        (self.directory / "result.mp3").write_bytes(b"synthetic-audio")
        self.app.extensions["mirror_close"]()
        self.hardware.close.assert_called_once()
        self.assertFalse(list(self.directory.iterdir()))

    def test_close_failure_still_removes_private_files(self):
        (self.directory / "result.mp3").write_bytes(b"synthetic-audio")
        (self.directory / "camera_capture.jpg").write_bytes(b"synthetic-image")
        self.hardware.close.side_effect = RuntimeError("driver failed")
        with self.assertRaises(RuntimeError):
            self.app.extensions["mirror_close"]()
        self.assertFalse(list(self.directory.iterdir()))


class ReviewTests(unittest.TestCase):
    def test_rejects_wrong_types_ranges_and_verdicts(self):
        for key, value in (("fit_score", True), ("overall_score", 101), ("fit_score", 0),
                           ("suits_user", "true"), ("key_issues", "text"),
                           ("reasoning_short", "x" * 61), ("verdict", "buy")):
            with self.subTest(key=key):
                review = sample_review()
                review[key] = value
                with self.assertRaises(main.InvalidReview):
                    main.validate_review(json.dumps(review), "rate")

    def test_vision_request_does_not_store_response(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.jpg"
            path.write_bytes(b"synthetic-image")
            provider = Mock()
            provider.responses.create.return_value.output_text = "{}"
            main.image_to_json_review(path, "prompt", provider, "gpt-4o-mini")
            self.assertFalse(provider.responses.create.call_args.kwargs["store"])

    def test_capture_releases_failed_device(self):
        cap = Mock()
        cap.isOpened.return_value = False
        cv2 = Mock()
        cv2.VideoCapture.return_value = cap
        with patch.dict(sys.modules, {"cv2": cv2}), tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                main.capture_image_from_camera_for_analysis(Path(directory))
            cap.release.assert_called_once()

    def test_capture_releases_device_on_read_exception(self):
        cap = Mock()
        cap.read.side_effect = RuntimeError("driver failed")
        cv2 = Mock()
        cv2.VideoCapture.return_value = cap
        with patch.dict(sys.modules, {"cv2": cv2}), tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                main.capture_image_from_camera_for_analysis(Path(directory))
            cap.release.assert_called_once()

    def test_capture_releases_device_on_write_failure(self):
        cap = Mock()
        cap.read.return_value = (True, object())
        cv2 = Mock()
        cv2.VideoCapture.return_value = cap
        cv2.imwrite.return_value = False
        with patch.dict(sys.modules, {"cv2": cv2}), tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                main.capture_image_from_camera_for_analysis(Path(directory))
            cap.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
