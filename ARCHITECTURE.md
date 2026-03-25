# Architecture of oceano-now-playing

## System Overview

```
AirPlay source
    │  (AirPlay protocol)
    ▼
shairport-sync
    │  writes metadata items to FIFO
    │  /tmp/shairport-sync-metadata
    ▼
┌─────────────────────────────────────┐
│  src/media_players/oceano.py        │
│  OceanoClient                       │
│  - Reads FIFO with select()         │
│  - Decodes XML metadata items       │
│  - Applies grace period for bursts  │
│  - Resolves artwork via providers   │
└──────────────┬──────────────────────┘
               │  state dict
               ▼
┌─────────────────────────────────────┐
│  src/app/main.py                    │
│  State Machine + Event Loop         │
│  - Detects state changes            │
│  - Manages artwork resolution       │
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

### 1. Metadata Client (`media_players/oceano.py` → `OceanoClient`)

**Responsibility**: Read and decode shairport-sync metadata, emit state dicts.

**Protocol**: shairport-sync writes XML items to a FIFO, each with a 4-byte type, 4-byte code, and base64-encoded payload. `OceanoClient` parses these with a regex, accumulates them into an internal `_state` dict, and applies a short grace period (`TRACK_METADATA_GRACE_SECONDS = 0.8s`) before emitting a state update to allow burst items to settle.

**Key state fields**:
```python
{
    'title': str,           # Track title
    'artist': str,          # Artist name
    'album': str,           # Album name
    'status': 'play'|'stop',
    'seek': int,            # Progress in ms (0 during sparse metadata periods)
    'duration': int,        # Track length in ms
    'samplerate': str,      # e.g. '44.1 kHz'
    'bitdepth': str,        # e.g. '16 bit'
    'playback_source': str, # 'AirPlay' | 'Bluetooth' | 'UPnP'
    '_resolved_artwork': dict | None,
}
```

**Artwork resolution**: `OceanoClient.resolve_artwork()` (defined in `MediaPlayer` base) uses `artwork.providers.ArtworkLookup` to query Cover Art Archive, iTunes, and Deezer by artist+album. Result is cached in the state dict under `_resolved_artwork`.

### 2. State Machine (`app/main.py`)

**Responsibility**: Detect state changes, orchestrate rendering, manage display lifecycle.

**Key responsibilities**:
- Detect new song, pause, resume, stop transitions.
- Decide when to resolve artwork (`should_resolve_artwork()`).
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

**Framebuffer**: 480×320 pixels, RGB565 (2 bytes/pixel). Written directly with `mmap` or sequential seeks to `/dev/fb0`.

### 4. Configuration (`config.py` → `Config`)

All runtime parameters are in `Config`, loaded from environment variables in `__post_init__`. Relevant settings:

| Field | Env var | Default |
|---|---|---|
| `oceano_metadata_pipe` | `OCEANO_METADATA_PIPE` | `/tmp/shairport-sync-metadata` |
| `external_artwork_enabled` | `EXTERNAL_ARTWORK_ENABLED` | `True` |
| `ui_preset` | `UI_PRESET` | `high_contrast_rotate` |
| `mode_cycle_time` | `CYCLE_TIME` | `30` |
| `standby_timeout` | `STANDBY_TIMEOUT` | `600` |

## Class Hierarchy

```
MediaPlayer (ABC)          media_players/base.py
    └── OceanoClient       media_players/oceano.py
            ↓ used by
        app/main.py
            ↓ uses
        renderer.py
```

`MediaPlayer` defines the interface (`connect`, `receive_message`, `is_connected`, `close`) and provides the shared `resolve_artwork` utility. `OceanoClient` is the only concrete implementation.

## Test Architecture

```
tests/
├── conftest.py              # Shared fixtures (oceano_state_*, mock_renderer)
├── test_oceano.py           # OceanoClient: FIFO parsing, state emission, grace period
├── test_media_player.py     # MediaPlayer ABC contract + detect_media_player factory
├── test_state_machine.py    # State transitions, artwork policy, seek interpolation
├── test_renderer.py         # Rendering utilities, dominant colour, progress bar
├── test_config.py           # Config loading, env var overrides, validation
└── test_artwork_providers.py
```

Tests run entirely offline. `OceanoClient` is tested with a temporary FIFO (via `tmp_path`). `Renderer` is tested with a mock framebuffer file. No network or hardware access required.
