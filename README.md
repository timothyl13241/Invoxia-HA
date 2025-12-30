# Invoxia™ GPS Tracker Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

This custom component integrates Invoxia™ GPS trackers with Home Assistant, allowing you to track the location of your Invoxia devices directly in your Home Assistant dashboard.

## Features

- **Real-time Location Tracking**: Monitor the GPS location of all your Invoxia trackers
- **Device Tracker Entities**: Each Invoxia™ device appears as a device tracker in Home Assistant
- **Battery Monitoring**: Track battery levels for all devices
- **Location Accuracy**: View the precision/accuracy of GPS coordinates
- **Automatic Updates**: Integration polls for updates every 7 minutes (420 seconds)
- **Multiple Device Support**: Track multiple Invoxia devices simultaneously
- **Custom Icons**: Devices display with appropriate Material Design Icons based on their type (car, bike, pet, etc.)

## Supported Devices

This integration works with Invoxia GPS tracker devices, including:
- Invoxia™ GPS Tracker (pets, vehicles, personal items)
- Invoxia™ Bike Tracker
- Any device compatible with the Invoxia™ GPS tracking platform

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to "Integrations"
3. Click the three dots in the top right corner and select "Custom repositories"
4. Add this repository URL: `https://github.com/timothyl13241/Invoxia-HA`
5. Select "Integration" as the category
6. Click "Add"
7. Search for "Invoxia" and install
8. Restart Home Assistant

### Manual Installation

1. Download the latest release from this repository
2. Copy the `custom_components/invoxia` folder to your Home Assistant's `custom_components` directory
3. If the `custom_components` directory doesn't exist, create it in your Home Assistant configuration directory
4. Restart Home Assistant

## Configuration

### Setup via UI

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Invoxia"
4. Enter your Invoxia™ account credentials:
   - **Username**: Your Invoxia™ account email
   - **Password**: Your Invoxia™ account password
5. Click **Submit**

The integration will automatically discover all trackers associated with your account and create device tracker entities for each one.

### Entity Naming

Entities are automatically created with the following format:
- **Entity ID**: `device_tracker.<tracker_name>`
- **Friendly Name**: The name you assigned to the tracker in the Invoxia app

### Available Attributes

Each device tracker entity provides the following attributes:
- `latitude`: Current GPS latitude
- `longitude`: Current GPS longitude
- `gps_accuracy`: Location accuracy in meters
- `battery_level`: Battery percentage (0-100)
- `source_type`: Always "gps"

## Usage Examples

### Displaying on a Map

The device trackers automatically appear on the Home Assistant map card. Add a map card to your dashboard to see all your trackers:

```yaml
type: map
entities:
  - device_tracker.my_invoxia_tracker
```

### Automation Examples

#### Notify when device enters a zone

```yaml
automation:
  - alias: "Notify when car arrives home"
    trigger:
      - platform: zone
        entity_id: device_tracker.my_car
        zone: zone.home
        event: enter
    action:
      - service: notify.mobile_app
        data:
          message: "Your car has arrived home"
```

#### Alert on low battery

```yaml
automation:
  - alias: "Low battery alert for tracker"
    trigger:
      - platform: numeric_state
        entity_id: device_tracker.my_invoxia_tracker
        value_template: "{{ state_attr('device_tracker.my_invoxia_tracker', 'battery_level') }}"
        below: 20
    action:
      - service: notify.mobile_app
        data:
          message: "Tracker battery is low ({{ state_attr('device_tracker.my_invoxia_tracker', 'battery_level') }}%)"
```

## Troubleshooting

### Integration fails to load

**Symptoms**: Integration shows as "Failed to load" or displays error messages during setup.

**Solutions**:
- Verify your Invoxia credentials are correct
- Check that your Invoxia account has active devices
- Ensure you have an active internet connection
- Check Home Assistant logs for specific error messages: **Settings** → **System** → **Logs**

### "Cannot connect" error

