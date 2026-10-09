"""Review contract and camera resource checks without physical devices."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from smart_mirror.errors import InvalidReview
from smart_mirror.review import validate_review
from smart_mirror.provider import image_to_json_review
from smart_mirror.devices.camera import capture_image
from test_app import sample_review


class ReviewTests(unittest.TestCase):
    def test_rejects_wrong_types_ranges_and_verdicts(self):
        for key, value in (("fit_score", True), ("overall_score", 101), ("fit_score", 0),
                           ("suits_user", "true"), ("key_issues", "text"),
                           ("reasoning_short", "x" * 61), ("verdict", "buy")):
            with self.subTest(key=key):
                review = sample_review()
                review[key] = value
                with self.assertRaises(InvalidReview):
                    validate_review(json.dumps(review), "rate")

    def test_vision_request_does_not_store_response(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.jpg"
            path.write_bytes(b"synthetic-image")
            provider = Mock()
            provider.responses.create.return_value.output_text = "{}"
            image_to_json_review(path, "prompt", provider, "gpt-4o-mini")
            self.assertFalse(provider.responses.create.call_args.kwargs["store"])

    def test_capture_releases_failed_device(self):
        cap = Mock()
        cap.isOpened.return_value = False
        cv2 = Mock()
        cv2.VideoCapture.return_value = cap
        with patch.dict(sys.modules, {"cv2": cv2}), tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                capture_image(Path(directory))
            cap.release.assert_called_once()

    def test_capture_releases_device_on_read_exception(self):
        cap = Mock()
        cap.read.side_effect = RuntimeError("driver failed")
        cv2 = Mock()
        cv2.VideoCapture.return_value = cap
        with patch.dict(sys.modules, {"cv2": cv2}), tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                capture_image(Path(directory))
            cap.release.assert_called_once()

    def test_capture_releases_device_on_write_failure(self):
        cap = Mock()
        cap.read.return_value = (True, object())
        cv2 = Mock()
        cv2.VideoCapture.return_value = cap
        cv2.imwrite.return_value = False
        with patch.dict(sys.modules, {"cv2": cv2}), tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                capture_image(Path(directory))
            cap.release.assert_called_once()


    def test_duplicate_json_fields_rejected(self):
        text = json.dumps(sample_review())
        text = text.replace('"overall_score": 75', '"overall_score": 50, "overall_score": 75')
        with self.assertRaises(InvalidReview):
            validate_review(text, "rate")

    def test_unknown_mode_rejected(self):
        with self.assertRaises(InvalidReview):
            validate_review(json.dumps(sample_review()), "unknown")

    def test_zero_warmup_rejected_before_allocating_camera(self):
        cv2 = Mock()
        with patch.dict(sys.modules, {"cv2": cv2}):
            with self.assertRaises(ValueError):
                capture_image(Path("unused"), warmup_frames=0)
            cv2.VideoCapture.assert_not_called()
