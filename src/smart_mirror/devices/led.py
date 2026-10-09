"""BCM-numbered capture/processing indicator using gpiozero's blink worker."""
from time import sleep
from gpiozero import LED


class StatusLED:
    def __init__(self, pin: int):
        self.led = LED(pin)

    def always_on(self):
        self.led.on()

    def flash_fast(self, times: int = 5):
        self.stop()
        for _ in range(times):
            self.led.on()
            sleep(0.05)
            self.led.off()
            sleep(0.05)

    def start_background_blink(self, interval: float = 0.5):
        self.led.blink(on_time=interval, off_time=interval, background=True)

    def stop(self):
        self.led.off()

    def close(self):
        self.led.close()
