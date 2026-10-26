"""Session tests against a fake GATT client."""

import asyncio
from datetime import datetime, timezone
import unittest

from _loader import load

protocol = load("protocol")
link = load("link")

CAPTURE_TIME = datetime(2026, 10, 21, 18, 38, 23, 606511, tzinfo=timezone.utc)
GOOD_FRAME = bytes.fromhex("300f610f00ffff0227ffff0373ffffffff460140")


class FakeClient:
    def __init__(self):
        self.is_connected = True
        self.notify_callback = None
        self.notify_uuid = None
        self.writes = []
        self.fail_writes = False
        self.stopped = False

    async def start_notify(self, char_specifier, callback):
        self.notify_uuid = char_specifier
        self.notify_callback = callback

    async def stop_notify(self, char_specifier):
        self.stopped = True

    async def write_gatt_char(self, char_specifier, data, response=None):
        if self.fail_writes:
            raise RuntimeError("write failed")
        self.writes.append((char_specifier, bytes(data), response))
        await asyncio.sleep(0)


def make_session(client, readings, **kwargs):
    return link.TP920Session(
        client,
        readings.append,
        clock=lambda: CAPTURE_TIME,
        settle=0,
        step_delay=0,
        **kwargs,
    )


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_subscribes_then_replays_handshake_in_order(self):
        client, readings = FakeClient(), []
        await make_session(client, readings).async_start()
        self.assertEqual(client.notify_uuid, protocol.NOTIFY_UUID)
        self.assertEqual(
            client.writes,
            [(protocol.COMMAND_UUID, command, True) for command in protocol.handshake(CAPTURE_TIME, True)],
        )

    async def test_celsius_display_option_changes_only_the_unit_write(self):
        client, readings = FakeClient(), []
        await make_session(client, readings, fahrenheit_display=False).async_start()
        self.assertEqual(client.writes[-1][1], protocol.unit_command(False))
        self.assertEqual([w[1] for w in client.writes[:-1]], protocol.handshake(CAPTURE_TIME)[:-1])

    async def test_telemetry_is_reported_and_acked(self):
        client, readings = FakeClient(), []
        session = make_session(client, readings)
        await session.async_start()
        client.writes.clear()
        client.notify_callback(None, bytearray(GOOD_FRAME))
        await asyncio.sleep(0.01)
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].probe2, 37.3)
        self.assertEqual(client.writes, [(protocol.COMMAND_UUID, protocol.ACK, True)])

    async def test_every_frame_gets_its_own_ack(self):
        client, readings = FakeClient(), []
        session = make_session(client, readings)
        await session.async_start()
        client.writes.clear()
        for _ in range(3):
            client.notify_callback(None, bytearray(GOOD_FRAME))
        await asyncio.sleep(0.01)
        self.assertEqual(len(readings), 3)
        self.assertEqual([w[1] for w in client.writes], [protocol.ACK] * 3)

    async def test_other_frames_and_bad_checksums_are_not_acked(self):
        client, readings = FakeClient(), []
        session = make_session(client, readings)
        await session.async_start()
        client.writes.clear()
        bad = bytearray(GOOD_FRAME)
        bad[17] ^= 0xFF
        for frame in (bytes.fromhex("2302020027ffffff270000190020480000200200"), bytes(bad)):
            client.notify_callback(None, bytearray(frame))
        await asyncio.sleep(0.01)
        self.assertEqual(readings, [])
        self.assertEqual(client.writes, [])

    async def test_failed_ack_does_not_raise(self):
        client, readings = FakeClient(), []
        session = make_session(client, readings)
        await session.async_start()
        client.fail_writes = True
        client.notify_callback(None, bytearray(GOOD_FRAME))
        await asyncio.sleep(0.01)
        self.assertEqual(len(readings), 1)

    async def test_frames_after_close_are_ignored(self):
        client, readings = FakeClient(), []
        session = make_session(client, readings)
        await session.async_start()
        session.close()
        client.writes.clear()
        client.notify_callback(None, bytearray(GOOD_FRAME))
        await asyncio.sleep(0.01)
        self.assertEqual(readings, [])
        self.assertEqual(client.writes, [])

    async def test_stop_unsubscribes_only_while_connected(self):
        client, readings = FakeClient(), []
        session = make_session(client, readings)
        await session.async_start()
        client.is_connected = False
        await session.async_stop()
        self.assertFalse(client.stopped)

        client2 = FakeClient()
        session2 = make_session(client2, readings)
        await session2.async_start()
        await session2.async_stop()
        self.assertTrue(client2.stopped)

    async def test_handshake_failure_propagates(self):
        client, readings = FakeClient(), []
        client.fail_writes = True
        with self.assertRaises(RuntimeError):
            await make_session(client, readings).async_start()


if __name__ == "__main__":
    unittest.main()
