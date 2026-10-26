"""One GATT session with the thermometer. No Home Assistant imports."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone
import logging
from typing import Any, Protocol

from .protocol import (
    ACK,
    COMMAND_UUID,
    NOTIFY_UUID,
    Reading,
    handshake,
    parse_notification,
)

_LOGGER = logging.getLogger(__name__)

SUBSCRIBE_SETTLE = 0.5
STEP_DELAY = 0.25


class GattClient(Protocol):
    """The slice of BleakClient that a session uses."""

    @property
    def is_connected(self) -> bool: ...

    async def start_notify(self, char_specifier: str, callback: Any) -> None: ...

    async def stop_notify(self, char_specifier: str) -> None: ...

    async def write_gatt_char(
        self, char_specifier: str, data: bytes, response: bool = ...
    ) -> None: ...


class TP920Session:
    """Subscribe, replay the app's handshake, then ack every telemetry frame."""

    def __init__(
        self,
        client: GattClient,
        on_reading: Callable[[Reading], None],
        *,
        fahrenheit_display: bool = True,
        clock: Callable[[], datetime] | None = None,
        settle: float = SUBSCRIBE_SETTLE,
        step_delay: float = STEP_DELAY,
    ) -> None:
        self._client = client
        self._on_reading = on_reading
        self._fahrenheit_display = fahrenheit_display
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._settle = settle
        self._step_delay = step_delay
        self._write_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()
        self._closed = False

    async def async_start(self) -> None:
        """Subscribe to telemetry and run the startup handshake."""
        await self._client.start_notify(NOTIFY_UUID, self._on_notification)
        await asyncio.sleep(self._settle)
        for command in handshake(self._clock(), self._fahrenheit_display):
            await self._write(command)
            await asyncio.sleep(self._step_delay)

    def close(self) -> None:
        """Stop reacting to frames and cancel pending acks."""
        self._closed = True
        for task in list(self._tasks):
            task.cancel()

    async def async_stop(self) -> None:
        """Close the session and unsubscribe if the link is still up."""
        self.close()
        if self._client.is_connected:
            with suppress(Exception):
                await self._client.stop_notify(NOTIFY_UUID)

    def _on_notification(self, _characteristic: Any, data: bytearray) -> None:
        if self._closed:
            return
        _LOGGER.debug("Notification %s", bytes(data).hex())
        reading = parse_notification(data)
        if reading is None:
            return
        self._on_reading(reading)
        task = asyncio.get_running_loop().create_task(self._async_ack())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _async_ack(self) -> None:
        try:
            await self._write(ACK)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Ack write failed: %s", err)

    async def _write(self, data: bytes) -> None:
        async with self._write_lock:
            await self._client.write_gatt_char(COMMAND_UUID, data, response=True)
