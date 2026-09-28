"""Load translations through HA and verify every key and placeholder."""

import json
from pathlib import Path
from string import Formatter

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from custom_components.openbeken.const import DOMAIN


def flatten(data: dict, prefix: str = "") -> dict[str, str]:
    result = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(flatten(value, path))
        else:
            assert isinstance(value, str) and value.strip()
            result[path] = value
    return result


@pytest.mark.parametrize("language", ["en", "nl"])
def test_translation_completeness(language: str) -> None:
    root = Path(__file__).resolve().parents[1] / "custom_components" / DOMAIN
    source = flatten(json.loads((root / "strings.json").read_text(encoding="utf-8")))
    translated = flatten(
        json.loads(
            (root / "translations" / f"{language}.json").read_text(encoding="utf-8")
        )
    )
    assert source.keys() == translated.keys()
    formatter = Formatter()
    for key, value in source.items():
        assert {field for _, field, _, _ in formatter.parse(value) if field} == {
            field for _, field, _, _ in formatter.parse(translated[key]) if field
        }


async def test_ha_loads_dutch_config_translations(hass: HomeAssistant) -> None:
    translations = await async_get_translations(hass, "nl", "config", [DOMAIN])
    prefix = f"component.{DOMAIN}.config"
    assert translations[f"{prefix}.step.user.title"] == "Verbinden met OpenBeken"
    assert translations[f"{prefix}.step.reconfigure.data.port"] == "Poort"
    assert "6054" in translations[f"{prefix}.error.cannot_connect"]
    assert "API-versie 1" in translations[f"{prefix}.error.unsupported_protocol"]


async def test_ha_loads_dutch_repair_translations(hass: HomeAssistant) -> None:
    translations = await async_get_translations(hass, "nl", "issues", [DOMAIN])
    prefix = f"component.{DOMAIN}.issues"
    assert (
        translations[f"{prefix}.wrong_device.title"]
        == "Ander OpenBeken-apparaat gevonden voor {name}"
    )
    assert "Opnieuw configureren" in translations[f"{prefix}.wrong_device.description"]


async def test_ha_loads_dutch_exception_translations(hass: HomeAssistant) -> None:
    translations = await async_get_translations(hass, "nl", "exceptions", [DOMAIN])
    assert (
        "niet op tijd bevestigd"
        in translations[f"component.{DOMAIN}.exceptions.command_timeout.message"]
    )
