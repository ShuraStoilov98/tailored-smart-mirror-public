# file: led_helper.py
from gpiozero import LED
from time import sleep
from threading import Thread

class StatusLED:
    def __init__(self, pin: int):
        self.led = LED(pin)
        self._stop_thread = False
        self._thread = None

    def _flash(self, interval: float, times: int = 1):
        for _ in range(times):
            self.led.on()
            sleep(interval)
            self.led.off()
            sleep(interval)

    def always_on(self):
        self.stop()
        self.led.on()

    def flash_fast(self, times: int = 5):
        self.stop()
        self._flash(0.05, times)

    def flash_medium(self, times: int = 5):
        self.stop()
        self._flash(0.25, times)

    def start_background_blink(self, interval: float = 0.5):
        self.stop()
        self._stop_thread = False

        def run():
            while not self._stop_thread:
                self.led.on()
                sleep(interval)
                self.led.off()
                sleep(interval)

        self._thread = Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_thread = True
        if self._thread:
            self._thread.join()
        if self.led:
            self.led.off()
        self._thread = None
