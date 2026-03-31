# Architecture of oceano-now-playing

## System Overview

```
oceano-player (backend)
    │
    ├── /tmp/oceano-state.json    ← track metadata, seek position, source, artwork path
    └── /tmp/oceano-vu.sock       ← stereo RMS frames at ~22 fps
              │
              ▼
┌─────────────────────────────────────┐
│  src/media_players/state_file.py    │
│  StateFileClient                    │
│  - Polls state file every 0.5s      │
│  - Interpolates seek position       │
│  - Loads artwork from file path     │
└──────────────┬──────────────────────┘
               │  state dict
               ▼
┌─────────────────────────────────────┐
│  src/app/main.py                    │
│  State Machine + Event Loop         │
│  - Detects state changes            │
│  - Handles display sleep/wake       │
│  - Controls text/artwork cycle      │
└──────────────┬──────────────────────┘
               │  render requests
               ▼
┌─────────────────────────────────────┐
│  src/renderer.py                    │
│  Renderer                           │
│  - PIL image composition            │
│  - RGB565 encoding                  │
│  - Writes to /dev/fb0               │
└──────────────┬──────────────────────┘
               │  RGB565 bytes
               ▼
           /dev/fb0
               │  SPI/I2C
               ▼
          SPI display (480×320)
```

## Component Details

### 1. Metadata Client (`media_players/state_file.py` → `StateFileClient`)

**Responsibility**: Poll `/tmp/oceano-state.json` and emit normalised state dicts.

**Key state fields**:
```python
{
    'title': str,               # Track title
    'artist': str,              # Artist name
    'album': str,               # Album name
    'status': 'play'|'stop',
    'seek': int,                # Progress in ms (interpolated from anchor)
    'duration': int,            # Track length in ms
    'samplerate': str,          # e.g. '44.1 kHz'
    'bitdepth': str,            # e.g. '16 bit'
    'playback_source': str,     # 'AirPlay' | 'Physical' | ''
    '_resolved_artwork': dict | None,
}
```

**Artwork**: Loaded from `track.artwork_path` in the state file (written by `oceano-state-manager`, which fetches from iTunes after ACRCloud recognition). No external provider lookups in this process.

### 2. State Machine (`app/main.py`)

**Responsibility**: Detect state changes, orchestrate rendering, manage display lifecycle.

**Key responsibilities**:
- Detect new song, pause, resume, stop transitions.
- Alternate between text mode and artwork mode on a `CYCLE_TIME` interval.
- Sleep the display after `STANDBY_TIMEOUT` seconds of inactivity.
- Interpolate seek position between metadata updates for smooth progress bars.

**Global state**:
```python
last_state: dict | None          # Most recently received state
last_rendered_state: dict | None # State of last render (avoids redundant redraws)
last_rendered_mode: str | None   # 'text' | 'artwork' | 'hybrid'
last_active_time: float          # Epoch time of last activity
last_cycle_time: float           # Epoch time of last mode switch
is_sleeping: bool                # True when display is powered down
is_showing_idle: bool            # True when idle screen is visible
```

### 3. Renderer (`renderer.py` → `Renderer`)

**Responsibility**: Compose PIL images and write RGB565 bytes to `/dev/fb0`.

**Display modes**:
- `text` — title, artist, quality info, progress bar.
- `artwork` — album art centred, progress bar overlay.
- `hybrid` — artwork + text on one screen, no rotation.
- `rotate` — alternates text ↔ artwork on `CYCLE_TIME` interval.
- `vu` — analog-style VU meters + title/artist footer.

**Framebuffer**: 480×320 pixels, RGB565 (2 bytes/pixel). Written directly with `mmap` or sequential seeks to `/dev/fb0`.

### 4. Configuration (`config.py` → `Config`)

All runtime parameters are in `Config`, loaded from environment variables in `__post_init__`.

| Field | Env var | Default |
|---|---|---|
| `oceano_state_file` | `OCEANO_STATE_FILE` | `/tmp/oceano-state.json` |
| `ui_preset` | `UI_PRESET` | `high_contrast_rotate` |
| `mode_cycle_time` | `CYCLE_TIME` | `30` |
| `standby_timeout` | `STANDBY_TIMEOUT` | `600` |

## Class Hierarchy

```
MediaPlayer (ABC)              media_players/base.py
    └── StateFileClient        media_players/state_file.py
            ↓ used by
        app/main.py
            ↓ uses
        renderer.py
```

`MediaPlayer` defines the interface (`connect`, `receive_message`, `is_connected`, `close`). `StateFileClient` is the only concrete implementation.

## Test Architecture

```
tests/
├── conftest.py              # Shared fixtures
├── test_renderer.py         # Rendering utilities, dominant colour, progress bar
├── test_config.py           # Config loading, env var overrides, validation
└── test_vu_client.py        # VU ballistics tests
```

Tests run entirely offline. `Renderer` is tested with a mock framebuffer file. No network or hardware access required.
