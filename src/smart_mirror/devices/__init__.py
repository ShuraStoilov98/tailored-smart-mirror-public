"""Own the lifetime of the status LED and speaker."""


class Hardware:
    """Allocate devices only when an authenticated capture request needs them."""
    def __init__(self, pin):
        from .led import StatusLED
        from .audio import AudioPlayer

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


