"""Services for Tuya Local integration."""

import asyncio
import logging

import voluptuous as vol
from homeassistant.components import infrared
from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    DEFAULT_DELAY_SECS,
)
from homeassistant.components.remote import DOMAIN as REMOTE_DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import service

from .const import DOMAIN
from .helpers.config import get_device_id
from .infrared import TuyaRemoteCommand
from .remote import FLAG_SAVE_DELAY, TuyaLocalRemote

REMOTE_SEND_IR_COMMAND_SCHEMA = {
    vol.Required("emitter_entity_id"): cv.entity_id,
    vol.Required("command"): str,
    vol.Optional("device"): str,
}

REFRESH_DPS_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("dps"): vol.All(cv.ensure_list, [vol.Coerce(int)]),
    }
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_services(hass: HomeAssistant, entities: list[str]):
    """Set up services for the Tuya Local integration."""
    if not hass.services.has_service(DOMAIN, "refresh_dps"):

        async def async_handle_refresh_dps(call: ServiceCall):
            await _device_for(hass, call.data["device_id"]).async_update_dps(
                call.data["dps"]
            )

        hass.services.async_register(
            DOMAIN,
            "refresh_dps",
            async_handle_refresh_dps,
            schema=REFRESH_DPS_SCHEMA,
        )
    if "remote" in entities:
        service.async_register_platform_entity_service(
            hass,
            DOMAIN,
            "send_learned_ir_command",
            entity_domain=REMOTE_DOMAIN,
            schema=REMOTE_SEND_IR_COMMAND_SCHEMA,
            func=async_handle_send_ir_command,
        )
    return True


async def async_handle_send_ir_command(entity, call: ServiceCall):
    """Action to send a saved remote command."""
    _LOGGER.info("Sending saved remote command: %s", call.data)

    if not isinstance(entity, TuyaLocalRemote):
        raise ValueError("Entity must be a tuya-local remote")
    if not entity._storage_loaded:
        await entity._async_load_storage()

    emitter = call.data.get("emitter_entity_id")
    device = call.data.get("device")
    command = call.data.get("command")
    delay = call.data.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
    code_list = entity._extract_codes(
        [command], subdevice=device
    )  # Validate command and get code
    at_least_one_sent = False
    for codes in code_list:
        if at_least_one_sent:
            await asyncio.sleep(delay)
        if len(codes) > 1:
            code = codes[entity._flags[device]]
            entity._flags[device] ^= 1
        else:
            code = codes[0]
        if code.startswith("rf:"):
            _LOGGER.error("RF emitters are not yet supported by this service")
            continue
        await infrared.async_send_command(
            entity.hass, emitter, TuyaRemoteCommand(code=code)
        )
        at_least_one_sent = True

        if at_least_one_sent:
            entity._flag_storage.async_delay_save(
                lambda: entity._flags, FLAG_SAVE_DELAY
            )


def _device_for(hass: HomeAssistant, device_id: str):
    """Return the TuyaLocalDevice behind a Home Assistant device id."""
    ha_device = dr.async_get(hass).async_get(device_id)
    for entry_id in ha_device.config_entries if ha_device else ():
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and entry.domain == DOMAIN:
            stored = hass.data.get(DOMAIN, {}).get(get_device_id(entry.data))
            if stored and stored.get("device"):
                return stored["device"]
    raise ServiceValidationError(f"{device_id} is not a connected tuya-local device")
