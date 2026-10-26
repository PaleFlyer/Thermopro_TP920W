"""Connection manager for the ThermoPro TP920."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import time

from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    close_stale_connections_by_address,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothScanningMode
from homeassistant.components.bluetooth.match import ADDRESS, BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, RETRY_BASE_SECONDS, RETRY_MAX_SECONDS
from .link import TP920Session
from .protocol import Reading

_LOGGER = logging.getLogger(__name__)

type TP920ConfigEntry = ConfigEntry[TP920Coordinator]


class TP920Coordinator:
    """Keep one connection to the thermometer and push readings to entities.

    The thermometer only talks to one Bluetooth client at a time, so the
    connection is opened when the device is seen advertising and can be
    released with ``async_set_enabled(False)`` to let the phone app in.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TP920ConfigEntry,
        address: str,
        fahrenheit_display: bool,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.address = address
        self.name = entry.title
        self.fahrenheit_display = fahrenheit_display
        self.data: Reading | None = None
        self.connected = False
        self.enabled = True
        self._client: BleakClientWithServiceCache | None = None
        self._session: TP920Session | None = None
        self._listeners: list[Callable[[], None]] = []
        self._connect_lock = asyncio.Lock()
        self._failures = 0
        self._retry_at = 0.0
        self._warned = False
        self._got_reading = False
        self._shutdown = False
        self._stale_closed = False

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        """Call ``update_callback`` whenever data or connection state changes."""
        self._listeners.append(update_callback)

        @callback
        def remove_listener() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove_listener

    @callback
    def async_start(self) -> Callable[[], None]:
        """Start watching for the device; returns a function that stops watching."""
        cancel = bluetooth.async_register_callback(
            self.hass,
            self._async_on_advertisement,
            BluetoothCallbackMatcher({ADDRESS: self.address}),
            BluetoothScanningMode.PASSIVE,
        )
        self._async_schedule_connect()
        return cancel

    async def async_shutdown(self) -> None:
        """Disconnect and stop reconnecting."""
        self._shutdown = True
        await self._async_drop_connection()

    async def async_set_enabled(self, enabled: bool) -> None:
        """Hold the connection (True) or release the thermometer (False)."""
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if enabled:
            self._failures = 0
            self._retry_at = 0.0
            self._async_schedule_connect()
            return
        await self._async_drop_connection()

    @callback
    def _async_notify(self) -> None:
        for update_callback in list(self._listeners):
            update_callback()

    @callback
    def _async_on_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        if (
            self._session is None
            and self.enabled
            and not self._shutdown
            and not self._connect_lock.locked()
            and time.monotonic() >= self._retry_at
        ):
            self._async_schedule_connect()

    @callback
    def _async_schedule_connect(self) -> None:
        self.entry.async_create_background_task(
            self.hass, self._async_connect(), f"{DOMAIN} connect {self.address}"
        )

    async def _async_connect(self) -> None:
        async with self._connect_lock:
            if (
                self._session is not None
                or not self.enabled
                or self._shutdown
                or time.monotonic() < self._retry_at
            ):
                return
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, True
            )
            if ble_device is None:
                return
            if not self._stale_closed:
                self._stale_closed = True
                await close_stale_connections_by_address(self.address)
            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self.name,
                    self._async_on_disconnect,
                    max_attempts=3,
                    ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                        self.hass, self.address, True
                    )
                    or ble_device,
                )
            except (BleakError, TimeoutError) as err:
                self._async_register_failure(err)
                return
            session = TP920Session(
                client,
                self._async_on_reading,
                fahrenheit_display=self.fahrenheit_display,
            )
            self._client = client
            self._session = session
            self._got_reading = False
            self.connected = True
            try:
                await session.async_start()
            except (BleakError, TimeoutError) as err:
                await self._async_drop_connection()
                self._async_register_failure(err)
                return
            _LOGGER.debug("Connected to %s", self.address)
            self._async_notify()

    @callback
    def _async_register_failure(self, err: Exception) -> None:
        self._failures += 1
        delay = min(RETRY_BASE_SECONDS * 2 ** (self._failures - 1), RETRY_MAX_SECONDS)
        self._retry_at = time.monotonic() + delay
        level = logging.DEBUG if self._warned else logging.WARNING
        self._warned = True
        _LOGGER.log(
            level,
            "Could not connect to %s (%s); retrying in %ss. Close the ThermoPro "
            "app and move a Bluetooth adapter or proxy closer if this repeats",
            self.address,
            err,
            delay,
        )

    @callback
    def _async_on_reading(self, reading: Reading) -> None:
        self._got_reading = True
        self._failures = 0
        self._warned = False
        self.data = reading
        self._async_notify()

    @callback
    def _async_on_disconnect(self, client: BleakClientWithServiceCache) -> None:
        if client is not self._client:
            return
        _LOGGER.debug("Disconnected from %s", self.address)
        session = self._session
        self._client = None
        self._session = None
        if session is not None:
            session.close()
        self.connected = False
        self.data = None
        if not self._got_reading:
            self._async_register_failure(
                BleakError("disconnected before any data was received")
            )
        self._async_notify()

    async def _async_drop_connection(self) -> None:
        client, session = self._client, self._session
        self._client = None
        self._session = None
        self.connected = False
        self.data = None
        if session is not None:
            await session.async_stop()
        if client is not None:
            try:
                await client.disconnect()
            except (BleakError, TimeoutError) as err:
                _LOGGER.debug("Error while disconnecting: %s", err)
        self._async_notify()
