import unittest
from canusb_backend import CANUSBBackend, CANFrame

class MockSerial:
    def __init__(self):
        self.in_waiting = 0
        self.buffer = bytearray()
        self.written = []

    def read(self, size):
        data = self.buffer[:size]
        self.buffer = self.buffer[size:]
        self.in_waiting = len(self.buffer)
        return data

    def write(self, data):
        self.written.append(data)

    def close(self):
        pass

class TestCANUSBBackend(unittest.TestCase):
    def test_parse_data_frame(self):
        backend = CANUSBBackend("MOCK")
        backend.running = True
        
        frames_received = []
        backend.add_callback(lambda f: frames_received.append(f))
        
        # Standard data frame: 0xaa, 0xc8 (DLC 8, STD, Data), ID 0x123 (LSB 0x23, MSB 0x01), 8 bytes data, 0x55
        test_data = bytes([0xAA, 0xC8, 0x23, 0x01, 1, 2, 3, 4, 5, 6, 7, 8, 0x55])
        backend.buffer.extend(test_data)
        
        backend._process_buffer()
        
        self.assertEqual(len(frames_received), 1)
        frame = frames_received[0]
        self.assertEqual(frame.id, 0x123)
        self.assertEqual(frame.dlc, 8)
        self.assertEqual(frame.data, bytes([1, 2, 3, 4, 5, 6, 7, 8]))
        self.assertFalse(frame.is_extended)


    def test_parse_extended_data_frame(self):
        backend = CANUSBBackend("MOCK")
        backend.running = True
        
        frames_received = []
        backend.add_callback(lambda f: frames_received.append(f))
        
        # Extended data frame (from user): aa e5 50 00 00 00 ff aa 69 88 b5 55
        # dlc=5, ID=0x50, is_extended=True
        test_data = bytes([0xAA, 0xE5, 0x50, 0x00, 0x00, 0x00, 0xFF, 0xAA, 0x69, 0x88, 0xB5, 0x55])
        backend.buffer.extend(test_data)
        
        backend._process_buffer()
        
        self.assertEqual(len(frames_received), 1)
        frame = frames_received[0]
        self.assertEqual(frame.id, 0x50)
        self.assertEqual(frame.dlc, 5)
        self.assertEqual(frame.data, bytes([0xFF, 0xAA, 0x69, 0x88, 0xB5]))
        self.assertTrue(frame.is_extended)


if __name__ == "__main__":
    unittest.main()
