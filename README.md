# STRATIS AC for Home Assistant

<p align="center">
  <img src="custom_components/stratis_ac/brand/icon.png" alt="STRATIS logo" width="160">
</p>

An unofficial Home Assistant custom integration that exposes STRATIS-managed thermostats as native `climate` entities.

> [!WARNING]
> This project uses an undocumented STRATIS cloud API. It is not affiliated with or supported by STRATIS. API behavior may change without notice.

## Features

- Automatic discovery across every property available to the STRATIS account
- One Home Assistant device and `climate` entity per thermostat
- Heat, cool, automatic heat/cool, and off modes when supported by the device
- Heating and cooling target temperatures
- Automatic-mode low/high target range
- Fan auto/on control when advertised by the thermostat
- Current temperature, humidity, online status, and HVAC action
- Automatic one-hour access-token renewal
- Safe persistence of rotating refresh tokens
- One forced refresh and retry after an HTTP 401
- Home Assistant reauthentication flow when the session can no longer refresh
- Redacted diagnostics
- English and Simplified Chinese UI

The integration polls every 30 seconds. STRATIS also exposes a temporary WebSocket stream, but polling is intentionally the reliable baseline and does not depend on a short-lived streaming URL.

## Installation with HACS

Until the repository is listed in HACS defaults:

1. Open HACS.
2. Select **Integrations**.
3. Open the menu and select **Custom repositories**.
4. Add `https://github.com/Apocalypsor/ha-stratis-ac` with category **Integration**.
5. Install **STRATIS AC** and restart Home Assistant.
6. Go to **Settings → Devices & services → Add integration → STRATIS AC**.

Manual installation is also possible by copying `custom_components/stratis_ac` into Home Assistant's `/config/custom_components/` directory and restarting.

## Authentication

STRATIS access tokens expire after 3600 seconds. The mobile app renews them through `https://auth.stratisiot.com/oauth/token` with `grant_type=refresh_token`. Every successful renewal returns a rotated refresh token.

The configuration form asks for the **latest `refresh_token` from a successful token response JSON**. Do not paste the old token from the request body; it has already been rotated.

The token can be found in a network capture made from your own STRATIS account:

1. Capture the STRATIS app startup traffic.
2. Locate a successful `POST https://auth.stratisiot.com/oauth/token` request.
3. Inspect its response JSON.
4. Copy the response's `refresh_token` value into the integration setup form.

Never publish the capture or token. HAR files commonly include live credentials, account identifiers, device serial numbers, and location data.

### Mobile-app token rotation caveat

The mobile app and Home Assistant may initially hold the same rotating refresh token. If STRATIS invalidates the previous token immediately after each refresh, whichever client refreshes first can leave the other with a stale token. A dedicated STRATIS account/session for Home Assistant is preferred when the property supports it. Otherwise, Home Assistant will request reauthentication if its saved token loses the rotation race.

## Thermostat behavior

STRATIS mode values are mapped as follows:

| STRATIS | Home Assistant |
| --- | --- |
| `HEAT` | Heat |
| `COOL` | Cool |
| `AUTO` | Heat/Cool |
| `OFF` | Off |

Temperature writes preserve the payload behavior observed from the mobile app: the requested temperature is written to `value`, the last confirmed integral temperature remains in `value_int`, and the thermostat's native `C` or `F` scale is included.

## Troubleshooting

- **Invalid or already rotated token:** Capture a newer successful OAuth token response and complete the Home Assistant reauthentication flow.
- **Entity unavailable:** Confirm the thermostat reports `online: ONLINE` in STRATIS and that the cloud service is reachable.
- **Command appears delayed:** The integration refreshes device state immediately after a command, but the upstream thermostat may publish the confirmed state asynchronously. The next 30-second poll will reconcile it.
- **API changed:** Enable debug logging and attach redacted diagnostics to an issue. Never attach a raw HAR or authorization header.

```yaml
logger:
  logs:
    custom_components.stratis_ac: debug
```

## Development

Repository conventions and protocol invariants are documented in [`AGENTS.md`](AGENTS.md).

```bash
uv sync --locked --all-groups
uv run --locked python -m compileall custom_components tests
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
```

## License

MIT
