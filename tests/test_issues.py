"""Confirmed incompatibilities need action; temporary outages do not."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openbeken.const import DOMAIN
from custom_components.openbeken.errors import (
    DeviceIdentityError,
    InvalidResponseError,
    UnsupportedProtocolError,
)
from custom_components.openbeken.issues import async_report_connection_issue

from .conftest import DEVICE_ID, DeviceEmulator
from .helpers import wait_until


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"protocol": 2}, "unsupported_protocol"),
        ({"device_id": "other"}, "wrong_device"),
    ],
)
async def test_initial_failure_creates_and_recovery_clears_issue(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    device: DeviceEmulator,
    changes: dict,
    reason: str,
) -> None:
    registry = ir.async_get(hass)
    device.hello.update(changes)
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    issue_id = f"connection_{entry.entry_id}"
    issue = registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == reason
    assert issue.translation_placeholders == {"name": "Test device"}
    assert issue.severity is ir.IssueSeverity.ERROR
    assert not issue.is_fixable
    assert not issue.is_persistent
    assert issue.learn_more_url.endswith("#connection-problems-and-repairs")
    assert not await hass.config_entries.async_reload(entry.entry_id)
    assert len([key for key in registry.issues if key[0] == DOMAIN]) == 1
    device.hello.update({"protocol": 1, "device_id": DEVICE_ID})
    assert await hass.config_entries.async_reload(entry.entry_id)
    assert registry.async_get_issue(DOMAIN, issue_id) is None


@pytest.mark.parametrize(
    "error",
    [
        OSError("offline"),
        TimeoutError(),
        InvalidResponseError("malformed"),
        ValueError("bad"),
    ],
)
async def test_transient_failure_does_not_raise_repair(
    hass: HomeAssistant, entry: MockConfigEntry, error: Exception
) -> None:
    async_report_connection_issue(hass, entry, error)
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"connection_{entry.entry_id}")
        is None
    )


async def test_remove_entry_clears_only_its_issue(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    other = MockConfigEntry(
        domain=DOMAIN, title="Other device", data={"host": "other.local"}
    )
    other.add_to_hass(hass)
    async_report_connection_issue(hass, entry, UnsupportedProtocolError())
    async_report_connection_issue(hass, other, DeviceIdentityError())
    assert await hass.config_entries.async_remove(entry.entry_id)
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, f"connection_{entry.entry_id}") is None
    assert registry.async_get_issue(DOMAIN, f"connection_{other.entry_id}") is not None


async def test_reconnect_identity_change_raises_repair(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    registry = ir.async_get(hass)
    issue_id = f"connection_{setup_entry.entry_id}"
    device.hello["device_id"] = "other"
    await device.disconnect()
    await wait_until(lambda: registry.async_get_issue(DOMAIN, issue_id) is not None)
    assert registry.async_get_issue(DOMAIN, issue_id).translation_key == "wrong_device"
    assert not hass.data[DOMAIN][setup_entry.entry_id].connected
    device.hello["device_id"] = DEVICE_ID
    assert await hass.config_entries.async_reload(setup_entry.entry_id)
    assert registry.async_get_issue(DOMAIN, issue_id) is None
