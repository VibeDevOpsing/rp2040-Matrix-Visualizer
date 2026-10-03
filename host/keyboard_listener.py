#!/usr/bin/env python3
"""
RP2040 Matrix Visualizer — Host Keyboard Listener
=================================================
Runs on the host computer (macOS, Linux, Windows).
Monitors keyboard typing activity and streams trigger pulses
to the RP2040 board via USB Serial.

Requirements:
    pip install pyserial
    pip install pynput  (optional, required for system-wide background listening)

Usage:
    python host/keyboard_listener.py                 # Auto-detect port and listen
    python host/keyboard_listener.py --demo          # Automated demo ripple pulses
    python host/keyboard_listener.py --port /dev/... # Specify serial port manually
"""

import sys
import time
import argparse
import glob

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None


def find_rp2040_port():
    """Attempt auto-discovery of the RP2040 USB serial port."""
    if serial is None:
        # Fallback to filesystem globbing
        candidates = []
        if sys.platform == "darwin":
            candidates = glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/tty.usbmodem*")
        elif sys.platform.startswith("linux"):
            candidates = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
        return candidates[0] if candidates else None

    # Use pyserial's list_ports
    ports = list(serial.tools.list_ports.comports())
    # 1. Search for known RP2040 identifiers in port description / VID:PID
    for p in ports:
        desc = f"{p.description} {p.manufacturer or ''} {p.hwid}".lower()
        if any(keyword in desc for keyword in ("rp2040", "pico", "waveshare", "circuitpython", "micropython")):
            return p.device

    # 2. Heuristic fallback based on OS default serial device names
    for p in ports:
        dev = p.device
        if sys.platform == "darwin" and "usbmodem" in dev:
            return dev
        if sys.platform.startswith("linux") and ("ttyACM" in dev or "ttyUSB" in dev):
            return dev
        if sys.platform == "win32" and dev.startswith("COM"):
            return dev

    return None


def run_demo_mode(ser, rate):
    """Periodically emits trigger pulses for demonstration."""
    interval = 1.0 / rate if rate > 0 else 1.0
    print(f"[*] Demo mode active: sending pulses every {interval:.2f}s (Ctrl+C to stop)...")
    try:
        while True:
            ser.write(b"K\n")
            ser.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[*] Demo stopped.")


def run_terminal_mode(ser):
    """Fallback interactive mode when pynput is not installed."""
    print("[*] Running in interactive terminal mode.")
    print("[*] Press Enter or type characters to trigger ripples (Ctrl+C to quit)...")
    try:
        while True:
            line = input("> ")
            ser.write(b"K\n")
            ser.flush()
    except (KeyboardInterrupt, EOFError):
        print("\n[*] Exiting.")


def run_pynput_mode(ser):
    """Global system-wide keyboard listener using pynput."""
    from pynput import keyboard

    print("[*] Global keyboard listener active! Type anywhere to trigger matrix ripples.")
    print("[*] Press Ctrl+C in this terminal to exit.\n")

    def on_press(key):
        try:
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
    parser = argparse.ArgumentParser(description="RP2040 Matrix Reactive Visualizer Host Bridge")
    parser.add_argument("-p", "--port", type=str, default=None, help="Serial port (e.g. /dev/cu.usbmodem1101 or COM3)")
    parser.add_argument("-b", "--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("-d", "--demo", action="store_true", help="Run automated pulse demo mode")
    parser.add_argument("-r", "--rate", type=float, default=2.0, help="Demo pulse rate in Hz (default: 2.0)")
    parser.add_argument("-t", "--test", action="store_true", help="Send a single test pulse and exit")
    args = parser.parse_args()

    if serial is None:
        print("[!] Error: 'pyserial' package is not installed.", file=sys.stderr)
        print("    Please run: pip install pyserial", file=sys.stderr)
        sys.exit(1)

    port = args.port or find_rp2040_port()
    if not port:
        print("[!] Could not auto-detect RP2040 serial port.", file=sys.stderr)
        print("    Please connect your board or specify the port manually with: --port <port>", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Connecting to RP2040 on {port} at {args.baud} baud...")
    try:
        ser = serial.Serial(port, args.baud, timeout=1)
    except Exception as e:
        print(f"[!] Failed to open serial port {port}: {e}", file=sys.stderr)
        sys.exit(1)

    print("[+] Connected successfully!")

    if args.test:
        print("[*] Sending single test pulse...")
        ser.write(b"K\n")
        ser.flush()
        print("[+] Test pulse sent!")
        ser.close()
        return

    if args.demo:
        run_demo_mode(ser, args.rate)
        ser.close()
        return

    # Try importing pynput for system-wide keystroke detection
    try:
        import pynput
        run_pynput_mode(ser)
    except ImportError:
        print("\n[i] Note: 'pynput' is not installed. To react to global keystrokes across all apps,")
        print("    run: pip install pynput\n")
        run_terminal_mode(ser)

    ser.close()


if __name__ == "__main__":
    main()
