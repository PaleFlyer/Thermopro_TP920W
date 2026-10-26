"""Minimal stand-ins for Home Assistant and Bleak so coordinator logic can be tested.

These encode assumptions about the framework API (checked by reading Home
Assistant core); they do not replace testing inside a real Home Assistant.
"""

import asyncio
import sys
import types


class BleakError(Exception):
    """Stand-in for bleak.exc.BleakError."""


class FakeGattClient:
    def __init__(self, disconnected_callback):
        self.disconnected_callback = disconnected_callback
        self.is_connected = True
        self.notify_callback = None
        self.writes = []
        self.disconnect_calls = 0
        self.fail_writes = False

    async def start_notify(self, char_specifier, callback):
        self.notify_callback = callback

    async def stop_notify(self, char_specifier):
        pass

    async def write_gatt_char(self, char_specifier, data, response=None):
        if self.fail_writes:
            raise BleakError("write failed")
        self.writes.append(bytes(data))
        await asyncio.sleep(0)

    async def disconnect(self):
        self.disconnect_calls += 1
        self.is_connected = False

    def drop(self):
        """Simulate the thermometer going away."""
        self.is_connected = False
        self.disconnected_callback(self)


class Stubs:
    """Mutable behaviour shared between the fake modules and the tests."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.device_present = True
        self.establish_calls = 0
        self.establish_script = []  # exceptions to raise, consumed in order
        self.fail_next_writes = False
        self.clients = []
        self.stale_closed = []
        self.advert_callback = None
        self.cancelled = False
        self.registered_matcher = None

    async def establish(self, client_class, device, name, disconnected_callback=None, **kwargs):
        self.establish_calls += 1
        await asyncio.sleep(0)
        if self.establish_script:
            outcome = self.establish_script.pop(0)
            if outcome is not None:
                raise outcome
        client = FakeGattClient(disconnected_callback)
        client.fail_writes = self.fail_next_writes
        self.clients.append(client)
        return client


def install() -> Stubs:
    stubs = Stubs()

    def module(name, **attrs):
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        sys.modules[name] = mod
        return mod

    bleak = module("bleak")
    bleak.exc = module("bleak.exc", BleakError=BleakError)

    async def close_stale(address):
        stubs.stale_closed.append(address)

    module(
        "bleak_retry_connector",
        BleakClientWithServiceCache=object,
        establish_connection=stubs.establish,
        close_stale_connections_by_address=close_stale,
    )

    def register_callback(hass, callback, matcher, mode):
        stubs.advert_callback = callback
        stubs.registered_matcher = matcher

        def cancel():
            stubs.cancelled = True

        return cancel

    def ble_device_from_address(hass, address, connectable=True):
        return object() if stubs.device_present else None

    homeassistant = module("homeassistant")
    components = module("homeassistant.components")
    bluetooth = module(
        "homeassistant.components.bluetooth",
        async_register_callback=register_callback,
        async_ble_device_from_address=ble_device_from_address,
        BluetoothScanningMode=types.SimpleNamespace(PASSIVE="passive", ACTIVE="active"),
        BluetoothServiceInfoBleak=object,
        BluetoothChange=object,
    )
    match = module(
        "homeassistant.components.bluetooth.match",
        ADDRESS="address",
        BluetoothCallbackMatcher=dict,
    )
    components.bluetooth = bluetooth
    bluetooth.match = match
    homeassistant.components = components

    class ConfigEntry:
        def __class_getitem__(cls, item):
            return cls

    module("homeassistant.config_entries", ConfigEntry=ConfigEntry)
    module(
        "homeassistant.core",
        HomeAssistant=object,
        callback=lambda func: func,
    )
    return stubs
