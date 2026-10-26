"""Coordinator logic against stubbed Home Assistant and Bleak modules."""

import asyncio
from datetime import datetime, timezone
from functools import partial
import time
import unittest
from unittest import mock

import _ha_stubs
from _loader import load

STUBS = _ha_stubs.install()
protocol = load("protocol")
link = load("link")
coordinator_module = load("coordinator")

ADDRESS = "C4:8F:2A:B4:AD:B7"
GOOD_FRAME = bytes.fromhex("300f610f00ffff0227ffff0373ffffffff460140")


class FakeEntry:
    title = "ThermoPro TP920 ADB7"

    def __init__(self):
        self.tasks = []

    def async_create_background_task(self, hass, target, name):
        task = asyncio.get_running_loop().create_task(target, name=name)
        self.tasks.append(task)
        return task

    async def settle(self):
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await asyncio.sleep(0)


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        STUBS.reset()
        patcher = mock.patch.object(
            coordinator_module,
            "TP920Session",
            partial(link.TP920Session, settle=0, step_delay=0),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.entry = FakeEntry()
        self.coordinator = coordinator_module.TP920Coordinator(object(), self.entry, ADDRESS, True)
        self.updates = 0
        self.coordinator.async_add_listener(self._count)

    def _count(self):
        self.updates += 1

    async def start(self):
        self.coordinator.async_start()
        await self.entry.settle()

    def advertise(self):
        STUBS.advert_callback(object(), object())

    async def test_registers_for_its_own_address_only(self):
        await self.start()
        self.assertEqual(STUBS.registered_matcher, {"address": ADDRESS})

    async def test_connects_on_start_and_replays_handshake(self):
        await self.start()
        client = STUBS.clients[0]
        self.assertTrue(self.coordinator.connected)
        self.assertEqual(len(client.writes), 4)
        self.assertEqual(client.writes[0][:2], bytes([protocol.CMD_LOGIN, 9]))
        self.assertEqual(client.writes[-1], protocol.unit_command(True))
        self.assertEqual(STUBS.stale_closed, [ADDRESS])

    async def test_readings_are_stored_and_listeners_called(self):
        await self.start()
        before = self.updates
        STUBS.clients[0].notify_callback(None, bytearray(GOOD_FRAME))
        await asyncio.sleep(0.01)
        self.assertEqual(self.coordinator.data.probe2, 37.3)
        self.assertGreater(self.updates, before)
        self.assertEqual(STUBS.clients[0].writes[-1], protocol.ACK)

    async def test_nothing_happens_while_device_is_not_visible(self):
        STUBS.device_present = False
        await self.start()
        self.assertEqual(STUBS.establish_calls, 0)
        self.assertFalse(self.coordinator.connected)

    async def test_disconnect_clears_state_and_next_advert_reconnects(self):
        await self.start()
        STUBS.clients[0].notify_callback(None, bytearray(GOOD_FRAME))
        await asyncio.sleep(0.01)
        STUBS.clients[0].drop()
        self.assertFalse(self.coordinator.connected)
        self.assertIsNone(self.coordinator.data)
        self.advertise()
        await self.entry.settle()
        self.assertEqual(len(STUBS.clients), 2)
        self.assertTrue(self.coordinator.connected)

    async def test_drop_before_any_data_backs_off(self):
        await self.start()
        STUBS.clients[0].drop()
        self.assertGreater(self.coordinator._retry_at, time.monotonic())
        self.advertise()
        await self.entry.settle()
        self.assertEqual(STUBS.establish_calls, 1)

    async def test_failures_reset_once_data_flows(self):
        STUBS.establish_script = [_ha_stubs.BleakError("busy")]
        await self.start()
        self.assertEqual(self.coordinator._failures, 1)
        self.coordinator._retry_at = 0.0
        self.advertise()
        await self.entry.settle()
        self.assertEqual(self.coordinator._failures, 1, "connected but no data yet")
        STUBS.clients[0].notify_callback(None, bytearray(GOOD_FRAME))
        await asyncio.sleep(0.01)
        self.assertEqual(self.coordinator._failures, 0)

    async def test_stale_disconnect_callback_is_ignored(self):
        await self.start()
        stranger = _ha_stubs.FakeGattClient(None)
        self.coordinator._async_on_disconnect(stranger)
        self.assertTrue(self.coordinator.connected)

    async def test_failed_connect_backs_off_then_retries(self):
        STUBS.establish_script = [_ha_stubs.BleakError("busy")]
        await self.start()
        self.assertFalse(self.coordinator.connected)
        self.assertEqual(STUBS.establish_calls, 1)
        self.advertise()
        await self.entry.settle()
        self.assertEqual(STUBS.establish_calls, 1, "must not retry inside the backoff window")
        self.coordinator._retry_at = time.monotonic() - 1
        self.advertise()
        await self.entry.settle()
        self.assertEqual(STUBS.establish_calls, 2)
        self.assertTrue(self.coordinator.connected)

    async def test_backoff_grows_and_is_capped(self):
        delays = []
        for _ in range(10):
            before = time.monotonic()
            self.coordinator._async_register_failure(_ha_stubs.BleakError("x"))
            delays.append(round(self.coordinator._retry_at - before))
        self.assertEqual(delays[:4], [10, 20, 40, 80])
        self.assertEqual(max(delays), 300)

    async def test_handshake_failure_drops_connection_and_backs_off(self):
        STUBS.fail_next_writes = True
        await self.start()
        self.assertFalse(self.coordinator.connected)
        self.assertEqual(STUBS.clients[0].disconnect_calls, 1)
        self.assertGreater(self.coordinator._retry_at, time.monotonic())

    async def test_release_switch_disconnects_and_blocks_reconnect(self):
        await self.start()
        await self.coordinator.async_set_enabled(False)
        self.assertEqual(STUBS.clients[0].disconnect_calls, 1)
        self.assertFalse(self.coordinator.connected)
        self.advertise()
        await self.entry.settle()
        self.assertEqual(STUBS.establish_calls, 1)

    async def test_reenabling_reconnects_immediately(self):
        await self.start()
        await self.coordinator.async_set_enabled(False)
        await self.coordinator.async_set_enabled(True)
        await self.entry.settle()
        self.assertEqual(len(STUBS.clients), 2)
        self.assertTrue(self.coordinator.connected)

    async def test_disabled_before_start_never_connects(self):
        await self.coordinator.async_set_enabled(False)
        await self.start()
        self.assertEqual(STUBS.establish_calls, 0)

    async def test_shutdown_disconnects_and_stops_reconnecting(self):
        await self.start()
        await self.coordinator.async_shutdown()
        self.assertEqual(STUBS.clients[0].disconnect_calls, 1)
        self.advertise()
        await self.entry.settle()
        self.assertEqual(STUBS.establish_calls, 1)

    async def test_rapid_advertisements_open_one_connection(self):
        STUBS.device_present = False
        await self.start()
        STUBS.device_present = True
        for _ in range(5):
            self.advertise()
        await self.entry.settle()
        self.assertEqual(STUBS.establish_calls, 1)

    async def test_listener_removal(self):
        remove = self.coordinator.async_add_listener(lambda: None)
        remove()
        remove()  # idempotent


if __name__ == "__main__":
    unittest.main()
