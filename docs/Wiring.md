# Wiring

The diagram shows the GPIO23 LED circuit, USB camera, Pi power and audio connections used by the application. Pin defaults are defined in `src/smart_mirror/config.py`; device code lives in `src/smart_mirror/devices/`. The LED circuit and suggested 330 Ω resistor must be checked against the physical build before applying power.

![Proposed Raspberry Pi 4 wiring: USB camera, USB-C power, GPIO23 physical pin 16 through a suggested 330 ohm resistor to the LED anode, LED cathode to ground at pin 6, and an OS-selected speaker.](assets/smart-mirror-wiring.png)

[Full-resolution diagram](assets/smart-mirror-wiring.png) · [Editable SVG](assets/smart-mirror-wiring.svg)

The colors distinguish USB camera, Pi power, LED signal, ground return and the software-selected audio route. The dashed speaker connection represents OS routing; it does not prescribe a speaker cable or GPIO connection. The board is an illustration, not a header-orientation guide. These pin labels assume the default `MIRROR_LED_PIN=23`; update the diagram and physical connection together if you change it. The table below repeats the connections as text.

| Connection | Code evidence | Verification |
| --- | --- | --- |
| LED BCM23 → pin 16 | `src/smart_mirror/config.py` default and `tests/scripts/led_test.py` | Pin mapping documented; actual connection unverified |
| LED series resistor → LED → ground | Standard current-limited indicator circuit | Suggested 330 Ω; original part/value unverified |
| USB camera → USB port | OpenCV `VideoCapture(index, CAP_V4L2)` | UVC device/model/index need testing |
| Pi → speaker | pygame mixer; historical Bluetooth test | OS must select/route audio; actual speaker unverified |

GPIO signals are 3.3 V. Use a series resistor and a small indicator LED, never connect the LED directly between an output and ground or attach 5 V to a GPIO input. Power off before changing connections. `gpiozero` uses BCM numbering, not physical header numbers. On the Pi, run `pinout` (from the OS gpiozero package) to confirm header orientation and numbering. Official [Raspberry Pi hardware documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html) describes the header and GPIO constraints.

The STL/3MF files describe the enclosure plates. Select print material and tolerances to suit the assembly, and allow for mounting and cooling. The application uses a USB camera; touchscreen, microphone and CSI camera integration are not implemented.
