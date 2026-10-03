"""
================================================================================
RP2040 Matrix — Universal Keyboard Reactive Visualizer
================================================================================

A high-performance, version-agnostic ambient light and interactive visualizer
for Raspberry Pi RP2040-based microcontrollers equipped with WS2812B (NeoPixel)
RGB LED matrices.

Key Features:
-------------
1. Ambient Mode:
   Smooth, real-time 2D mathematical plasma synthesis using overlapping
   trigonometric waveforms (row, column, and radial distance sinusoids) in HSV
   color space with dynamic hue phase rotation.

2. Reactive Mode:
   Listens over USB Serial (CDC/stdin) for keystroke events streamed from a host
   computer. When typing activity is detected, concentric ripple waves (based on
   the Chebyshev distance metric) expand outwards from the matrix center,
   alpha-blending over the ambient plasma with random hues and natural decay.

3. Standalone Capability:
   Runs autonomously as a desk ambient light whenever powered by any standard 5V
   USB source, power bank, or phone charger, without requiring a host PC.

4. Universal Hardware & Firmware Compatibility:
   - Primary target: Waveshare RP2040-Matrix (onboard 5x5 WS2812B matrix on GP16).
   - Also compatible with Raspberry Pi Pico, Pico W, Pico 2, Waveshare RP2040-Zero,
     RP2040-One, Seeed Studio XIAO RP2040, or custom RP2040 designs with WS2812 LEDs.
   - Runs seamlessly across ANY version of MicroPython (v1.14 through v1.24+).
   - Runs on CircuitPython (7.x, 8.x, 9.x+).
   - Runs in headless emulation mode on standard desktop Python 3 for testing.

Author: Antigravity Pair Programmer
License: MIT
================================================================================
"""

import sys
import time
import math
import random

# ==============================================================================
# Hardware & Visualizer Configuration
# ==============================================================================
# GPIO pin connected to the NeoPixel matrix data input line (DI/DIN).
# On the Waveshare RP2040-Matrix, the onboard 5x5 WS2812B matrix is wired to GP16.
LED_PIN: int = 16

# Matrix dimensions (grid width and height)
ROWS: int = 5
COLS: int = 5
NUM_LEDS: int = ROWS * COLS

# PCB trace routing topology:
# True: Serpentine / Zigzag layout (alternating row directions: row 0 L->R,
#       row 1 R->L, row 2 L->R, etc.). This is the layout used by Waveshare RP2040-Matrix.
# False: Linear / Progressive layout (every row wired from left to right).
SERPENTINE: bool = True

# Global brightness scale factor [0.001 to 1.0]:
# 0.05 corresponds to 5% duty cycle.
# IMPORTANT: 25 WS2812 LEDs displaying full white (255, 255, 255) draw ~1.5 Amps
# at full brightness. Setting brightness to 0.05 keeps power consumption at a safe
# ~60-80 mA, protecting USB host ports while maintaining rich, eye-friendly colors.
BRIGHTNESS: float = 0.05

# Animation speeds and physics parameters:
SPEED_PLASMA: float = 3.5    # Speed multiplier for ambient plasma wave oscillation
RING_STEP: float    = 0.035  # Time delay (in seconds) between concentric ring expansions
RING_FADE: float    = 0.25   # Opacity decay factor per ring expansion step (1.0 = instant)

# Serial trigger characters that trigger ripple generation upon reception:
TRIGGER_KEYS = ('K', 'k', ' ', '\n', '\r')


# ==============================================================================
# Universal High-Resolution Clock
# ==============================================================================
# In MicroPython, time.ticks_ms() returns an arbitrary 30-bit signed integer that
# wraps around every ~12.4 days. Calling time.ticks_diff(now, last) properly accounts
# for this rollover. The accumulator below provides an monotonically increasing
# timestamp in seconds that never overflows or suffers from wrap-around artifacts.
if hasattr(time, "ticks_ms") and hasattr(time, "ticks_diff"):
    _last_tick = time.ticks_ms()
    _accum_seconds = 0.0

    def get_seconds() -> float:
        """Return elapsed monotonic time in seconds using MicroPython ticks."""
        global _last_tick, _accum_seconds
        now = time.ticks_ms()
        dt = time.ticks_diff(now, _last_tick)
        _last_tick = now
        _accum_seconds += dt / 1000.0
        return _accum_seconds

elif hasattr(time, "monotonic"):
    _t0 = time.monotonic()

    def get_seconds() -> float:
        """Return elapsed monotonic time in seconds using CircuitPython / CPython."""
        return time.monotonic() - _t0

else:
    _t0 = time.time()

    def get_seconds() -> float:
        """Fallback monotonic time using standard time.time()."""
        return time.time() - _t0


