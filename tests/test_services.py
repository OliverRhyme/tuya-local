"""Tests for the tuya_local actions."""

from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tuya_local.const import CONF_DEVICE_ID, DOMAIN
from custom_components.tuya_local.services import async_setup_services


@pytest.fixture
async def tuya_device(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_DEVICE_ID: "dev1"})
    entry.add_to_hass(hass)
    ha_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "dev1")}
    )
    device = Mock(async_update_dps=AsyncMock())
    hass.data[DOMAIN] = {"dev1": {"device": device}}
    await async_setup_services(hass, [])
    return ha_device, device


async def test_refresh_dps_requests_dps_from_the_device(hass, tuya_device):
    ha_device, device = tuya_device

    await hass.services.async_call(
        DOMAIN,
        "refresh_dps",
        {"device_id": ha_device.id, "dps": [18, 19, 20]},
        blocking=True,
    )

    device.async_update_dps.assert_awaited_once_with([18, 19, 20])


async def test_refresh_dps_rejects_a_device_from_another_integration(hass, tuya_device):
    other = MockConfigEntry(domain="other")
    other.add_to_hass(hass)
    foreign = dr.async_get(hass).async_get_or_create(
        config_entry_id=other.entry_id, identifiers={("other", "x")}
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "refresh_dps", {"device_id": foreign.id, "dps": [18]}, blocking=True
        )
