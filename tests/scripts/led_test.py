"""Blink BCM23; confirm resistor and physical wiring before running."""
from gpiozero import LED
from signal import pause

if __name__ == "__main__":
    with LED(23) as led:
        led.blink(on_time=0.5, off_time=0.5)
        try:
            pause()
        except KeyboardInterrupt:
            pass
