# TP920W Bluetooth protocol notes

Reverse engineered from an Android HCI snoop capture of the official ThermoPro BBQ app talking to a
TP920W (advertises as `Thermopro`). Everything below was observed unless marked *inferred*.

## GATT

| UUID | Properties | Use |
|---|---|---|
| `1086fff0-3343-4817-8bb2-b32206336ce8` | service | |
| `1086fff1-…` | READ, WRITE | commands to the thermometer (write with response) |
| `1086fff2-…` | NOTIFY, READ | frames from the thermometer |

The device is not bonded; connecting and enabling notifications is all the "pairing" there is.
It accepts one client at a time. Notifications are always 20 bytes; bytes after the payload and
checksum are stale buffer content.

## Frame format (both directions)

```
[cmd:1][length:1][payload:length][checksum:1]    checksum = sum(previous bytes) mod 256
```

## Startup sequence (after enabling notifications on `fff2`, one write at a time)

| Write to `fff1` | Meaning |
|---|---|
| `01 09 <9 bytes> <sum>` | Login. Payload `8a7a13b73ed68b67c2` was captured from one phone and replayed unchanged from another client with success. |
| `41 00 41` | Info request (reply starts `41 03 …`). |
| `28 04 <u32 big endian> <sum>` | Clock: seconds since 2020-01-01 00:00 **UTC+8**. Verified against the capture's absolute timestamp to within 1 s. |
| `20 01 <0f|0c> <sum>` | Display unit, `0f` = °F (observed), `0c` = °C (*inferred*, matches the flag in telemetry). |

The first telemetry frame arrives shortly after the unit write.

## Telemetry (`cmd 0x30`), sent only when a value changes

```
idx  0   30         type
     1   0f         payload length (15)
     2   61         battery %
     3   0f / 0c    display unit flag (°F / °C)
     4   00
   5-6   ff ff      not decoded (unset on every sample)
   7-8   02 27      probe 1: 4 BCD digits, tenths of °C  -> 22.7 °C   (ff ff = unplugged)
  9-10   ff ff      not decoded
 11-12   03 73      probe 2: -> 37.3 °C
 13-16   ff ff ff ff
    17   46         checksum of bytes 0-16
 18-19   01 40      constant padding observed
```

Probe values are **always °C on the wire**, regardless of display mode. Byte 3 only mirrors the unit shown on the thermometer (confirmed on hardware: changing the mode flips just that flag, not the temperature encoding), so the app can tell the hardware changed modes.

After **every** telemetry frame the app writes `30 00 30` (an acknowledgement) 10-30 ms later.
It is not known whether the unit stops streaming without it; this integration always sends it.

## Other frames seen, not used

* `23 06 02|04 00 ff ff ff ff <sum>`: written by the app at startup, looks like alarm-threshold
  clearing for each probe; the unit replies with `23 02 …` frames.
* Unit replies `01 02 0a 02 0f …` (login), `41 03 29 11 02 80 …` (info), `28 04 …` (clock echo),
  `20 00 20 …` (unit).

## Unknowns

* Whether the login payload is per-phone or accepted from anyone.
* Encoding of temperatures below 0 °C.
* Meaning of bytes 5-6 and 9-10 (probably per-probe alarm targets).
* Whether other ThermoPro models (TP90x, TP93x) use the same service.
