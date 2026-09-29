# OpenBeken Home Assistant integration

A native Home Assistant custom integration for OpenBeken devices. It uses local TCP push communication and mDNS discovery.

The current [integration beta release](https://github.com/WilbertVerhoeff/openbeken-homeassistant/releases/tag/0.1.1-beta.1) supports Native API protocol 1. Install it through HACS or copy the integration files as described below.

## Requirements

The OpenBeken device firmware must include the `OpenBekenAPI` driver. Start it with `startDriver OpenBekenAPI`. For automatic discovery, also run `startDriver MDNS`. Add these commands to `autoexec.bat` to keep them enabled after reboot. The native API listens on TCP port 6054. Without mDNS, add the device by IP address in Home Assistant.

The API currently has no authentication or TLS. Use it only on a trusted local network.

## Firmware beta

The first [Native HA API firmware beta](https://github.com/WilbertVerhoeff/OpenBK7231T_App/releases/tag/ha-api-v0.1.0-beta.1) is available from the OpenBeken fork. Download the `.rbl` file for your device's chipset:

- [BK7231N](https://github.com/WilbertVerhoeff/OpenBK7231T_App/releases/download/ha-api-v0.1.0-beta.1/OpenBK7231N_ha_api_3b979180.rbl) — checked on LSC Smart Panel Lights with a BK7231N chip, RGB, warm and cool white, and an IR remote.
- [BK7231T](https://github.com/WilbertVerhoeff/OpenBK7231T_App/releases/download/ha-api-v0.1.0-beta.1/OpenBK7231T_ha_api_3b979180.rbl) — build checked. Hardware operation has not yet been checked.

The firmware contains no device-specific pin or template configuration. Keep using OpenBeken's device configuration for those settings. Release notes list checksums, activation steps and beta limitations.

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

Diagnostics redact device addresses and names. Debug logs may contain personal information. Check them before uploading. If logging or diagnostics are unavailable, report the issue with the information you have.
