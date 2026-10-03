"""
RP2040 Matrix — Universal Keyboard Reactive Visualizer
======================================================
Compatible with:
- MicroPython (any version v1.14 - v1.24+ on any RP2040 board)
- CircuitPython (7.x, 8.x, 9.x+)
- CPython 3 (Headless / Emulation mode for testing)

Default Hardware Target:
- Waveshare RP2040-Matrix (onboard 5x5 WS2812 RGB LED matrix on GP16)
- Also works on Raspberry Pi Pico / Pico W, RP2040-Zero, or any RP2040 board
  with WS2812/NeoPixel LEDs connected to any GPIO.
"""

import sys
import time
import math
import random

# ==============================================================================
# Configuration
# ==============================================================================
LED_PIN      = 16       # GPIO pin connected to the NeoPixel matrix data line
ROWS         = 5        # Number of matrix rows (height)
COLS         = 5        # Number of matrix columns (width)
NUM_LEDS     = ROWS * COLS
SERPENTINE   = True     # True: zigzag wiring (Waveshare RP2040-Matrix default)
                        # False: progressive / linear row-by-row layout
BRIGHTNESS   = 0.05     # 0.01 - 1.0 (0.05 = 5% brightness; safe for USB current & pleasant on eyes)
SPEED_PLASMA = 3.5      # Plasma wave propagation speed
RING_STEP    = 0.035    # Delay (seconds) per concentric ring expansion
RING_FADE    = 0.25     # Ring fade decay factor per expansion step
TRIGGER_KEYS = ('K', 'k', ' ', '\n', '\r') # Serial characters triggering ripple


# ==============================================================================
# Universal High-Resolution Clock
# ==============================================================================
# Handles 30-bit MicroPython ticks_ms rollover without time dilation
if hasattr(time, "ticks_ms") and hasattr(time, "ticks_diff"):
    _last_tick = time.ticks_ms()
    _accum_seconds = 0.0

    def get_seconds():
        global _last_tick, _accum_seconds
        now = time.ticks_ms()
        dt = time.ticks_diff(now, _last_tick)
        _last_tick = now
        _accum_seconds += dt / 1000.0
        return _accum_seconds
elif hasattr(time, "monotonic"):
    _t0 = time.monotonic()
    def get_seconds():
        return time.monotonic() - _t0
else:
    _t0 = time.time()
    def get_seconds():
        return time.time() - _t0


