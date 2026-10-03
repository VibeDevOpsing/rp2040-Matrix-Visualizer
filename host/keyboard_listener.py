#!/usr/bin/env python3
"""
================================================================================
RP2040 Matrix Visualizer — Host Keyboard Listener
================================================================================

A lightweight, cross-platform Python host client that monitors keyboard typing
activity across the entire operating system and streams real-time trigger pulses
to the connected RP2040 board over USB Serial.

Supported Host Operating Systems:
  - macOS (Intel & Apple Silicon)
  - Linux (Ubuntu, Debian, Arch, Fedora, Raspberry Pi OS, etc.)
  - Microsoft Windows 10 / 11

Requirements:
  pip install pyserial
  pip install pynput  # Required for global, background keystroke capture

Usage Examples:
  python host/keyboard_listener.py                   # Auto-discover RP2040 port and listen
  python host/keyboard_listener.py --demo            # Automated demo pulse mode (no typing needed)
  python host/keyboard_listener.py --demo --rate 3.0 # Demo mode at 3.0 pulses/sec
  python host/keyboard_listener.py --port /dev/cu.usbmodem1101  # Specify serial device manually
  python host/keyboard_listener.py --test            # Send a single verification pulse and exit
================================================================================
"""

import sys
import time
import argparse
import glob
from typing import Optional

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None


def find_rp2040_port() -> Optional[str]:
    """
    Automatically detect the serial port of a connected RP2040 board.

    Scans serial device descriptions for RP2040/MicroPython/CircuitPython keywords,
    falling back to standard OS-specific serial device patterns.
    """
    if serial is None:
        # Fallback filesystem globbing if pyserial list_ports is unavailable
        candidates = []
        if sys.platform == "darwin":
            candidates = glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/tty.usbmodem*")
        elif sys.platform.startswith("linux"):
            candidates = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
        return candidates[0] if candidates else None

    ports = list(serial.tools.list_ports.comports())

    # Strategy 1: Check hardware description and manufacturer strings
    keywords = ("rp2040", "pico", "waveshare", "circuitpython", "micropython")
    for p in ports:
        desc = f"{p.description} {p.manufacturer or ''} {p.hwid}".lower()
        if any(keyword in desc for keyword in keywords):
            return p.device

    # Strategy 2: OS-specific USB-serial naming conventions
    for p in ports:
        dev = p.device
        if sys.platform == "darwin" and "usbmodem" in dev:
            return dev
        if sys.platform.startswith("linux") and ("ttyACM" in dev or "ttyUSB" in dev):
            return dev
        if sys.platform == "win32" and dev.startswith("COM"):
            return dev

    return None


def run_demo_mode(ser: "serial.Serial", rate: float):
    """
    Emit periodic trigger pulses at a fixed frequency for demonstrations and testing.

    Parameters:
        ser: Active serial.Serial connection object.
        rate: Frequency in Hertz (pulses per second).
    """
    interval = 1.0 / rate if rate > 0 else 1.0
    print(f"[*] Demo mode active: sending pulses every {interval:.2f}s (Press Ctrl+C to stop)...")
    try:
        while True:
            ser.write(b"K\n")
            ser.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[*] Demo stopped.")


def run_terminal_mode(ser: "serial.Serial"):
    """
    Interactive fallback mode when 'pynput' is not installed.
    Accepts keyboard input directly from the terminal prompt.
    """
    print("[*] Running in interactive terminal mode.")
    print("[*] Press Enter or type characters to trigger ripples (Press Ctrl+C to quit)...")
    try:
        while True:
            line = input("> ")
            ser.write(b"K\n")
            ser.flush()
    except (KeyboardInterrupt, EOFError):
        print("\n[*] Exiting.")


def run_pynput_mode(ser: "serial.Serial"):
    """
    Global keyboard listener using 'pynput'.
    Intercepts keypress events system-wide, regardless of which window is in focus.
    """
    from pynput import keyboard

    print("[*] Global keyboard listener active! Type anywhere to trigger matrix ripples.")
    print("[*] Press Ctrl+C in this terminal to exit.\n")

    def on_press(key):
        try:
            # Send single character trigger with newline
            ser.write(b"K\n")
            ser.flush()
        except Exception as e:
            print(f"[!] Serial communication error: {e}", file=sys.stderr)

    with keyboard.Listener(on_press=on_press) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            print("\n[*] Stopping listener.")


def main():
    parser = argparse.ArgumentParser(
        description="RP2040 Matrix Reactive Visualizer — Host Serial Bridge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  python host/keyboard_listener.py --demo --rate 2.0"
    )
    parser.add_argument("-p", "--port", type=str, default=None,
                        help="Serial port identifier (e.g. /dev/cu.usbmodem1101 or COM3)")
    parser.add_argument("-b", "--baud", type=int, default=115200,
                        help="Baud rate (default: 115200; note: USB CDC operates at full bus speed)")
    parser.add_argument("-d", "--demo", action="store_true",
                        help="Run automated pulse demo mode without requiring manual typing")
    parser.add_argument("-r", "--rate", type=float, default=2.0,
                        help="Pulse frequency in Hz for demo mode (default: 2.0)")
    parser.add_argument("-t", "--test", action="store_true",
                        help="Send a single test pulse and exit immediately")
    args = parser.parse_args()

    # Verify prerequisite pyserial package
    if serial is None:
        print("[!] Error: 'pyserial' package is required but not installed.", file=sys.stderr)
        print("    Install it via: pip install pyserial", file=sys.stderr)
        sys.exit(1)

    # Resolve target serial port
    port = args.port or find_rp2040_port()
    if not port:
        print("[!] Could not auto-detect RP2040 serial port.", file=sys.stderr)
        print("    Please connect your board or specify the port with: --port <port>", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Connecting to RP2040 on {port} at {args.baud} baud...")
    try:
        ser = serial.Serial(port, args.baud, timeout=1)
    except Exception as e:
        print(f"[!] Failed to open serial port {port}: {e}", file=sys.stderr)
        sys.exit(1)

    print("[+] Connected successfully!")

    # Mode 1: Single test pulse
    if args.test:
        print("[*] Sending single test pulse...")
        ser.write(b"K\n")
        ser.flush()
        print("[+] Test pulse sent!")
        ser.close()
        return

    # Mode 2: Automated demo pulse loop
    if args.demo:
        run_demo_mode(ser, args.rate)
        ser.close()
        return

    # Mode 3: Global keyboard capture
    try:
        import pynput
        run_pynput_mode(ser)
    except ImportError:
        print("\n[i] Notice: 'pynput' is not installed.")
        print("    For system-wide background typing capture across all windows, run:")
        print("    pip install pynput\n")
        run_terminal_mode(ser)

    ser.close()


if __name__ == "__main__":
    main()
