"""Validate configuration before allocating devices or sending provider requests."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from smart_mirror import create_app
from smart_mirror.config import MirrorSettings, default_config


class ConfigTests(unittest.TestCase):
    def test_explicit_config_overrides_invalid_environment(self):
        with patch.dict("os.environ", {"MIRROR_CAMERA_INDEX": "invalid", "MIRROR_LED_PIN": "invalid"}):
            app = create_app({"CAMERA_INDEX": 2, "LED_PIN": 23})
            self.assertEqual(app.config["CAMERA_INDEX"], 2)
            app.extensions["mirror_close"]()

    def test_invalid_configuration_rejected_without_values_in_error(self):
        for name, value in (("CAMERA_INDEX", -1), ("CAMERA_INDEX", "synthetic-invalid"),
                            ("LED_PIN", 40), ("LED_PIN", True), ("ACCESS_TOKEN", ""),
                            ("VISION_MODEL", ""), ("MAX_CONTENT_LENGTH", 0),
                            ("DATA_DIR", ""), ("API_KEY", 5)):
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as error:
                    create_app({name: value})
                self.assertIn(name, str(error.exception))
                self.assertNotIn("synthetic-invalid", str(error.exception))

    def test_settings_repr_does_not_reveal_api_key(self):
        config = default_config()
        config["API_KEY"] = "synthetic-private-value"  # pragma: allowlist secret
        self.assertNotIn("synthetic-private-value", repr(MirrorSettings.from_config(config)))
