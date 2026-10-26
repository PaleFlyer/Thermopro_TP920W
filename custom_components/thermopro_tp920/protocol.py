"""Wire protocol for the ThermoPro TP920(W) dual-probe BLE thermometer.

Reverse engineered from a Bluetooth HCI capture of the official ThermoPro BBQ
app. This module is deliberately free of Home Assistant and Bleak imports so it
can be unit tested on its own.

Frame format (both directions)::

    [cmd:1][length:1][payload:length][checksum:1]

``checksum`` is the sum of all preceding bytes modulo 256. Notifications from
the thermometer are always padded to 20 bytes; the padding is stale buffer
content and is ignored.

Only the pieces needed to read temperatures are implemented. Alarm/target
commands (cmd 0x23) are seen in the capture but are not used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SERVICE_UUID = "1086fff0-3343-4817-8bb2-b32206336ce8"
COMMAND_UUID = "1086fff1-3343-4817-8bb2-b32206336ce8"  # READ, WRITE
NOTIFY_UUID = "1086fff2-3343-4817-8bb2-b32206336ce8"  # NOTIFY, READ

CMD_LOGIN = 0x01
CMD_UNIT = 0x20
CMD_TIME = 0x28
CMD_TELEMETRY = 0x30  # device -> host temperature frame; host -> device ack
CMD_INFO = 0x41

# Payload of the first write the official app sends after subscribing. It was
# captured from one phone and replayed verbatim from an ESP32 and the unit
# streamed normally, so the thermometer does not appear to bind it to a
# particular phone. If a unit ever refuses to stream, this is the first thing
# to suspect.
LOGIN_PAYLOAD = bytes.fromhex("8a7a13b73ed68b67c2")

# Seconds-since-2020-01-01 clock, expressed in UTC+8 (verified against the
# absolute timestamp of the captured write to within one second).
_CLOCK_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)
_CLOCK_OFFSET = timedelta(hours=8)

UNIT_FAHRENHEIT = 0x0F
UNIT_CELSIUS = 0x0C

# Offsets into a telemetry notification (index into the whole frame).
_BATTERY = 2
_UNIT = 3
_PROBE1 = (7, 8)
_PROBE2 = (11, 12)
_MIN_PAYLOAD_LENGTH = 11  # must cover the highest offset above (12 - 2 + 1)


def checksum(data: bytes) -> int:
    """Return the protocol checksum (sum of bytes mod 256)."""
    return sum(data) & 0xFF


def build_command(cmd: int, payload: bytes = b"") -> bytes:
    """Frame a command: [cmd][len][payload][checksum]."""
    body = bytes([cmd, len(payload)]) + payload
    return body + bytes([checksum(body)])


ACK = build_command(CMD_TELEMETRY)  # 30 00 30, sent after every telemetry frame
INFO_REQUEST = build_command(CMD_INFO)  # 41 00 41


def login_command() -> bytes:
    return build_command(CMD_LOGIN, LOGIN_PAYLOAD)


def time_command(now: datetime) -> bytes:
    """Clock-set command for ``now`` (any timezone-aware datetime)."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    seconds = int((now.astimezone(timezone.utc) + _CLOCK_OFFSET - _CLOCK_EPOCH).total_seconds())
    return build_command(CMD_TIME, seconds.to_bytes(4, "big"))


def unit_command(fahrenheit: bool) -> bytes:
    """Set the unit shown on the thermometer's own display.

    The Fahrenheit form is verbatim from the capture. The Celsius form follows
    the same pattern (payload equals the unit flag seen in telemetry) but has
    not been captured from the app.
    """
    return build_command(CMD_UNIT, bytes([UNIT_FAHRENHEIT if fahrenheit else UNIT_CELSIUS]))


def handshake(now: datetime, fahrenheit: bool = True) -> list[bytes]:
    """Commands the app sends after subscribing, in order."""
    return [login_command(), INFO_REQUEST, time_command(now), unit_command(fahrenheit)]


@dataclass(frozen=True)
class Reading:
    """One decoded telemetry frame. Temperatures are in °C; None = no probe."""

    battery: int
    fahrenheit_display: bool
    probe1: float | None
    probe2: float | None


def _decode_probe(hi: int, lo: int) -> float | None:
    """Decode a probe temperature: four BCD digits, tenths of °C.

    ``ff ff`` means no probe is plugged in. Anything that is not valid BCD is
    treated as unknown (sub-zero encodings have not been observed).
    """
    if hi == 0xFF and lo == 0xFF:
        return None
    nibbles = (hi >> 4, hi & 0xF, lo >> 4, lo & 0xF)
    if any(n > 9 for n in nibbles):
        return None
    return (nibbles[0] * 1000 + nibbles[1] * 100 + nibbles[2] * 10 + nibbles[3]) / 10


def parse_notification(data: bytes | bytearray) -> Reading | None:
    """Decode a telemetry notification, or return None for anything else.

    Returns None for other frame types, truncated frames and checksum failures.
    """
    if len(data) < 4 or data[0] != CMD_TELEMETRY:
        return None
    end = 2 + data[1]
    if data[1] < _MIN_PAYLOAD_LENGTH or len(data) <= end:
        return None
    if checksum(bytes(data[:end])) != data[end]:
        return None
    return Reading(
        battery=data[_BATTERY],
        fahrenheit_display=data[_UNIT] == UNIT_FAHRENHEIT,
        probe1=_decode_probe(data[_PROBE1[0]], data[_PROBE1[1]]),
        probe2=_decode_probe(data[_PROBE2[0]], data[_PROBE2[1]]),
    )
