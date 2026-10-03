# RP2040 Matrix — Universal Keyboard Reactive Visualizer 🎆

An interactive ambient light and real-time reactive typing visualizer for **Raspberry Pi RP2040**-based development boards paired with WS2812B (NeoPixel) RGB LED matrices.

Designed with **maximum universality** in mind: works across **all RP2040 boards**, runs out-of-the-box on **any MicroPython version** (v1.14 through v1.24+), maintains seamless **CircuitPython** compatibility, operates independently of host Python versions, and delivers smooth, stutter-free 50–60+ FPS performance.

---

## 📋 Table of Contents
1. [Project Overview & Visualizer Mechanics](#-project-overview--visualizer-mechanics)
2. [Target Hardware Specifications](#-target-hardware-specifications)
3. [Universal Firmware Architecture](#-universal-firmware-architecture)
4. [Repository Structure](#-repository-structure)
5. [Quick Start Guide](#-quick-start-guide)
   - [Option A: MicroPython (Recommended)](#option-a-micropython-recommended)
   - [Option B: CircuitPython](#option-b-circuitpython)
   - [Option C: Standalone Ambient Light Mode](#option-c-standalone-ambient-light-mode)
6. [Host Companion Script (Keyboard Reactivity)](#-host-companion-script-keyboard-reactivity)
7. [Configuration Reference](#-configuration-reference)
8. [Wiring & Custom Board Pinout](#-wiring--custom-board-pinout)
9. [Troubleshooting & FAQ](#-troubleshooting--faq)
10. [License](#-license)

---

## 💡 Project Overview & Visualizer Mechanics

This project bridges real-time mathematical wave modeling on embedded hardware with desktop typing activity over USB:

### 1. Ambient Mode (2D Trigonometric Plasma Simulation)
When idle, the board synthesizes a flowing, multi-layered 2D plasma wave across the matrix:
* **Wave Superposition:** The light intensity $v(r, c, t)$ at row $r$, column $c$, and elapsed time $t$ is computed as the average of three continuous sinusoidal waveforms:
  $$v(r, c, t) = \frac{\sin(r \cdot 1.3 + t \cdot \omega) + \sin(c \cdot 1.3 + t \cdot \omega) + \sin(d_{center}(r, c) \cdot 1.8 - t \cdot \omega)}{3.0}$$
* **Radial Center Wave:** $d_{center}(r, c) = \sqrt{(c - c_{mid})^2 + (r - r_{mid})^2}$ generates ripples emanating from the matrix midpoint.
* **HSV Color Mapping:** The scalar intensity $v$ drives dynamic hue rotation $\theta(t) = (v \cdot 120^\circ + t \cdot 40^\circ) \pmod{360^\circ}$, transformed into vibrant 8-bit RGB values.

### 2. Reactive Mode (Keystroke Ripple Wave)
Whenever you type on your computer (in any application, browser, code editor, or game), the host companion client streams trigger pulses over USB Serial:
* **Chebyshev Rings:** An expanding wave front originates from the center and travels outward through concentric rings defined by the Chebyshev metric:
  $$D_{Chebyshev}((r, c), (r_{mid}, c_{mid})) = \max(|r - r_{mid}|, |c - c_{mid}|)$$
* **Alpha Blending:** Each ripple wave is assigned a random neon hue upon birth. As the wave propagates, its opacity decays linearly:
  $$\alpha = \max(0.0, 1.0 - \text{ring\_index} \times \text{decay})$$
  The ripple is blended over the underlying plasma via alpha compositing:
  $$C_{final} = C_{plasma} \times (1.0 - \alpha) + C_{ripple} \times \alpha$$

---

## 🖲️ Target Hardware Specifications

### Primary Target: Waveshare RP2040-Matrix
The visualizer was originally developed for the **Waveshare RP2040-Matrix** development board:
* **Microcontroller:** Raspberry Pi RP2040 (Dual ARM Cortex-M0+ running up to 133 MHz, 264 KB SRAM, 2 MB QSPI Flash).
* **Onboard LED Matrix:** 5×5 grid (25 addressable RGB LEDs) based on the **WS2812B** (NeoPixel) protocol.
* **Matrix Data Pin:** Hardwired internally to **GPIO 16 (GP16)**.
* **Wiring Topology:** **Serpentine / Zigzag** — even rows (0, 2, 4...) run left-to-right, while odd rows (1, 3...) run right-to-left. The engine incorporates geometric coordinate compensation (`SERPENTINE = True`) to preserve distortion-free concentric ripples.
* **Interface:** USB Type-C connector with BOOT and RESET tactile switches.

### Universal Compatibility with Other RP2040 Boards
The engine is completely hardware-agnostic and runs on any RP2040 development board:
* **Raspberry Pi Pico / Pico W / Pico 2**
* **Waveshare RP2040-Zero / RP2040-Plus / RP2040-One**
* **Seeed Studio XIAO RP2040**
* Custom boards or external WS2812B matrices (5×5, 8×8, 16×16, etc.) connected to any GPIO pin.

---

## ⚙️ Universal Firmware Architecture

Key technical engineering decisions that ensure compatibility across all environments:

1. **Multi-Tier Hardware Abstraction Layer ([`UniversalMatrix`](file:///Users/booo/embeded/rp2040-matrix-visulizer/main.py#L125-L224)):**
   * **Native MicroPython Driver:** Uses the built-in C-level `neopixel` and `machine.Pin` modules included in official RP2040 builds. Requires no external libraries or `.mpy` files.
   * **Native RP2040 Hardware PIO Fallback:** If running on a minimal or legacy MicroPython build lacking the `neopixel` module, the engine compiles and executes an assembly state machine using RP2040's Programmable I/O (`rp2.asm_pio`) at 800 kHz.
   * **CircuitPython Driver:** Detects Adafruit CircuitPython environments and binds through `board.GP16` and CircuitPython's `neopixel`.
   * **Headless Emulation Driver:** When executed on desktop Python 3, the engine automatically switches to headless dummy mode for testing and CI validation.

2. **Safe Software Brightness Scaling (Overcurrent Protection):**
   * 25 WS2812 LEDs at full white (255, 255, 255) draw ~1.5 Amps, which can trigger USB port shutdown or MCU resets.
   * The driver incorporates safe software scaling (`BRIGHTNESS = 0.05` by default), limiting current to ~60–80 mA while preserving vivid contrast.

3. **Rollover-Proof High-Resolution Timer:**
   * MicroPython's `time.ticks_ms()` is a 30-bit signed integer that rolls over every ~12.4 days.
   * The clock implementation calculates deltas via `time.ticks_diff()`, allowing continuous operation for months without timing distortion or drift.

4. **Non-blocking USB Serial (Zero FPS Drops):**
   * Serial input is queried non-blockingly using `select.poll(0)` on `sys.stdin` (MicroPython) and `usb_cdc.data` (CircuitPython). The render loop never stalls while awaiting keystrokes.

5. **Zero-Allocation Render Loop (Zero GC Stutter):**
   * Frame buffers and trigonometric lookup tables are allocated once at startup.
   * The 60 FPS animation loop performs zero dynamic list allocations, preventing MicroPython Garbage Collector latency spikes.

---

## 📁 Repository Structure

```text
rp2040-matrix-visulizer/
├── .gitignore               # Excludes OS artifacts, virtualenvs, and MCU boot logs
├── boot.py                  # Early USB endpoint configuration for RP2040
├── code.py                  # CircuitPython entrypoint (delegates to main.py)
├── main.py                  # Universal visualizer engine (MicroPython & CircuitPython)
├── settings.toml.example    # Configuration template for CircuitPython environments
├── host/                    # Host computer companion client
│   ├── keyboard_listener.py # Cross-platform global keystroke capture and serial bridge
│   └── requirements.txt     # Python dependencies for the host client (pyserial, pynput)
└── README.md                # Comprehensive documentation
```

---

## 🚀 Quick Start Guide

### Option A: MicroPython (Recommended)

MicroPython provides the lowest memory overhead and maximum frame rates.

1. **Flash MicroPython to your board (if not already installed):**
   - Hold the **BOOTSEL** (or **BOOT**) button on your board and connect it to your computer via USB.
   - The board will mount as a mass storage volume named `RPI-RP2`.
   - Download the official `.uf2` firmware for your board from [micropython.org/download](https://micropython.org/download/) (e.g. Raspberry Pi Pico or RP2040-Zero) and drag it onto `RPI-RP2`. The board will automatically reboot into MicroPython.

2. **Upload the code:**
   - **Method 1: Thonny IDE (Easiest)**
     1. Download and open [Thonny IDE](https://thonny.org/).
     2. In the bottom-right corner, select interpreter: **MicroPython (Raspberry Pi Pico)**.
     3. Open [`main.py`](file:///Users/booo/embeded/rp2040-matrix-visulizer/main.py) and select *File -> Save as... -> Raspberry Pi Pico -> main.py*.
     4. Save [`boot.py`](file:///Users/booo/embeded/rp2040-matrix-visulizer/boot.py) to the device as `boot.py`.
   - **Method 2: Command Line via `mpremote`**
     ```bash
     pip install mpremote
     mpremote cp boot.py :boot.py
     mpremote cp main.py :main.py
     mpremote reset
     ```

3. The board will immediately start rendering the ambient plasma!

---

### Option B: CircuitPython

If you prefer Adafruit CircuitPython:

1. Connect your CircuitPython-flashed board (mounts as `CIRCUITPY`).
2. Copy [`main.py`](file:///Users/booo/embeded/rp2040-matrix-visulizer/main.py), [`code.py`](file:///Users/booo/embeded/rp2040-matrix-visulizer/code.py), and [`boot.py`](file:///Users/booo/embeded/rp2040-matrix-visulizer/boot.py) to the root of the `CIRCUITPY` drive.
3. Ensure `neopixel.mpy` from the official Adafruit CircuitPython Bundle is located in the `/lib` folder of the board.
4. CircuitPython will automatically reload and launch the visualizer.

---

### Option C: Standalone Ambient Light Mode

No computer is required for the visualizer to run. Simply connect the RP2040 board to any 5V USB wall adapter, USB power strip, or power bank. The board will boot and run the ambient plasma animation autonomously.

---

## ⌨️ Host Companion Script (Keyboard Reactivity)

To enable keyboard reactivity so that the matrix illuminates as you type:

1. **Install dependencies on your host computer:**
   ```bash
   pip install -r host/requirements.txt
   ```

2. **Launch the keyboard listener:**
   ```bash
   python host/keyboard_listener.py
   ```
   *The script automatically detects the connected RP2040 serial port (`/dev/cu.usbmodem*` on macOS, `/dev/ttyACM*` on Linux, `COM*` on Windows) and starts streaming keystrokes.*

3. **CLI Options:**
   - **Automated Demo Mode (generates pulses periodically without typing):**
     ```bash
     python host/keyboard_listener.py --demo --rate 2.0
     ```
   - **Specify a custom serial port manually:**
     ```bash
     python host/keyboard_listener.py --port /dev/cu.usbmodem1101
     ```
   - **Connection Health Check (sends a single pulse and exits):**
     ```bash
     python host/keyboard_listener.py --test
     ```

> **macOS Accessibility Permission:** On macOS, global background key detection requires Accessibility permissions. When running `pynput` for the first time, grant permission to your terminal app (Terminal, iTerm2, or VS Code) under:
> *System Settings -> Privacy & Security -> Accessibility*.

---

## 🔧 Configuration Reference

All settings can be customized at the top of [`main.py`](file:///Users/booo/embeded/rp2040-matrix-visulizer/main.py):

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `LED_PIN` | `16` | RP2040 GPIO pin connected to the matrix data line (GP16 on Waveshare RP2040-Matrix) |
| `ROWS` | `5` | Number of LED rows in the matrix |
| `COLS` | `5` | Number of LED columns in the matrix |
| `SERPENTINE` | `True` | Set `True` for zigzag trace layout (Waveshare), `False` for linear progressive layout |
| `BRIGHTNESS` | `0.05` | Global brightness scalar (0.01 to 1.0; 0.05 = 5%, safe for USB power) |
| `SPEED_PLASMA` | `3.5` | Speed factor of the ambient plasma wave oscillation |
| `RING_STEP` | `0.035` | Propagation delay in seconds between concentric ring expansions |
| `RING_FADE` | `0.25` | Opacity decay step per concentric ring expansion |

---

## 🔌 Wiring & Custom Board Pinout

If you are using a standard **Raspberry Pi Pico**, **RP2040-Zero**, or an external WS2812B matrix module:

```text
RP2040 Board                WS2812B LED Matrix
┌──────────────┐            ┌─────────────────┐
│   VBUS / 5V  ├───────────►│ VDD / 5V / +    │
│   GND        ├───────────►│ GND / -         │
│   GP16 (GPIO)├───────────►│ DIN / DI / Data │
└──────────────┘            └─────────────────┘
```

* To use another pin (such as **GP22** or **GP28**), update `LED_PIN = 22` in [`main.py`](file:///Users/booo/embeded/rp2040-matrix-visulizer/main.py).
* For larger matrices (e.g. 8×8), set `ROWS = 8` and `COLS = 8`. The mathematical distance and Chebyshev ring precomputations adapt automatically to any dimensions.

---

## ❓ Troubleshooting & FAQ

#### 1. The LEDs are uncomfortably bright or drawing too much power
Adjust `BRIGHTNESS = 0.03` or `0.02` in [`main.py`](file:///Users/booo/embeded/rp2040-matrix-visulizer/main.py). Even at 2–5% brightness, WS2812 LEDs provide vibrant desktop illumination with low power draw.

#### 2. The ripple rings look distorted or mirrored on every second row
Your matrix uses a serpentine wiring pattern. Ensure `SERPENTINE = True` in [`main.py`](file:///Users/booo/embeded/rp2040-matrix-visulizer/main.py). If you are using a straight linear matrix, set `SERPENTINE = False`.

#### 3. How to test ripples without running the host script
Open a serial terminal connected to your board (such as the Thonny REPL, Screen, PuTTY, or the Arduino Serial Monitor) at 115200 baud and press the spacebar or Enter key. Every transmitted character instantly triggers a ripple on the matrix.

---

## 📄 License
This project is open-source and released under the [MIT License](https://opensource.org/licenses/MIT). Feel free to adapt, extend, and embed it in your own hardware projects!
