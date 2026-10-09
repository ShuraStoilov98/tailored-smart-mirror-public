"""Serialize one mirror's analysis and own temporary media/device lifetimes."""
from contextlib import contextmanager
from dataclasses import dataclass
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from .devices import Hardware
from .devices.camera import capture_image
from .errors import MirrorBusy, MirrorUnavailable
from .images import decode_and_save_image_from_request
from .review import review_json_to_spoken_text


@dataclass(frozen=True)
class AnalysisResult:
    mode: str
    review: dict
    spoken_text: str


class MirrorController:
    def __init__(self, settings, provider, *, hardware=None, logger=None):
        self.settings = settings
        self.provider = provider
        self.hardware = hardware
        self.logger = logger or logging.getLogger(__name__)
        self.audio_path = settings.data_dir / "result.mp3"
        self._lock = Lock()
        self._closed = False

    @contextmanager
    def _operation(self):
        if not self._lock.acquire(blocking=False):
            raise MirrorBusy("Mirror is busy")
        try:
            if self._closed:
                raise MirrorUnavailable("Mirror has been shut down")
            yield
        finally:
            self._lock.release()

    def analyze(self, mode: str, body: dict) -> AnalysisResult:
        with self._operation():
            self.settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.settings.data_dir.chmod(0o700)
            started, succeeded = False, False
            try:
                # Each request owns its input and partial speech. Invalid uploads
                # cannot erase or interrupt the previous successful result.
                with TemporaryDirectory(prefix=".capture-", dir=self.settings.data_dir) as directory:
                    working_dir = Path(directory)
                    image_path = working_dir / "camera_capture.jpg"
                    uploaded = decode_and_save_image_from_request(body, image_path)
                    self.provider.prepare()
                    if self.hardware is None:
                        self.hardware = Hardware(self.settings.led_pin)
                    started = True
                    self.hardware.audio.stop()
                    self.hardware.led.flash_fast(times=5)
                    if not uploaded:
                        image_path = capture_image(working_dir, camera_index=self.settings.camera_index)
                    self.hardware.led.start_background_blink(interval=0.3)
                    review = self.provider.review(image_path, mode)
                    spoken = review_json_to_spoken_text(review, mode)
                    audio_path = working_dir / "result.mp3"
                    self.provider.speak(spoken, audio_path)
                    audio_path.chmod(0o600)
                    # pygame opens the file synchronously; on Linux its stream
                    # survives rename. Failed playback cannot replace prior audio.
                    self.hardware.audio.play(audio_path)
                    # Same-filesystem rename publishes the complete MP3 atomically.
                    audio_path.replace(self.audio_path)
                    succeeded = True
                    return AnalysisResult(mode, review, spoken)
            finally:
                cleanups = []
                if started:
                    if not succeeded:
                        cleanups.append(self.hardware.audio.stop)
                    cleanups.append(self.hardware.led.always_on)
                for cleanup in cleanups:
                    try:
                        cleanup()
                    except Exception:
                        self.logger.error("Mirror cleanup failed; check local device state")

    def read_audio(self) -> bytes:
        # Return a snapshot so later replacements/shutdown cannot alter a response.
        with self._operation():
            return self.audio_path.read_bytes()

    def close(self):
        # Wait for in-flight work; shutdown must not race capture/playback.
        with self._lock:
            if self._closed:
                return
            self._closed = True
            cleanups = [self.provider.close, lambda: self.audio_path.unlink(missing_ok=True)]
            if self.hardware is not None:
                cleanups.insert(0, self.hardware.close)
            failed = False
            for cleanup in cleanups:
                try:
                    cleanup()
                except Exception:
                    failed = True
                    self.logger.error("Mirror shutdown cleanup failed; check local device state")
            if failed:
                raise RuntimeError("Mirror shutdown cleanup failed") from None
