import serial
import serial.tools.list_ports
import threading
import time
from dataclasses import dataclass
from typing import List, Callable

@dataclass
class CANFrame:
    """Representa una trama CAN individual."""
    id: int                # CAN Identifier (Standard or Extended)
    dlc: int               # Data Length Code (0-8)
    data: bytes            # Payload bytes
    is_extended: bool = False # True if using 29-bit identifier
    timestamp: float = 0.0    # Arrival timestamp (unix epoch)

class CANUSBBackend:
    """
    Handles serial communication and protocol parsing for the CANUSB Monitor for Linux.
    Based on the canusb.c protocol definition.
    """
    def __init__(self, port, baudrate=2000000, can_speed=500000):
        self.port = port
        self.baudrate = baudrate
        self.can_speed = can_speed
        self.ser = None
        self.running = False
        self.read_thread = None
        self.on_frame_received: List[Callable[[CANFrame], None]] = []
        self.buffer = bytearray()

    def add_callback(self, callback: Callable[[CANFrame], None]):
        """Register a callback function to be called when a new CAN frame is received."""
        self.on_frame_received.append(callback)

    def connect(self):
        """Establish serial connection and start the background reading thread."""
        try:
            # Protocol uses 2 stop bits (CSTOPB in C)
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.1, stopbits=serial.STOPBITS_TWO)
            self._init_adapter()
            self.running = True
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            return True
        except Exception:
            return False

    def disconnect(self):
        """Stop monitoring and close the serial port."""
        self.running = False
        if self.read_thread:
            self.read_thread.join()
        if self.ser:
            self.ser.close()

    def _generate_checksum(self, data: bytes) -> int:
        """Calculate the 8-bit checksum for command packets."""
        return sum(data) & 0xFF

    def _init_adapter(self):
        """Send initialization command to the USB-CAN adapter to set CAN bus speed."""
        # Speed mapping derived from canusb.c
        speed_map = {
            1000000: 0x01, 800000: 0x02, 500000: 0x03, 400000: 0x04,
            250000: 0x05, 200000: 0x06, 125000: 0x07, 100000: 0x08,
            50000: 0x09, 20000: 0x0a, 10000: 0x0b, 5000: 0x0c
        }
        speed_byte = speed_map.get(self.can_speed, 0x03) # Default to 500k
        
        # AA 55 start bytes, 0x12 command type...
        cmd = bytearray([0xAA, 0x55, 0x12, speed_byte, 0x01, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x01, 0, 0, 0, 0])
        checksum = self._generate_checksum(cmd[2:])
        cmd.append(checksum)
        self.ser.write(cmd)

    def _read_loop(self):
        """Background thread loop to read bytes from the serial port."""
        self.buffer = bytearray()
        while self.running:
            self._read_loop_iteration()
            if self.ser.in_waiting == 0:
                time.sleep(0.001)

    def _read_loop_iteration(self):
        """Read pending bytes and trigger buffer processing."""
        if self.ser.in_waiting > 0:
            data = self.ser.read(self.ser.in_waiting)
            self.buffer.extend(data)
        self._process_buffer()

    def _process_buffer(self):
        """
        Parse the byte buffer to identify CAN frames using the specified framing.
        Framing: 0xAA (Start) ... 0x55 (End)
        """
        while len(self.buffer) > 0:
            # Each frame must start with 0xAA
            if self.buffer[0] != 0xAA:
                self.buffer.pop(0)
                continue
            
            if len(self.buffer) < 2:
                break
            
            # 0x55 as second byte indicates a command/response frame (fixed 20 bytes)
            if self.buffer[1] == 0x55:
                if len(self.buffer) >= 20:
                    self.buffer = self.buffer[20:]
                else:
                    break
            # 0x0C in high nibble of second byte indicates a standard data frame
            elif (self.buffer[1] >> 4) == 0x0C:
                dlc = self.buffer[1] & 0x0F
                frame_len = dlc + 5 # 0xAA + CMD + ID_L + ID_H + DATA[DLC] + 0x55
                if len(self.buffer) >= frame_len:
                    frame_data = self.buffer[:frame_len]
                    if frame_data[-1] == 0x55: # Verify end byte
                        is_ext = bool(frame_data[1] & 0x20)
                        can_id = frame_data[2] | (frame_data[3] << 8)
                        frame = CANFrame(
                            id=can_id,
                            dlc=dlc,
                            data=bytes(frame_data[4:4+dlc]),
                            is_extended=is_ext,
                            timestamp=time.time()
                        )
                        # Notify all observers
                        for callback in self.on_frame_received:
                            callback(frame)
                    self.buffer = self.buffer[frame_len:]
                else:
                    break
            else:
                # Discard invalid start byte
                self.buffer.pop(0)