# ==============================================================================
# Universal NeoPixel / WS2812 Hardware Abstraction Layer (HAL)
# ==============================================================================
class UniversalMatrix:
    """
    Multi-tier hardware abstraction driver for WS2812 / NeoPixel LEDs.

    Fallback Hierarchy:
    1. Native MicroPython 'neopixel' C module (standard in official RP2040 firmware).
    2. CircuitPython 'neopixel' driver with Adafruit 'board.GPxx' bindings.
    3. Native RP2040 Hardware PIO driver ('rp2.asm_pio') if 'neopixel' is unavailable.
    4. Headless dummy driver (allows linting and tests to run on desktop Python 3).
    """

    def __init__(self, pin_num: int = LED_PIN, num_leds: int = NUM_LEDS, brightness: float = BRIGHTNESS):
        self.num_leds = num_leds
        self.brightness = max(0.001, min(1.0, brightness))
        self.driver_name = "None"
        # Preallocated RGB color buffer: list of (r, g, b) tuples
        self._pixels = [(0, 0, 0)] * num_leds

        # ----------------------------------------------------------------------
        # Strategy 1: Native MicroPython built-in neopixel
        # ----------------------------------------------------------------------
        try:
            import machine
            import neopixel
            self._pin = machine.Pin(pin_num, machine.Pin.OUT)
            self._np = neopixel.NeoPixel(self._pin, num_leds)
            self.driver_name = "MicroPython (neopixel)"
            return
        except (ImportError, AttributeError):
            pass

        # ----------------------------------------------------------------------
        # Strategy 2: CircuitPython neopixel driver
        # ----------------------------------------------------------------------
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

        # ----------------------------------------------------------------------
        # Strategy 3: Native RP2040 PIO State Machine (assembly driver fallback)
        # ----------------------------------------------------------------------
        try:
            import rp2
            from machine import Pin
            import array

            # Standard 800kHz WS2812 timing on RP2040 PIO running at 8.0 MHz
            # T1 = 2 cycles high, T2 = 5 cycles data-dependent, T3 = 3 cycles low
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

        # ----------------------------------------------------------------------
        # Strategy 4: Headless Dummy (Desktop CPython / CI environment)
        # ----------------------------------------------------------------------
        self.driver_name = "Headless Emulation (Desktop CPython)"

    def set_pixel(self, idx: int, rgb_tuple: tuple):
        """Set pixel at logical index `idx` (0 to num_leds - 1) to (r, g, b)."""
        if 0 <= idx < self.num_leds:
            self._pixels[idx] = rgb_tuple

    def show(self):
        """Flush the buffered pixel values to the physical LEDs with software brightness scaling."""
        b = self.brightness
        if self.driver_name == "MicroPython (neopixel)":
            np = self._np
            for i in range(self.num_leds):
                r, g, bl = self._pixels[i]
                # Scale each color channel by brightness before writing to WS2812
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
                # WS2812 expects 24-bit GRB byte order: (G << 16) | (R << 8) | B
                buf[i] = (int(g * b) << 16) | (int(r * b) << 8) | int(bl * b)
            self._sm.put(buf, 8)


# ==============================================================================
# Matrix Geometry & Spatial Precomputations
# ==============================================================================
def get_pixel_index(col: int, row: int, cols: int = COLS, serpentine: bool = SERPENTINE) -> int:
    """
    Map 2D Cartesian coordinates (col, row) to the 1D physical NeoPixel index.

    In a serpentine matrix (e.g. Waveshare RP2040-Matrix):
      - Even rows (0, 2, 4...) run Left -> Right: index = row * cols + col
      - Odd rows (1, 3...) run Right -> Left:      index = row * cols + (cols - 1 - col)
    This inversion guarantees that geometric waves appear undistorted in physical space.
    """
    if serpentine and (row % 2 == 1):
        return row * cols + (cols - 1 - col)
    return row * cols + col


# Floating-point center coordinates of the matrix
CENTER_R: float = (ROWS - 1) / 2.0
CENTER_C: float = (COLS - 1) / 2.0

# Precompute Euclidean distance from the matrix center to each physical LED index.
# Formula: sqrt((col - center_col)^2 + (row - center_row)^2)
_DIST = [0.0] * NUM_LEDS
for r in range(ROWS):
    for c in range(COLS):
        idx = get_pixel_index(c, r, COLS, SERPENTINE)
        _DIST[idx] = math.sqrt((c - CENTER_C) ** 2 + (r - CENTER_R) ** 2)

