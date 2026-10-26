"""Protocol tests built from bytes captured from the official app and a real TP920W."""

from datetime import datetime, timezone
import unittest

from _loader import load

protocol = load("protocol")

# Writes the official app sent to the command characteristic (capture frames 913-930).
CAPTURED_LOGIN = bytes.fromhex("01098a7a13b73ed68b67c2a0")
CAPTURED_INFO = bytes.fromhex("410041")
CAPTURED_TIME = bytes.fromhex("28040ccd961fba")
CAPTURED_UNIT_F = bytes.fromhex("20010f30")
CAPTURED_ACK = bytes.fromhex("300030")
# Wall-clock time of the captured time write (UTC).
CAPTURE_TIME = datetime(2026, 10, 21, 18, 38, 23, 606511, tzinfo=timezone.utc)

# Notifications received from the thermometer (probe 1 idle at 22.7 C, probe 2 warming).
FRAME_P2_37_3 = bytes.fromhex("300f610f00ffff0227ffff0373ffffffff460140")
FRAME_P2_37_2 = bytes.fromhex("300f610f00ffff0227ffff0372ffffffff450140")
FRAME_P2_36_6 = bytes.fromhex("300f610f00ffff0227ffff0366ffffffff390140")
# Other frame types seen in the capture.
OTHER_FRAMES = [
    bytes.fromhex("01020a020fb73ed68b67c2a00020b73ed68b67c2"),
    bytes.fromhex("410329110280917d0000e1190020480000200200"),
    bytes.fromhex("2302020027ffffff270000190020480000200200"),
    bytes.fromhex("2302040029ffffff290000190020480000200200"),
]


def telemetry(p1: bytes = b"\xff\xff", p2: bytes = b"\xff\xff", battery=0x61, unit=0x0F) -> bytes:
    """Build a valid 20-byte telemetry notification."""
    body = bytes([0x30, 0x0F, battery, unit, 0x00, 0xFF, 0xFF]) + p1
    body += b"\xff\xff" + p2 + b"\xff\xff\xff\xff"
    return body + bytes([protocol.checksum(body)]) + b"\x01\x40"


class BuildCommandTests(unittest.TestCase):
    def test_reproduces_captured_writes(self):
        self.assertEqual(protocol.login_command(), CAPTURED_LOGIN)
        self.assertEqual(protocol.INFO_REQUEST, CAPTURED_INFO)
        self.assertEqual(protocol.unit_command(True), CAPTURED_UNIT_F)
        self.assertEqual(protocol.ACK, CAPTURED_ACK)

    def test_time_command_matches_capture(self):
        self.assertEqual(protocol.time_command(CAPTURE_TIME), CAPTURED_TIME)

    def test_time_command_is_timezone_independent(self):
        local = CAPTURE_TIME.astimezone(timezone(offset=__import__("datetime").timedelta(hours=-4)))
        self.assertEqual(protocol.time_command(local), CAPTURED_TIME)

    def test_time_command_requires_aware_datetime(self):
        with self.assertRaises(ValueError):
            protocol.time_command(datetime(2026, 10, 21, 18, 38, 23))

    def test_celsius_unit_command_follows_pattern(self):
        self.assertEqual(protocol.unit_command(False), bytes.fromhex("20010c2d"))

    def test_handshake_order(self):
        commands = protocol.handshake(CAPTURE_TIME, True)
        self.assertEqual(commands, [CAPTURED_LOGIN, CAPTURED_INFO, CAPTURED_TIME, CAPTURED_UNIT_F])

    def test_every_captured_write_has_a_valid_checksum(self):
        for frame in (CAPTURED_LOGIN, CAPTURED_INFO, CAPTURED_TIME, CAPTURED_UNIT_F, CAPTURED_ACK):
            self.assertEqual(frame[-1], protocol.checksum(frame[:-1]))
            self.assertEqual(frame[1], len(frame) - 3)


class ParseTests(unittest.TestCase):
    def test_real_frames(self):
        cases = [(FRAME_P2_37_3, 37.3), (FRAME_P2_37_2, 37.2), (FRAME_P2_36_6, 36.6)]
        for frame, expected in cases:
            with self.subTest(frame=frame.hex()):
                reading = protocol.parse_notification(frame)
                self.assertEqual(reading.probe1, 22.7)
                self.assertEqual(reading.probe2, expected)
                self.assertEqual(reading.battery, 97)
                self.assertTrue(reading.fahrenheit_display)

    def test_fahrenheit_reading_matches_the_unit_display(self):
        reading = protocol.parse_notification(FRAME_P2_37_3)
        self.assertEqual(round(reading.probe2 * 9 / 5 + 32), 99)  # unit showed 99 F

    def test_other_frame_types_are_ignored(self):
        for frame in OTHER_FRAMES:
            with self.subTest(frame=frame.hex()):
                self.assertIsNone(protocol.parse_notification(frame))

    def test_bad_checksum_is_rejected(self):
        bad = bytearray(FRAME_P2_37_3)
        bad[17] ^= 0x01
        self.assertIsNone(protocol.parse_notification(bytes(bad)))

    def test_corrupt_payload_is_rejected(self):
        bad = bytearray(FRAME_P2_37_3)
        bad[12] ^= 0x01
        self.assertIsNone(protocol.parse_notification(bytes(bad)))

    def test_truncated_frames_are_rejected(self):
        for size in range(0, 18):
            with self.subTest(size=size):
                self.assertIsNone(protocol.parse_notification(FRAME_P2_37_3[:size]))

    def test_unplugged_probe_is_none(self):
        reading = protocol.parse_notification(telemetry(p1=b"\xff\xff", p2=b"\x03\x73"))
        self.assertIsNone(reading.probe1)
        self.assertEqual(reading.probe2, 37.3)

    def test_both_unplugged(self):
        reading = protocol.parse_notification(telemetry())
        self.assertIsNone(reading.probe1)
        self.assertIsNone(reading.probe2)

    def test_invalid_bcd_is_unknown_not_garbage(self):
        reading = protocol.parse_notification(telemetry(p1=b"\x0a\x00", p2=b"\x01\x2f"))
        self.assertIsNone(reading.probe1)
        self.assertIsNone(reading.probe2)

    def test_hot_smoker_range(self):
        reading = protocol.parse_notification(telemetry(p1=b"\x12\x10", p2=b"\x00\x94"))
        self.assertEqual(reading.probe1, 121.0)
        self.assertEqual(reading.probe2, 9.4)

    def test_celsius_display_flag(self):
        reading = protocol.parse_notification(telemetry(unit=0x0C))
        self.assertFalse(reading.fahrenheit_display)

    def test_battery_percentage(self):
        self.assertEqual(protocol.parse_notification(telemetry(battery=0x52)).battery, 82)
        self.assertEqual(protocol.parse_notification(telemetry(battery=0x5A)).battery, 90)


if __name__ == "__main__":
    unittest.main()
