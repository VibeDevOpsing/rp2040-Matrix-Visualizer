"""
RP2040 Boot Configuration
Safe across both MicroPython and CircuitPython runtimes.
"""
try:
    import usb_cdc
    import usb_hid

    usb_hid.disable()
    usb_cdc.enable(console=True, data=True)
except (ImportError, AttributeError):
    # Running on MicroPython — USB CDC and endpoints are handled directly by the C firmware
    pass
