# TokenDash in Home Assistant

**English** · [Español](es/HOME_ASSISTANT.md)

In every address, `SERVER` is the IP address of the TokenDash computer (for example `192.168.1.50`) and `KEY` the key you will create in step 1.

TokenDash offers three independent modules. You can add one, two or all three to Home Assistant, each on its own card:

| Module | Address |
|---|---|
| ChatGPT | `http://SERVER:8000/en/ha/chatgpt/#key=KEY` |
| Claude | `http://SERVER:8000/en/ha/claude/#key=KEY` |
| Limits over time | `http://SERVER:8000/en/ha/chart/#key=KEY` |

The `/en/` in the address is the module's language; with `/es/` it appears in Spanish.

Each module refreshes itself: the cards every 30 seconds and the chart every 10 minutes. The chart opens on 7 days. For another period, add `?days=` before the `#`, for example `/en/ha/chart/?days=30#key=KEY`. 7, 30, 90, 182, 365 and 1825 are valid.

> **Already have modules with addresses like `/ha/grafica/?dias=30#clave=…`?** They keep working with no changes, in the language of Home Assistant's browser.

If you prefer Home Assistant entities of your own, for automations, history or native cards, each provider also has its sensor. They are in section 4.

## 1. Create the key

1. In TokenDash, open **Administration → Home Assistant keys → Add**.
2. Give it a name, for example "Home Assistant at home", and save.
3. The next page shows the key and the addresses of the three modules, already complete. **Copy them then: the key is not shown again.** TokenDash only stores its SHA-256 fingerprint.

The key can only **read** the limits. It cannot press "Refresh now", connect accounts or open the administration.

- **If it is lost or leaked:** delete the key in the administration and create another one.
- **To know whether it is used:** the "last used" column tells whether Home Assistant is using it.

The key goes after the `#` in the module addresses. The browser does not send that part to the server, so the key does not appear in its logs. The page passes it to the API in a header.

## 2. Let Home Assistant reach the server

If you gave the IP address to `init_env.py` when installing, TokenDash can already be seen from the network: try opening `http://SERVER:8000` from another device. If not, follow [Open TokenDash from other devices](MAINTENANCE.md#open-tokendash-from-other-devices).

- **If you open Home Assistant over HTTPS** (for example with Nabu Casa or a proxy): the browser blocks a card that loads an `http://` page ("mixed content"). In that case TokenDash also has to be served over HTTPS, through a proxy: see [Maintenance → HTTPS](MAINTENANCE.md#https).
- **If you open it over `http://` on the local network:** the `http://` address is enough.
- **Sensors:** they do not have this limitation, because Home Assistant's server reads them, not the browser.

## 3. "Webpage" cards

On a Home Assistant dashboard:

1. Press **Edit → Add card → Webpage**.
2. Paste the address of a module.
3. Repeat for every module you want.

In YAML:

```yaml
type: iframe
url: http://SERVER:8000/en/ha/claude/#key=KEY
aspect_ratio: 95%
```

`aspect_ratio` sets the card's height in proportion to its width. Suggested values:

| Module | `aspect_ratio` |
|---|---|
| ChatGPT and Claude cards | between `90%` and `100%` |
| Chart in a wide column | `55%` |
| Chart in a narrow column | `110%` |

The module takes the full width of the card and has a transparent background.

## 4. Sensors (optional)

Each provider has its own address. One can be added without the other:

- `http://SERVER:8000/api/ha/chatgpt/`
- `http://SERVER:8000/api/ha/claude/`

Both are requested with the `Authorization: Bearer KEY` header and return the fields below. `state_label` comes in the language of the `Accept-Language` header (English without it); the rest are numbers and dates:

| Field | Content |
|---|---|
| `session_used_percent`, `session_resets_at` | 5-hour window: % used and reset time |
| `weekly_used_percent`, `weekly_resets_at` | Weekly window |
| `session_window_reset`, `weekly_window_reset` | `true` if the window restarted after the reading: the value is the last known one, not the current one |
| `state`, `state_label` | State of the reading (`ok`, `expired`, `unavailable`…) |
| `last_success_at`, `last_attempt_at` | Last valid reading and last attempt |

A window with no data is `null`, never 0. "No data" does not mean 0 % used.

First store the key in `secrets.yaml`, with the word `Bearer` in front:

```yaml
tokendash_auth: "Bearer KEY"
```

Then, in `configuration.yaml`, add one block per provider. This one is for Claude; for ChatGPT, copy the block and replace `claude` with `chatgpt`:

```yaml
rest:
  - resource: http://SERVER:8000/api/ha/claude/
    headers:
      Authorization: !secret tokendash_auth
    scan_interval: 300
    sensor:
      - name: "Claude · 5 h session"
        unique_id: tokendash_claude_session
        unit_of_measurement: "%"
        state_class: measurement
        value_template: "{{ value_json.session_used_percent }}"
        availability: "{{ value_json.session_used_percent is not none }}"
        json_attributes: [session_resets_at, session_window_reset, state, last_success_at]
      - name: "Claude · week"
        unique_id: tokendash_claude_weekly
        unit_of_measurement: "%"
        state_class: measurement
        value_template: "{{ value_json.weekly_used_percent }}"
        availability: "{{ value_json.weekly_used_percent is not none }}"
        json_attributes: [weekly_resets_at, weekly_window_reset, state, last_success_at]
```

TokenDash reads the providers as often as set in **Administration → Settings**, every 20 minutes by default. A `scan_interval` of 300 seconds is enough.