# ==============================================================================
# Universal NeoPixel / WS2812 Hardware Abstraction
# ==============================================================================
class UniversalMatrix:
    """
    Unified driver supporting:
    1. MicroPython (built-in neopixel module with software brightness scaling)
    2. CircuitPython (board.GPxx + neopixel module)
    3. MicroPython PIO (rp2 hardware state machine fallback if neopixel missing)
    4. Headless dummy driver (for desktop testing / linting)
    """
    def __init__(self, pin_num=LED_PIN, num_leds=NUM_LEDS, brightness=BRIGHTNESS):
        self.num_leds = num_leds
        self.brightness = max(0.001, min(1.0, brightness))
        self.driver_name = "None"
        self._pixels = [(0, 0, 0)] * num_leds

        # 1. Try MicroPython standard built-in neopixel
        try:
            import machine
            import neopixel
            self._pin = machine.Pin(pin_num, machine.Pin.OUT)
            self._np = neopixel.NeoPixel(self._pin, num_leds)
            self.driver_name = "MicroPython (neopixel)"
            return
        except (ImportError, AttributeError):
            pass

        # 2. Try CircuitPython neopixel
        try:
            import board
            import neopixel
            pin_obj = getattr(board, f"GP{pin_num}", None) or getattr(board, f"IO{pin_num}", None)
            if pin_obj is None:
                pin_obj = board.GP16
            self._cp_np = neopixel.NeoPixel(
                pin_obj, num_leds, brightness=self.brightness, auto_write=False
            )
            self.driver_name = "CircuitPython (neopixel)"
            return
        except (ImportError, AttributeError):
            pass

        # 3. Try MicroPython hardware PIO fallback (RP2040 native state machine)
        try:
            import rp2
            from machine import Pin
            import array

            @rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW, out_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=True, pull_thresh=24)
            def ws2812_pio():
                wrap_target()
                label("bitloop")
                out(x, 1)               .side(0) [2]
                jmp(not_x, "do_zero")   .side(1) [1]
                jmp("bitloop")          .side(1) [4]
                label("do_zero")
                nop()                   .side(0) [4]
                wrap()

            self._sm = rp2.StateMachine(0, ws2812_pio, freq=8_000_000, sideset_base=Pin(pin_num))
            self._sm.active(1)
            self._pio_buffer = array.array("I", [0] * num_leds)
            self.driver_name = "MicroPython (RP2040 PIO)"
            return
        except Exception:
            pass

        # 4. Fallback for desktop CPython / development
        self.driver_name = "Headless Emulation (no hardware detected)"

    def set_pixel(self, idx, rgb_tuple):
        """Buffer a pixel color (r, g, b) at logical index idx [0..num_leds-1]."""
        if 0 <= idx < self.num_leds:
            self._pixels[idx] = rgb_tuple

    def show(self):
        """Flush the buffered pixels to physical LEDs with brightness scaling."""
        b = self.brightness
        if self.driver_name == "MicroPython (neopixel)":
            np = self._np
            for i in range(self.num_leds):
                r, g, bl = self._pixels[i]
                np[i] = (int(r * b), int(g * b), int(bl * b))
            np.write()
        elif self.driver_name == "CircuitPython (neopixel)":
            cp = self._cp_np
            for i in range(self.num_leds):
                cp[i] = self._pixels[i]
            cp.show()
        elif self.driver_name == "MicroPython (RP2040 PIO)":
            buf = self._pio_buffer
            for i in range(self.num_leds):
                r, g, bl = self._pixels[i]
                # WS2812 GRB 24-bit encoding
                buf[i] = (int(g * b) << 16) | (int(r * b) << 8) | int(bl * b)
            self._sm.put(buf, 8)


# ==============================================================================
# Matrix Geometry & Spatial Precomputations
# ==============================================================================
def get_pixel_index(col, row, cols=COLS, serpentine=SERPENTINE):
    """
    Maps Cartesian coordinates (col, row) to linear NeoPixel index.
    Accounts for serpentine (zigzag) PCB traces.
    """
    if serpentine and (row % 2 == 1):
        return row * cols + (cols - 1 - col)
    return row * cols + col

# Matrix center coordinates
CENTER_R = (ROWS - 1) / 2.0
CENTER_C = (COLS - 1) / 2.0

# Precompute radial distance from center for each LED index
_DIST = [0.0] * NUM_LEDS
for r in range(ROWS):
    for c in range(COLS):
        idx = get_pixel_index(c, r, COLS, SERPENTINE)
        _DIST[idx] = math.sqrt((c - CENTER_C) ** 2 + (r - CENTER_R) ** 2)

# Precompute concentric Chebyshev distance rings for ripple propagation
MAX_RINGS = int(math.ceil(max(CENTER_R, CENTER_C))) + 2
RIPPLE_RINGS = []
for d in range(MAX_RINGS):
    ring = []
    for r in range(ROWS):
        for c in range(COLS):
            chebyshev_dist = max(abs(r - CENTER_R), abs(c - CENTER_C))
            if int(round(chebyshev_dist)) == d:
                ring.append(get_pixel_index(c, r, COLS, SERPENTINE))
    RIPPLE_RINGS.append(ring)


# ==============================================================================
# Colour Space Math
# ==============================================================================
def hsv_to_rgb(h, s, v):
    """
    Converts HSV to RGB (0-255).
    h in [0, 360), s in [0.0, 1.0], v in [0.0, 1.0].
    """
    h = h % 360
    c = v * s
    x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
    m = v - c
    if h < 60:
        r, g, b = c, x, 0.0
    elif h < 120:
        r, g, b = x, c, 0.0
    elif h < 180:
        r, g, b = 0.0, c, x
    elif h < 240:
        r, g, b = 0.0, x, c
    elif h < 300:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x
    return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))


