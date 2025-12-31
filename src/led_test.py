from gpiozero import LED
from time import sleep

led = LED(23)

try:
    while True:
        led.on()
        sleep(0.5)
        led.off()
        sleep(0.5)
except KeyboardInterrupt:
    print("Stopping LED test")
finally:
    led.off()
