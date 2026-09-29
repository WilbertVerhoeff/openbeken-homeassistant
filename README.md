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

## Report an issue

Having a problem? [Open an issue](https://github.com/WilbertVerhoeff/openbeken-homeassistant/issues/new) with a short description and these files:

1. In Home Assistant, go to **Settings → Devices & services → OpenBeken**.
2. Open the **⋮** menu at the top right and select **Enable debug logging**.
3. Reproduce the problem, then select **Disable debug logging** from the same menu and save the downloaded log.
4. Open the affected device's integration entry **⋮** menu and select **Download diagnostics**.
5. Attach the log and diagnostics to your issue. Include your Home Assistant version, integration version, OpenBeken firmware version and device model, plus the steps to reproduce the problem, what you expected and what happened.

Diagnostics redact device addresses and names. Debug logs may contain personal information; check them before uploading. If logging or diagnostics are unavailable, report the issue with the information you have.