**Symptoms**: Setup fails with "cannot_connect" error.

**Solutions**:
- Verify internet connectivity from your Home Assistant instance
- Check if Invoxia services are operational
- Try again in a few minutes (temporary API issues)

### "Invalid authentication" error

**Symptoms**: Setup fails with "invalid_auth" error.

**Solutions**:
- Double-check your username (email) and password
- Ensure your account is active on the Invoxia platform
- Try logging into the Invoxia mobile app to verify credentials

### Devices not updating

**Symptoms**: Location or battery level not updating.

**Solutions**:
- The integration polls every 7 minutes - wait for the next update cycle
- Check that the device has battery and GPS signal
- Restart the integration: **Settings** → **Devices & Services** → **Invoxia** → **⋮** → **Reload**
- Check Home Assistant logs for API errors

### Re-authentication Required

If you change your Invoxia password or if your authentication expires:

1. Go to **Settings** → **Devices & Services**
2. Find the Invoxia integration
3. Click **Configure** or the re-authentication notification
4. Enter your new credentials

## API Rate Limiting & Disclaimer

The integration is designed to respect Invoxia's API rate limits:
- Update interval: 420 seconds (7 minutes)
- Efficient data fetching using batch operations
- Automatic retry with exponential backoff on failures

This integration uses the [gps-tracker](https://gps-tracker.readthedocs.io/) Python library to communicate with Invoxia's API.
[gps_tracker on GitLab](https://gitlab.com/ezlo.picori/gps_tracker)

As documented on the library:
> Note that even though direct access to Invoxia™ API is not strictly prohibited in their terms of use, it is
not encouraged either: company representatives have already stated that they do not currently consider making the
API opened for all customers and this feature is limited to their pro tracking offer.
Therefore, by using gps_tracker you:
> 1. Accept to use this direct API access in a reasonable manner by limiting the query rate to the bare minimum required
for your application.
> 2. Understand that the Invoxia™ company may take any action they see fit regarding your account if they consider your
usage of their API to be in violation with their terms of use.

## Privacy & Security

- Your Invoxia credentials are stored securely in Home Assistant's encrypted configuration
- Communication with Invoxia™ servers uses secure HTTPS connections
- No data is shared with third parties
- All data processing happens locally within your Home Assistant instance

## Known Limitations

- Location updates depend on the Invoxia device's GPS signal and reporting frequency
- Battery life of devices is managed by Invoxia's™ platform (typically configured for optimal battery conservation)
- The integration requires an active internet connection to communicate with Invoxia's™ cloud services

### Reporting Issues

If you encounter bugs or have feature requests:
1. Check existing [GitHub Issues](https://github.com/timothyl13241/Invoxia-HA/issues)
2. Create a new issue with:
   - Home Assistant version
   - Integration version
   - Detailed description of the problem
   - Relevant logs (remove sensitive information)

## Credits & Acknowledgments

This integration was originally written by [@ezlo-picori](https://github.com/ezlo-picori) as part of a [core Home Assistant pull request](https://github.com/home-assistant/core/pull/63671). This repository re-packages it as a custom component for easier installation and maintenance.

Special thanks to the following contributors:
- [@ezlo-picori](https://github.com/ezlo-picori) - Original integration development
- [@MagnusErler](https://github.com/MagnusErler) - Testing and feedback
- [@bercht-a](https://github.com/bercht-a) - Code improvements
- [@julesxxl](https://github.com/julesxxl) - Bug fixes and enhancements

## License

This project is provided as-is for use with Home Assistant. See the repository license for details.

## Related Links

- [Invoxia Official Website](https://www.invoxia.com/)
- [gps-tracker Python Library Documentation](https://gps-tracker.readthedocs.io/)
- [Home Assistant Device Tracker Documentation](https://www.home-assistant.io/integrations/device_tracker/)
- [Original Pull Request](https://github.com/home-assistant/core/pull/63671)