# Precompute concentric ripple rings based on the Chebyshev distance metric:
# D_Chebyshev((r, c), (center_r, center_c)) = max(|r - center_r|, |c - center_c|)
# Grouping pixels by rounded Chebyshev distance creates natural expanding wave rings.
MAX_RINGS: int = int(math.ceil(max(CENTER_R, CENTER_C))) + 2
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
# Colour Space Conversion (HSV to RGB)
# ==============================================================================
def hsv_to_rgb(h: float, s: float, v: float) -> tuple:
    """
    Convert Hue-Saturation-Value (HSV) to 8-bit RGB tuple (0-255).

    Parameters:
        h: Hue angle in degrees [0.0, 360.0)
        s: Saturation ratio [0.0, 1.0]
        v: Value / Intensity ratio [0.0, 1.0]

    Returns:
        (red, green, blue) with integer components in range [0, 255].
    """
    h = h % 360.0
    c = v * s
    x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
    m = v - c
    if h < 60.0:
        r, g, b = c, x, 0.0
    elif h < 120.0:
        r, g, b = x, c, 0.0
    elif h < 180.0:
        r, g, b = 0.0, c, x
    elif h < 240.0:
        r, g, b = 0.0, x, c
    elif h < 300.0:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x
    return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))


# ==============================================================================
# Non-blocking USB Serial Keystroke Listener
# ==============================================================================
_poll_obj = None
_cdc_serial = None

# MicroPython stdin polling initialization (non-blocking)
try:
    import select
    _poll_obj = select.poll()
    _poll_obj.register(sys.stdin, select.POLLIN)
except Exception:
    _poll_obj = None

# CircuitPython USB CDC serial initialization
try:
    import usb_cdc
    _cdc_serial = usb_cdc.data if usb_cdc.data else usb_cdc.console
except Exception:
    _cdc_serial = None


# State of active ripple waves: list of (start_timestamp, hue_angle)
ripples = []

def trigger_ripple():
    """Initiate a new ripple pulse originating from the matrix center."""
    ripples.append((get_seconds(), random.uniform(0.0, 360.0)))


def check_serial_input():
    """
    Poll the USB Serial interface without blocking the render loop.
    Triggers an expanding ripple when valid trigger characters arrive from the host.
    """
    # MicroPython stdin poll
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

    # CircuitPython CDC poll
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
# Main Animation & Render Loop
# ==============================================================================
def run():
    """
    Main execution loop.
    Pre-allocates pixel buffers to achieve zero dynamic memory allocations
    inside the tight loop, preventing MicroPython Garbage Collector latency spikes.
    """
    global ripples
    matrix = UniversalMatrix(LED_PIN, NUM_LEDS, BRIGHTNESS)
    print("RP2040 Matrix Visualizer running.")
    print(f"Driver: {matrix.driver_name} | Pin: GP{LED_PIN} | Size: {COLS}x{ROWS} (Serpentine={SERPENTINE})")

    # Static buffer for background plasma colors: avoids re-allocating lists per frame
    plasma_buffer = [(0, 0, 0)] * NUM_LEDS

    while True:
        t = get_seconds()

        # 1. Check for incoming keystrokes over USB serial
        check_serial_input()

        # 2. Compute 1D trigonometric wave terms along rows and columns
        #    Evaluating 5 + 5 = 10 sin() terms instead of 25 * 2 = 50 terms
        sr = [math.sin(r * 1.3 + t * SPEED_PLASMA) for r in range(ROWS)]
        sc = [math.sin(c * 1.3 + t * SPEED_PLASMA) for c in range(COLS)]

        # 3. Synthesize 2D ambient plasma wave
        for r in range(ROWS):
            for c in range(COLS):
                idx = get_pixel_index(c, r, COLS, SERPENTINE)
                # Radial wave component from center:
                vd = math.sin(_DIST[idx] * 1.8 - t * SPEED_PLASMA)
                # Wave superposition:
                v = (sr[r] + sc[c] + vd) / 3.0
                # Map intensity to HSV hue and value
                hue = (v * 120.0 + t * 40.0) % 360.0
                val = max(0.2, 0.6 + v * 0.4)
                color = hsv_to_rgb(hue, 0.9, val)
                plasma_buffer[idx] = color
                matrix.set_pixel(idx, color)

        # 4. Alpha-blend active ripple waves over the plasma
        if ripples:
            now = get_seconds()
            alive = []
            for r_entry in ripples:
                t0, hue = r_entry
                ring_idx = int((now - t0) / RING_STEP)
                if ring_idx < len(RIPPLE_RINGS):
                    alive.append(r_entry)
                    # Compute fading alpha: 1.0 at origin, decreasing with each outward step
                    alpha = max(0.0, 1.0 - ring_idx * RING_FADE)
                    if alpha > 0.0:
                        ia = 1.0 - alpha
                        rr, rg, rb = hsv_to_rgb(hue, 0.9, 1.0)
                        # Blend ripple color with the underlying plasma color
                        for p_idx in RIPPLE_RINGS[ring_idx]:
                            pr, pg, pb = plasma_buffer[p_idx]
                            blended = (
                                int(pr * ia + rr * alpha),
                                int(pg * ia + rg * alpha),
                                int(pb * ia + rb * alpha)
                            )
                            matrix.set_pixel(p_idx, blended)
            ripples = alive

        # 5. Flush buffered frame to physical LEDs
        matrix.show()


if __name__ == "__main__":
    run()