# ==============================================================================
# Non-blocking Serial Keystroke Listener
# ==============================================================================
_poll_obj = None
_cdc_serial = None

# MicroPython stdin polling setup
try:
    import select
    _poll_obj = select.poll()
    _poll_obj.register(sys.stdin, select.POLLIN)
except Exception:
    _poll_obj = None

# CircuitPython usb_cdc setup
try:
    import usb_cdc
    _cdc_serial = usb_cdc.data if usb_cdc.data else usb_cdc.console
except Exception:
    _cdc_serial = None


# Active ripples state: list of (start_timestamp, hue)
ripples = []

def trigger_ripple():
    """Triggers an expanding ripple originating from the matrix center."""
    ripples.append((get_seconds(), random.uniform(0.0, 360.0)))


def check_serial_input():
    """
    Non-blocking poll for incoming keystroke commands over USB Serial (CDC/stdin).
    Triggers a reactive ripple when any trigger character is detected.
    """
    # 1. MicroPython stdin poll
    if _poll_obj is not None:
        try:
            while _poll_obj.poll(0):
                ch = sys.stdin.read(1)
                if not ch:
                    break
                if ch in TRIGGER_KEYS or ch.isalnum():
                    trigger_ripple()
                    break
        except Exception:
            pass

    # 2. CircuitPython CDC poll
    if _cdc_serial is not None:
        try:
            n = _cdc_serial.in_waiting
            if n:
                data = _cdc_serial.read(n)
                for byte in data:
                    char = chr(byte)
                    if char in TRIGGER_KEYS or char.isalnum():
                        trigger_ripple()
                        break
        except Exception:
            pass


# ==============================================================================
# Visualizer Engine & Main Loop
# ==============================================================================
def run():
    global ripples
    matrix = UniversalMatrix(LED_PIN, NUM_LEDS, BRIGHTNESS)
    print("RP2040 Matrix Visualizer running.")
    print(f"Driver: {matrix.driver_name} | Pin: GP{LED_PIN} | Size: {COLS}x{ROWS} (Serpentine={SERPENTINE})")

    plasma_buffer = [(0, 0, 0)] * NUM_LEDS

    while True:
        t = get_seconds()

        # Check for keyboard events over serial
        check_serial_input()

        # Compute wave offsets
        sr = [math.sin(r * 1.3 + t * SPEED_PLASMA) for r in range(ROWS)]
        sc = [math.sin(c * 1.3 + t * SPEED_PLASMA) for c in range(COLS)]

        # Render background plasma
        for r in range(ROWS):
            for c in range(COLS):
                idx = get_pixel_index(c, r, COLS, SERPENTINE)
                vd = math.sin(_DIST[idx] * 1.8 - t * SPEED_PLASMA)
                v = (sr[r] + sc[c] + vd) / 3.0
                hue = (v * 120.0 + t * 40.0) % 360.0
                val = max(0.2, 0.6 + v * 0.4)
                color = hsv_to_rgb(hue, 0.9, val)
                plasma_buffer[idx] = color
                matrix.set_pixel(idx, color)

        # Alpha-blend reactive ripples on top of the plasma
        if ripples:
            now = get_seconds()
            alive = []
            for r_entry in ripples:
                t0, hue = r_entry
                ring_idx = int((now - t0) / RING_STEP)
                if ring_idx < len(RIPPLE_RINGS):
                    alive.append(r_entry)
                    alpha = max(0.0, 1.0 - ring_idx * RING_FADE)
                    if alpha > 0.0:
                        ia = 1.0 - alpha
                        rr, rg, rb = hsv_to_rgb(hue, 0.9, 1.0)
                        for p_idx in RIPPLE_RINGS[ring_idx]:
                            pr, pg, pb = plasma_buffer[p_idx]
                            blended = (
                                int(pr * ia + rr * alpha),
                                int(pg * ia + rg * alpha),
                                int(pb * ia + rb * alpha)
                            )
                            matrix.set_pixel(p_idx, blended)
            ripples = alive

        matrix.show()


if __name__ == "__main__":
    run()
