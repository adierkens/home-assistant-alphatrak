"""Constants for the AlphaTRAK integration."""

DOMAIN = "alphatrak"

# Configuration constants
CONF_TOKEN_KEY = "token"  # noqa: S105 - configuration key name, not a hardcoded secret
CONF_PET_ID = "pet_id"

# API constants
API_BASE_URL = "https://alphatrakapi.zoetis.com/api"
API_ENDPOINT = "GetPetActivityByDateWiseList"
API_TIMEOUT = 30

# Default values
DEFAULT_LANGUAGE_ID = "1"
DEFAULT_SCAN_INTERVAL_MINUTES = 5

# Data keys
DATA_GLUCOSE_LEVEL = "GlucoseLevel"
DATA_GLUCOSE_UNIT_ID = "GlucoseUnitId"
DATA_GLUCOSE_ENTRY_DATETIME = "GlucoseEntryDateTime"
DATA_UNIT_TYPE = "UnitType"
DATA_GLUCOSE_DEVICE_NAME = "GlucoseDeviceName"
DATA_AFTER_MEAL = "AfterMeal"
DATA_AFTER_INSULIN = "AfterInsulinInjection"
DATA_CONTROL_TEST = "ControlTest"
DATA_GLUCOSE_NOTE = "GlucoseNote"
DATA_INSULIN_DOSE = "InsulinDose"
DATA_INSULIN_ENTRY_DATETIME = "InsulinEntryDateTime"
DATA_FEEDING_ENTRY_DATETIME = "FeedingEntryDateTime"

# Response keys
RESPONSE_SUCCESS = "IsSuccess"
RESPONSE_DATA = "ResponseData"
RESPONSE_PET_ACTIVITY = "PetActivity"
RESPONSE_BLOOD_GLUCOSE = "BloodGlucose"
RESPONSE_MIN_RANGE = "MinRange"
RESPONSE_MAX_RANGE = "MaxRange"
RESPONSE_INSULIN = "Insulin"
RESPONSE_FEEDING = "Feeding"
RESPONSE_EXERCISE = "Exercise"
RESPONSE_URINATION = "Urination"
RESPONSE_VOMITING = "Vomiting"
RESPONSE_WATER_INTAKE = "WaterIntake"
RESPONSE_WEIGHT = "Weight"
RESPONSE_SIGNS_OF_ILLNESS = "SignsOfillness"
