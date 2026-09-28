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

## Issues

Please report integration-specific issues in the [issue tracker](https://github.com/WilbertVerhoeff/openbeken-homeassistant/issues).
