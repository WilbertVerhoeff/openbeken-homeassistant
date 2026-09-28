"""Cover advertised light capabilities and native API value conversion."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.light import (
    DEFAULT_MAX_KELVIN,
    DEFAULT_MIN_KELVIN,
    ColorMode,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openbeken.coordinator import OpenBekenCoordinator
from custom_components.openbeken.light import OpenBekenLight

from .conftest import DEVICE_ID, ENTITIES, DeviceEmulator


@pytest.fixture
def light(hass: HomeAssistant, entry: MockConfigEntry) -> OpenBekenLight:
    coordinator = OpenBekenCoordinator(
        hass, entry, "127.0.0.1", entry.data["port"], "Test device", DEVICE_ID
    )
    return OpenBekenLight(coordinator, deepcopy(ENTITIES[0]))


@pytest.mark.parametrize(
    ("features", "supported", "mode", "expected"),
    [
        (["brightness"], {ColorMode.BRIGHTNESS}, None, ColorMode.BRIGHTNESS),
        (
            ["rgb", "white_level"],
            {ColorMode.RGB, ColorMode.WHITE},
            "white",
            ColorMode.WHITE,
        ),
        (["rgb"], {ColorMode.RGB}, "rgb", ColorMode.RGB),
        (["color_temp"], {ColorMode.COLOR_TEMP}, "white", ColorMode.COLOR_TEMP),
        (
            ["brightness", "effects"],
            {ColorMode.BRIGHTNESS},
            "effect",
            ColorMode.BRIGHTNESS,
        ),
        (["rgb", "effects"], {ColorMode.RGB}, "effect", ColorMode.RGB),
        (["rgb"], {ColorMode.RGB}, "unsupported", ColorMode.RGB),
        ([], {ColorMode.BRIGHTNESS}, None, ColorMode.BRIGHTNESS),
    ],
)
def test_capabilities(
    light: OpenBekenLight,
    features: list[str],
    supported: set[ColorMode],
    mode: str | None,
    expected: ColorMode,
) -> None:
    light._apply_description(deepcopy(ENTITIES[0]) | {"features": features})
    light.coordinator.states[light.obk_id] = {"mode": mode}
    assert light.supported_color_modes == supported
    assert light.color_mode is expected
    if "effects" not in features:
        assert light.effect is None
        assert light.effect_list is None
        assert light.supported_features == 0
    if "color_temp" not in features:
        assert light.min_color_temp_kelvin == DEFAULT_MIN_KELVIN
        assert light.max_color_temp_kelvin == DEFAULT_MAX_KELVIN


@pytest.mark.parametrize("rgb", [None, [], [1, 2], [1, 2, 3, 4], "red", (1, 2, 3)])
def test_invalid_rgb_returns_none(light: OpenBekenLight, rgb: object) -> None:
    light.coordinator.states[light.obk_id] = {"rgb": rgb}
    assert light.rgb_color is None


@pytest.mark.parametrize("mireds", [None, 0])
def test_absent_temperature(light: OpenBekenLight, mireds: int | None) -> None:
    light.coordinator.states[light.obk_id] = {"color_temp": mireds}
    assert light.color_temp_kelvin is None


@pytest.mark.parametrize(
    ("features", "kwargs", "expected"),
    [
        (
            ["brightness", "white_level", "rgb"],
            {"brightness": 200, "white": 100},
            {"on": True, "white_level": 100, "mode": "white"},
        ),
        (["effects", "brightness"], {"effect": "off"}, {"on": True, "mode": "white"}),
        (
            ["brightness"],
            {
                "rgb_color": (1, 2, 3),
                "color_temp_kelvin": 4000,
                "effect": "Rainbow",
                "white": 120,
            },
            {"on": True},
        ),
        (["rgb"], {"brightness": 200}, {"on": True}),
    ],
)
async def test_command_respects_features(
    light: OpenBekenLight, features: list[str], kwargs: dict, expected: dict
) -> None:
    light._apply_description(deepcopy(ENTITIES[0]) | {"features": features})
    with patch.object(light.coordinator, "async_set_state", AsyncMock()) as send:
        await light.async_turn_on(**kwargs)
    send.assert_awaited_once_with(light.obk_id, expected)


async def test_white_service(
    hass: HomeAssistant, entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    device.entities[0]["features"] = ["brightness", "rgb", "white_level"]
    device.states["light_0"]["mode"] = "white"
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        hass.states.get("light.test_device_light").attributes["color_mode"] == "white"
    )
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.test_device_light", "white": 100},
        blocking=True,
    )
    assert (await device.next_command("set_state"))["state"] == {
        "on": True,
        "white_level": 100,
        "mode": "white",
    }


def test_missing_state_and_name(light: OpenBekenLight) -> None:
    light._apply_description(deepcopy(ENTITIES[0]) | {"name": ""})
    assert light.name == light.obk_id
    assert not light.available
    assert light.is_on is None
    assert light.brightness is None
    assert light.rgb_color is None
