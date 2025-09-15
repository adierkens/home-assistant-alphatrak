"""AlphaTRAK sensor platform."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfBloodGlucoseConcentration
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DATA_AFTER_INSULIN,
    DATA_AFTER_MEAL,
    DATA_CONTROL_TEST,
    DATA_GLUCOSE_DEVICE_NAME,
    DATA_GLUCOSE_ENTRY_DATETIME,
    DATA_GLUCOSE_LEVEL,
    DATA_GLUCOSE_NOTE,
    DATA_INSULIN_DOSE,
    DATA_UNIT_TYPE,
    DOMAIN,
    RESPONSE_EXERCISE,
    RESPONSE_FEEDING,
    RESPONSE_INSULIN,
    RESPONSE_MAX_RANGE,
    RESPONSE_MIN_RANGE,
    RESPONSE_SIGNS_OF_ILLNESS,
    RESPONSE_URINATION,
    RESPONSE_VOMITING,
    RESPONSE_WATER_INTAKE,
    RESPONSE_WEIGHT,
)
from .coordinator import AlphaTrakCoordinator

_LOGGER = logging.getLogger(__name__)

SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="glucose_level",
        name="Glucose level",
        device_class=SensorDeviceClass.BLOOD_GLUCOSE_CONCENTRATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfBloodGlucoseConcentration.MILLIGRAMS_PER_DECILITER,
        icon="mdi:diabetes",
    ),
)


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AlphaTRAK sensor platform."""
    coordinator: AlphaTrakCoordinator = config_entry.runtime_data

    entities = [
        AlphaTrakSensor(coordinator, description, config_entry)
        for description in SENSORS
    ]

    async_add_entities(entities)


class AlphaTrakSensor(CoordinatorEntity[AlphaTrakCoordinator], SensorEntity):
    """AlphaTRAK sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AlphaTrakCoordinator,
        description: SensorEntityDescription,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{config_entry.entry_id}_{description.key}"

        # Device info for the pet
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator.api.pet_id))},
            name=f"AlphaTRAK Pet {coordinator.api.pet_id}",
            manufacturer="Zoetis",
            model="AlphaTRAK 3",
        )

    @property
    def native_value(self) -> float | None:
        """Return the native value of the sensor."""
        if not self.coordinator.data:
            return None

        latest_reading = self.coordinator.data.get("latest_reading")
        if not latest_reading:
            return None

        if self.entity_description.key == "glucose_level":
            return latest_reading.get(DATA_GLUCOSE_LEVEL)

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        # Combine checks to reduce branching
        if not self.coordinator.data or not (
            latest_reading := self.coordinator.data.get("latest_reading")
        ):
            return None

        # Parse the datetime string
        datetime_str = latest_reading.get(DATA_GLUCOSE_ENTRY_DATETIME)
        last_reading_time = None
        if datetime_str:
            try:
                last_reading_time = datetime.fromisoformat(datetime_str)
            except (ValueError, AttributeError):
                _LOGGER.debug("Could not parse datetime: %s", datetime_str)

        attributes = {
            "unit_type": latest_reading.get(DATA_UNIT_TYPE),
            "device_name": latest_reading.get(DATA_GLUCOSE_DEVICE_NAME),
            "after_meal": latest_reading.get(DATA_AFTER_MEAL, False),
            "after_insulin": latest_reading.get(DATA_AFTER_INSULIN, False),
            "control_test": latest_reading.get(DATA_CONTROL_TEST, False),
            "normal_range_min": latest_reading.get(RESPONSE_MIN_RANGE),
            "normal_range_max": latest_reading.get(RESPONSE_MAX_RANGE),
            "pet_id": self.coordinator.api.pet_id,
        }

        # Add last reading time if available
        if last_reading_time:
            attributes["last_reading_time"] = last_reading_time.isoformat()

        # Add note if available
        note = latest_reading.get(DATA_GLUCOSE_NOTE)
        if note:
            attributes["note"] = note

        # Add reading count from recent readings
        recent_readings = self.coordinator.data.get("recent_readings", [])
        attributes["readings_last_7_days"] = len(recent_readings)

        # Calculate average for last 7 days
        glucose_values = [
            reading.get(DATA_GLUCOSE_LEVEL)
            for reading in recent_readings
            if reading.get(DATA_GLUCOSE_LEVEL) is not None
        ]
        if glucose_values:
            attributes["average_last_7_days"] = round(
                sum(glucose_values) / len(glucose_values), 1
            )

        # Activity counts and last events from recent_activities/latest_activities
        recent_activities = self.coordinator.data.get("recent_activities", {})
        latest_activities = self.coordinator.data.get("latest_activities", {})

        # Helper to get a datetime value from an arbitrary activity entry
        def _find_entry_datetime(entry: dict[str, Any]) -> str | None:
            if not entry:
                return None
            for key, val in entry.items():
                if key.endswith("EntryDateTime") and isinstance(val, str):
                    return val
            # fallback: any key containing 'EntryDate'
            for key, val in entry.items():
                if "EntryDate" in key and isinstance(val, str):
                    return val
            return None

        # Define activity types and their short names for attribute keys
        activities = [
            (RESPONSE_INSULIN, "insulin"),
            (RESPONSE_FEEDING, "feeding"),
            (RESPONSE_EXERCISE, "exercise"),
            (RESPONSE_URINATION, "urination"),
            (RESPONSE_VOMITING, "vomiting"),
            (RESPONSE_WATER_INTAKE, "water_intake"),
            (RESPONSE_WEIGHT, "weight"),
            (RESPONSE_SIGNS_OF_ILLNESS, "signs_of_illness"),
        ]

        for activity_key, short_name in activities:
            # Count in the recent 7 day window
            attributes[f"{short_name}_count_last_7_days"] = len(
                recent_activities.get(activity_key, [])
            )

            # If there is a latest event for that activity, add its datetime
            latest = latest_activities.get(activity_key)
            if latest:
                dt = _find_entry_datetime(latest)
                if dt:
                    attributes[f"last_{short_name}_time"] = dt

            # Activity-specific extra fields
            if activity_key == RESPONSE_INSULIN and latest:
                attributes["last_insulin_dose"] = latest.get(DATA_INSULIN_DOSE)

            if activity_key == RESPONSE_WEIGHT and latest:
                pet_weight = latest.get("PetWeight")
                if pet_weight is not None:
                    attributes["last_weight_value"] = pet_weight

        return attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get("latest_reading") is not None
        )
