"""
================================================================================
RP2040 Matrix — CircuitPython Entrypoint
================================================================================

This file serves as the automatic startup script for Adafruit CircuitPython.
CircuitPython firmware searches for `code.py` on the root of the CIRCUITPY
drive and executes it automatically upon power-up or soft reset.

To maintain a single source of truth across both MicroPython and CircuitPython,
this file imports and executes the universal engine implemented in `main.py`.

Compatibility:
  - CircuitPython 7.x, 8.x, 9.x+
  - Waveshare RP2040-Matrix, RP2040-Zero, Raspberry Pi Pico / Pico W, etc.
================================================================================
"""

import main

if __name__ == "__main__":
    # Launch the universal visualizer loop
    main.run()
