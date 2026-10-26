# ThermoPro TP920 (Bluetooth) for Home Assistant

Local, cloud-free temperatures from a ThermoPro / TempPro **TP920W** dual-probe
Bluetooth thermometer, using **any Bluetooth adapter or ESPHome Bluetooth proxy
that Home Assistant already has**. No dedicated ESP32 firmware is needed.

The TP920W is not a broadcast sensor, so the built-in ThermoPro integration cannot
read it. It only streams temperatures to whoever connects, subscribes and replays
the official app's startup handshake. This integration does exactly that, using
Home Assistant's own Bluetooth stack, and reconnects by itself whenever the
thermometer is switched on and in range. **It may work with other devices that use
ThermoPro app. However only the TP920W is tested.

> **Status: early / unverified in a live Home Assistant.** The protocol was
> reverse engineered from a real TP920W and the byte-level code is unit tested
> against that capture. The Home Assistant glue was written against Home
> Assistant core's current sources and logic-tested with stubs, but has not yet
> run inside a real Home Assistant. Expect to iterate; please open issues.

## Entities

| Entity | Notes |
|---|---|
| `sensor` **Probe 1**, **Probe 2** | °C natively (Home Assistant shows your unit system), 0.1° resolution. The thermometer's own screen only shows whole degrees. Unknown when a probe is unplugged. |
| `sensor` **Battery** | Diagnostic, %. |
| `binary_sensor` **Connected** | Diagnostic. Always available, so it works in automations. |
| `switch` **Bluetooth connection** | Turn **off** to release the thermometer so the phone app can connect. |

Entity IDs are built from the device name, which defaults to `ThermoPro TP920 <last 4 hex of the MAC>`,
for example `sensor.thermopro_tp920_adb7_probe_1`. Probes are not labelled "meat" or "ambient"
because the app lets you assign either role to either probe.

## Important: one connection at a time

The thermometer accepts a single Bluetooth client. While Home Assistant is connected,
the ThermoPro app cannot connect, and the other way round. Use the **Bluetooth connection**
switch (or power-cycle the thermometer) to hand it over.

If you previously set up an ESPHome `ble_client` for this thermometer, **remove it**,
otherwise the ESP32 holds the connection and Home Assistant can never connect.
Keep only `bluetooth_proxy:` on that ESP32.

## Install

**HACS (custom repository)**

1. HACS → ⋮ → *Custom repositories* → add this repository, category *Integration*.
2. Install **ThermoPro TP920 (Bluetooth, connected)** and restart Home Assistant.

**Manual**: copy `custom_components/thermopro_tp920` into your `config/custom_components/` folder
(on Home Assistant OS that is `/homeassistant/custom_components/`) and restart.

## Set up

1. Close the ThermoPro app, then switch the thermometer on near a Bluetooth adapter or proxy.
2. It should appear under *Settings → Devices & services → Discovered*. Otherwise choose
   *Add integration → ThermoPro TP920*.
3. Within a few seconds the sensors should start updating.

Options (*Configure* on the integration): whether the thermometer's own display shows °F or °C.
This is sent on each connect, like the app does.

## Cook logic (ETA, stall and flameout alerts)

`examples/cook_logic.yaml` is a Home Assistant *package* that builds on these sensors: a target
temperature helper, two ETA estimates, "done at" time, flameout and stall detection, and phone
notifications. Copy it to `config/packages/` after enabling packages:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Edit the three marked placeholders (the two probe entity IDs and your `person.` entity).

## Troubleshooting

* **Nothing found when adding**: the thermometer must be on and advertising, not connected to
  the phone app, and within range of a *connectable* adapter or proxy.
* **"Could not connect" warnings**: close the app, move the adapter/proxy within a few metres,
  and check the proxy has a free connection slot. Retries back off from 10 s up to 5 min.
* **Connects but no data**: enable debug logging for `custom_components.thermopro_tp920` and
  open an issue with the log. The startup handshake includes a login payload captured from one
  phone (see `docs/PROTOCOL.md`); if a unit rejects it, that is the first suspect.
* **Sub-zero probe readings** are reported as unknown: the encoding for negative values has not
  been observed.
* On one ESP32-C6 proxy, connections failed (`status=133`) until a custom
  `CONFIG_BT_BLE_50_FEATURES_SUPPORTED` sdkconfig option was removed from its ESPHome config.

## Development

The protocol and connection logic have no Home Assistant dependency in `protocol.py` and
`link.py`, so tests run anywhere:

```
python3 -m unittest discover -s tests -v
```

## Credits and disclaimer

Not affiliated with or endorsed by ThermoPro / TempPro. Protocol details were worked out by
capturing the official app's Bluetooth traffic from the author's own thermometer.
