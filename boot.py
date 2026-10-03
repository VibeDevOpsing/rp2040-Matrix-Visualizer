"""
================================================================================
RP2040 Boot Configuration (boot.py)
================================================================================

This file executes once during microcontroller hardware initialization, prior
to main script execution.

Behavior across runtimes:
-------------------------
1. CircuitPython:
   - Configures USB endpoints before the USB stack enumerates with the host PC.
   - Disables USB Human Interface Device (HID) endpoints to free endpoint RAM.
   - Enables dual USB CDC serial channels (Console REPL and Data CDC channel)
     so the host can stream keystroke events without interfering with the REPL.

2. MicroPython:
   - MicroPython manages USB descriptors and endpoints directly in compiled C.
   - The `usb_cdc` and `usb_hid` modules do not exist in MicroPython; the try-except
     block safely intercepts the ImportError and passes without error.
================================================================================
"""

try:
    import usb_cdc
    import usb_hid

    # Disable HID to free USB endpoints
    usb_hid.disable()
    # Enable both REPL console and secondary raw data serial channel
    usb_cdc.enable(console=True, data=True)
except (ImportError, AttributeError):
    # MicroPython environment: USB endpoints are pre-configured at compile time
    pass
