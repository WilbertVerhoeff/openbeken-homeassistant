"""Entry failure, cleanup and listener tests using HA's entry manager."""

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openbeken import async_unload_entry
from custom_components.openbeken.const import DOMAIN, PLATFORMS

from .conftest import DeviceEmulator


async def test_failed_setup_is_retried(
    hass: HomeAssistant, entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    device.hello["protocol"] = 2
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert DOMAIN not in hass.data
    assert not hass.states.async_all()
    device.hello["protocol"] = 1
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert len(hass.states.async_all()) == 5


async def test_unload_platform_failure_keeps_connection(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    with patch.object(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)
    ) as unload:
        assert not await async_unload_entry(hass, setup_entry)
    unload.assert_awaited_once_with(setup_entry, PLATFORMS)
    assert hass.data[DOMAIN][setup_entry.entry_id] is coordinator
    assert coordinator.connected


async def test_unload_one_of_two_entries_preserves_other(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    sentinel = object()
    hass.data[DOMAIN]["other_entry"] = sentinel
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    assert hass.data[DOMAIN] == {"other_entry": sentinel}
    hass.data[DOMAIN].pop("other_entry")
