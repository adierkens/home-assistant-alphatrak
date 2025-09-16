# AlphaTRAK Integration

AlphaTRAK is a Home Assistant integration that integrates with the AlphaTRAK 3
blood glucose meter and the Zoetis cloud API to provide readings and activity
data for pets. This repository contains a custom integration that implements a
config flow, data coordinator, and a set of sensor entities exposing glucose
readings, activity counts and metadata.

Project status

- Quality scale: bronze
- Integration version: 0.1.0

Supported Home Assistant

- Tested with Home Assistant Core 2025.2.4 and later

Installation

Option A — HACS (recommended)

1. In HACS, go to Integrations → + (Add) → Explore & Download repositories.
2. Search for "AlphaTRAK" and install the integration.
3. Restart Home Assistant.

Option B — Manual

1. Copy the `custom_components/alphatrak` folder to your Home Assistant
   `config/custom_components/` folder.
2. Restart Home Assistant.

Configuration

This integration uses a standard username/password config flow.

1. In Home Assistant, go to Settings → Devices & Services → Add Integration.
2. Search for "AlphaTRAK" and follow the guided setup to enter your credentials.
3. Select the pet to create an entry for (the flow supports multiple pets and
   can create entries for each pet automatically).

Entities

The integration creates the following sensor entities per pet (entity names
include the pet id):

- Glucose level (`sensor.alpha_trak_glucose_level`) — latest glucose reading
- Readings last 7 days (`sensor.alpha_trak_readings_last_7_days`) — count
- Average last 7 days (`sensor.alpha_trak_average_last_7_days`) — computed avg
- Feedings, insulin, exercise, urination, vomiting, water intake, signs of
  illness counts (7d) and their last event timestamps
- Last insulin dose, last weight value, and various boolean flags from the
  latest glucose reading (after meal, after insulin, control test)

Developer notes

- Domain: `alphatrak`
- Integration directory: `custom_components/alphatrak`
- Requirements: `pycryptodome>=3.19.0` (declared in `manifest.json`)
- This project exposes a config flow (`config_flow.py`) and uses an
  UpdateCoordinator (`coordinator.py`) to manage polling and caching.

Contributing

Contributions are welcome. Please follow standard Home Assistant
contribution guidelines:

- Run linting and tests if applicable.
- Update the `quality_scale.yaml` when changing the integration quality.

Troubleshooting

- If the config flow fails with authentication errors, double-check your
  username/password and try again.
- If no pets are found during setup, ensure your account has an active
  pet registered with the AlphaTRAK service.

License

This project is licensed under the MIT license. See `LICENSE` for details.
