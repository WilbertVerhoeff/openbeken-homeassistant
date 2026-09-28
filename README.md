# OpenBeken Home Assistant integration

A native Home Assistant custom integration for OpenBeken devices. It uses local TCP push communication and mDNS discovery; MQTT is not required.

## Requirements

The OpenBeken device firmware must include the `OpenBekenAPI` and `MDNS` drivers. Start them with `startDriver OpenBekenAPI` and `startDriver MDNS`, and add those commands to `autoexec.bat` to keep them enabled after reboot. The native API listens on TCP port 6054. If mDNS discovery is unavailable, add the device by IP address in Home Assistant.

The API currently has no authentication or TLS. Use it only on a trusted local network.

## Install with HACS

1. In HACS, open **Integrations** and select the three-dot menu.
2. Choose **Custom repositories** and add `https://github.com/WilbertVerhoeff/openbeken-homeassistant` as an **Integration**.
3. Find **OpenBeken**, download it, and restart Home Assistant.
4. Add the discovered OpenBeken device, or add it manually from **Settings → Devices & services → Add integration**.

## Manual installation

Copy `custom_components/openbeken` into the `custom_components` directory under your Home Assistant configuration directory, then restart Home Assistant. Add the OpenBeken integration from **Settings → Devices & services**.

## Entities and behavior

The integration exposes configured relays as switches; LED outputs as lights; read-only channels as sensors; motion and open/closed channels as binary sensors; and a restart button. Supported light features and sensor types depend on the device's firmware entity description. State changes are pushed over the persistent local connection, with automatic reconnection and state resynchronization.

See the [native API protocol documentation](https://github.com/openshwprojects/OpenBK7231T_App/blob/main/docs/openbekenNativeAPI.md) and [OpenBeken firmware documentation](https://github.com/openshwprojects/OpenBK7231T_App/blob/main/docs/homeAssistantNative.md).

## Diagnostics and changing the connection

In **Settings → Devices & services**, open the OpenBeken entry's menu and choose
**Reconfigure** to change its IP address/hostname and TCP port. The integration
checks the connection and device identity before saving, then reloads the entry.
Existing entity IDs, device assignments and automations are preserved. A different
device must be added separately. Failed connection checks leave the old settings intact.

Choose **Download diagnostics** from the same entry menu when reporting a problem.
The file includes cached connection status, firmware, entity capabilities and
counts. Hostnames/IP addresses, device identifiers and names are redacted.
Sensor readings, entity states and arbitrary device metadata are omitted.
Downloading does not send commands to the device and also works while disconnected.

## Connection problems and repairs

The setup, reconfiguration, command errors and repair notices are available in
English and Dutch, following your Home Assistant language settings. Device names
and entity names provided by firmware are preserved.

Connection errors distinguish unreachable devices, invalid native API responses,
unsupported API versions and mismatched device identities. Check the native API
port (default: 6054) and whether the `OpenBekenAPI` driver is running.

Confirmed unsupported API versions or changed device identities create an entry
in **Settings → System → Repairs** with instructions for correcting the address
or firmware. These require a manual change; they are not automatic repair flows.
Temporary network outages continue reconnecting without a repair notice. Notices
are removed after a successful connection or when the entry is removed. They are
scoped per device and do not persist across restarts unless detected again.

When a command times out, the device may already have acted on it. The error
therefore asks you to check its actual state before retrying.

## Issues

Please report integration-specific issues in the [issue tracker](https://github.com/WilbertVerhoeff/openbeken-homeassistant/issues).

## Development and tests

The test dependencies are pinned to Home Assistant **2026.9.4** through
`pytest-homeassistant-custom-component`. Use **Python 3.14** on Linux, preferably
in a virtual environment:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements_test.txt
ruff check tests
ruff format --check tests
python -m pytest -q
python -m coverage report --include=custom_components/openbeken/config_flow.py --fail-under=100
```

The suite uses real Home Assistant config flows, entries, entity/device registries,
and services. A local TCP device emulator exercises the actual protocol and push
connection without physical hardware. Focused tests inject failures and inspect
wire messages, metadata changes, timeouts, reconnects, resynchronization,
concurrent commands, cancellation, reload and unload.

Pytest enforces at least **95% coverage including branches**, with a 30-second
deadline per test. GitHub Actions also requires **100% config-flow coverage** and
checks test lint and formatting on every push and pull request. The XML coverage
report is available as an Actions artifact. This suite does not replace testing
on physical OpenBeken devices or real mDNS networks, and currently covers the
pinned Home Assistant version rather than a compatibility matrix.

The **Hassfest validation** workflow also checks the integration structure,
manifest and translation schemas with Home Assistant's official hassfest action
on every push and pull request. It can be run manually from GitHub Actions.
