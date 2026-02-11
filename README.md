# CANUSB Monitor for Linux

A modern, high-performance Python application for monitoring CAN bus traffic using a USB-CAN adapter. This tool provides a rich graphical interface with real-time data visualization, advanced multi-filtering capabilities, and export features.

![CANUSB Monitoring Hardware](USB-CAN.jpg)

## Features

- **Real-time Monitoring**: Stream CAN frames directly from your USB-CAN hardware.
- **Advanced Filtering**: 
  - Add multiple concurrent filters.
  - Support for **Include** (whitelist) and **Exclude** (blacklist) logic.
  - Filter by **CAN ID** or **Data Pattern** (Hex).
- **Project Management**: Save and load your filter configurations (JSON format) via the **Project** menu.
- **Enhanced Table Interaction**:
  - Support for **Multi-selection** (Shift/Ctrl + Click).
  - **Clipboard Support**: Copy selected cells/rows to the clipboard via the right-click menu.
- **Smart Context Menu**: Right-click to copy or quickly add a single value to filters.
- **Dual Data View**: View payload data in both **Hexadecimal** and **Decimal** formats simultaneously.
- **Export**: Save your filtered data to `.txt` (tabular) or `.csv` formats.
- **Dark Theme**: Premium dark-mode interface for comfortable long-term use.
- **CLI Support**: Launch with pre-configured port and speed settings.

## Hardware Support

Designed to work with USB-CAN adapters following the protocol used in typical `canusb.c` implementations. This software is specifically compatible with the device shown in the header image.
- **Default Serial Settings**: 2,000,000 baud, 2 stop bits.
- **Supported CAN Speeds**: 5k to 1M bit/s.

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/jaruizn/usb-can.git
   cd usb-can
   ```

2. **Create a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Start the application:
```bash
python3 can_monitor_gui.py
```

### CLI Arguments
- `-d`, `--device`: Serial port path (e.g., `/dev/ttyUSB0` or `COM3`).
- `-s`, `--speed`: CAN bus speed in bps (default: 500000).
- `-b`, `--baudrate`: Serial link baudrate (default: 2000000).

Example:
```bash
python3 can_monitor_gui.py -d /dev/ttyUSB0 -s 250000
```

## Repository Structure

- `can_monitor_gui.py`: Main application entry point and UI logic.
- `canusb_backend.py`: Serial communication and CAN protocol parser.
- `requirements.txt`: Python dependency list.
- `.gitignore`: Common Python git exclusion rules.

## License

MIT License - feel free to use and modify for your own projects.
