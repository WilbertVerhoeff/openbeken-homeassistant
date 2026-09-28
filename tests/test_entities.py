"""Entity behavior tested through HA states, registries, and service calls."""

from copy import deepcopy
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openbeken.const import DOMAIN

from .conftest import ENTITIES, NORMALIZED_ID, DeviceEmulator
from .helpers import has_state, wait_until


@pytest.mark.parametrize(
    ("entity_id", "expected"),
    [
        ("light.test_device_light", "on"),
        ("switch.test_device_relay", "off"),
        ("sensor.test_device_temperature", "21.5"),
        ("binary_sensor.test_device_motion", "on"),
        ("button.test_device_restart", "unknown"),
    ],
)
async def test_initial_states(
    hass: HomeAssistant, setup_entry: MockConfigEntry, entity_id: str, expected: str
) -> None:
    assert has_state(hass, entity_id, expected)
    assert setup_entry.state is ConfigEntryState.LOADED


async def test_entity_and_device_registry(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    registry = er.async_get(hass)
    entity = registry.async_get("light.test_device_light")
    assert entity is not None
    assert entity.unique_id == f"{NORMALIZED_ID}_light_0"
    assert entity.config_entry_id == setup_entry.entry_id
    device = dr.async_get(hass).async_get(entity.device_id)
    assert device is not None
    assert device.identifiers == {(DOMAIN, NORMALIZED_ID)}
    assert device.manufacturer == "OpenBeken"
    assert device.sw_version == "1.18.100"
    assert device.configuration_url == "http://127.0.0.1"


async def test_light_attributes(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    attrs = hass.states.get("light.test_device_light").attributes
    assert attrs["brightness"] == 128
    assert attrs["rgb_color"] == (255, 0, 0)
    assert attrs["effect_list"] == ["off", "Rainbow", "Fire"]
    assert attrs["effect"] == "off"
    assert set(attrs["supported_color_modes"]) == {"rgb", "color_temp"}
    assert attrs["min_color_temp_kelvin"] == 2000
    assert attrs["max_color_temp_kelvin"] == 6536


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"brightness": 200}, {"on": True, "brightness": 200}),
        ({"rgb_color": [1, 2, 3]}, {"on": True, "rgb": [1, 2, 3], "mode": "rgb"}),
        ({"color_temp_kelvin": 4000}, {"on": True, "color_temp": 250, "mode": "white"}),
        ({"effect": "Rainbow"}, {"on": True, "effect": "Rainbow", "mode": "effect"}),
        ({"effect": "off"}, {"on": True, "mode": "rgb"}),
    ],
)
async def test_light_turn_on(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    device: DeviceEmulator,
    data: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.test_device_light", **data},
        blocking=True,
    )
    command = await device.next_command("set_state")
    assert command["entity"] == "light_0"
    assert command["state"] == expected


async def test_light_turn_off(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": "light.test_device_light"}, blocking=True
    )
    command = await device.next_command("set_state")
    assert command["state"] == {"on": False}
    await wait_until(lambda: has_state(hass, "light.test_device_light", "off"))


@pytest.mark.parametrize(
    ("service", "expected"), [("turn_on", True), ("turn_off", False)]
)
async def test_switch_commands(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    device: DeviceEmulator,
    service: str,
    expected: bool,
) -> None:
    await hass.services.async_call(
        "switch", service, {"entity_id": "switch.test_device_relay"}, blocking=True
    )
    command = await device.next_command("set_state")
    assert command["entity"] == "relay_1"
    assert command["state"] == {"on": expected}


async def test_restart(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.test_device_restart"}, blocking=True
    )
    assert (await device.next_command("restart"))["id"] > 0


async def test_sensor_attributes(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    attrs = hass.states.get("sensor.test_device_temperature").attributes
    assert attrs["unit_of_measurement"] == "°C"
    assert attrs["device_class"] == "temperature"
    assert attrs["state_class"] == "measurement"
    assert (
        hass.states.get("binary_sensor.test_device_motion").attributes["device_class"]
        == "motion"
    )


async def test_push_updates(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    await device.push(
        {
            "type": "state_changed",
            "seq": 1,
            "entity": "temp_2",
            "state": {"value": 24.2},
        }
    )
    await wait_until(lambda: has_state(hass, "sensor.test_device_temperature", "24.2"))
    await device.push(
        {
            "type": "state_changed",
            "seq": 2,
            "entity": "motion_3",
            "state": {"on": False},
        }
    )
    await wait_until(lambda: has_state(hass, "binary_sensor.test_device_motion", "off"))


async def test_dynamic_entities_preserve_identity(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    registry = er.async_get(hass)
    original_id = registry.async_get("sensor.test_device_temperature").id
    device.entities = [item for item in device.entities if item["id"] != "temp_2"]
    await device.push({"type": "entities", "entities": device.entities})
    await wait_until(
        lambda: has_state(hass, "sensor.test_device_temperature", "unavailable")
    )
    device.entities.append(deepcopy(ENTITIES[2]))
    device.entities.append(
        {
            "id": "humidity_4",
            "platform": "sensor",
            "name": "Humidity",
            "unit": "%",
            "device_class": "humidity",
            "state_class": "measurement",
        }
    )
    device.states["humidity_4"] = {"value": 45}
    await device.push({"type": "entities", "entities": device.entities})
    await device.push(device.snapshot())
    await wait_until(lambda: has_state(hass, "sensor.test_device_humidity", "45"))
    await wait_until(lambda: has_state(hass, "sensor.test_device_temperature", "21.5"))
    assert registry.async_get("sensor.test_device_temperature").id == original_id
    assert len(hass.states.async_all("sensor")) == 2


async def test_dynamic_metadata(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    device.entities[0]["effects"] = ["New effect"]
    device.entities[0]["min_mireds"] = 200
    await device.push(
        {
            "type": "entities",
            "entities": device.entities,
            "device": {"name": "Updated device", "firmware": "2.0"},
        }
    )
    await wait_until(
        lambda: (
            hass.states.get("light.test_device_light").attributes["effect_list"]
            == ["off", "New effect"]
        )
    )
    assert (
        hass.states.get("light.test_device_light").attributes["max_color_temp_kelvin"]
        == 5000
    )
    entity = er.async_get(hass).async_get("light.test_device_light")
    device_entry = dr.async_get(hass).async_get(entity.device_id)
    assert device_entry.name == "Updated device"
    assert device_entry.sw_version == "2.0"


async def test_disconnect_unavailable(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    device.server.close()
    await device.disconnect()
    await device.server.wait_closed()
    await wait_until(lambda: has_state(hass, "light.test_device_light", "unavailable"))
    assert has_state(hass, "button.test_device_restart", "unavailable")


async def test_reload_and_unload(
    hass: HomeAssistant, entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(hass.states.async_all()) == 5
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await wait_until(lambda: not device.writers)
    assert entry.state is ConfigEntryState.NOT_LOADED
    # HA keeps registry placeholders after unload; they must be unavailable.
    assert all(state.state == "unavailable" for state in hass.states.async_all())
    assert DOMAIN not in hass.data
