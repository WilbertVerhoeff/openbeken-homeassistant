"""Verify the HA download endpoint, privacy, and unloaded-entry behavior."""

import json
from unittest.mock import AsyncMock, patch

from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.openbeken.const import DOMAIN
from custom_components.openbeken.diagnostics import async_get_config_entry_diagnostics

from .conftest import DEVICE_ID, NORMALIZED_ID


async def test_diagnostics_download(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    setup_entry: MockConfigEntry,
) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    with patch.object(coordinator, "_send", AsyncMock()) as send:
        data = await get_diagnostics_for_config_entry(hass, hass_client, setup_entry)
    send.assert_not_awaited()
    assert data["config_entry"]["unique_id"] == REDACTED
    assert data["config_entry"]["data"] == {
        "host": REDACTED,
        "port": setup_entry.data["port"],
        "name": REDACTED,
        "device_id": REDACTED,
    }
    runtime = data["runtime"]
    assert runtime["connected"] is True
    assert runtime["last_update_success"] is True
    assert runtime["firmware"] == "1.18.100"
    assert runtime["protocol"] == 1
    assert runtime["entity_count"] == 5
    assert runtime["state_count"] == 4
    assert {item["platform"] for item in runtime["entities"]} == {
        "light",
        "switch",
        "sensor",
        "binary_sensor",
        "button",
    }
    assert sum(item["has_state"] for item in runtime["entities"]) == 4
    encoded = json.dumps(data)
    for sensitive in [
        DEVICE_ID,
        NORMALIZED_ID,
        "127.0.0.1",
        "Test device",
        "light_0",
        "temp_2",
    ]:
        assert sensitive not in encoded
    assert all(
        "value" not in item and "name" not in item for item in runtime["entities"]
    )


async def test_diagnostics_snapshot_is_independent(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    coordinator.entities["light_0"]["secret"] = "private"
    coordinator.states["temp_2"]["value"] = "private reading"
    hass.config_entries.async_update_entry(
        setup_entry, data=dict(setup_entry.data) | {"password": "secret password"}
    )
    data = await async_get_config_entry_diagnostics(hass, setup_entry)
    assert "private" not in json.dumps(data)
    assert "password" not in json.dumps(data)
    data["runtime"]["entities"][0]["features"].clear()
    assert coordinator.entities["light_0"]["features"]
    assert setup_entry.data["host"] == "127.0.0.1"


async def test_diagnostics_disconnected(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    await coordinator.async_shutdown()
    data = await async_get_config_entry_diagnostics(hass, setup_entry)
    assert data["runtime"]["connected"] is False
    assert data["runtime"]["entity_count"] == 5


async def test_diagnostics_unloaded(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data["runtime"] is None
    assert data["config_entry"]["data"]["device_id"] == REDACTED
    hass.data[DOMAIN] = {}
    assert await async_get_config_entry_diagnostics(hass, entry) == data
