# Architecture of spi-now-playing

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                                                               │
│  Volumio (localhost:3000)                                    │
│  WebSocket Server                                            │
│  (Playing status updates)                                    │
│                                                               │
└───────────────────┬───────────────────────────────────────────┘
                    │
                    │ Socket.io WebSocket
                    │ (42["pushState", {...}])
                    │
        ┌───────────▼──────────────┐
        │ media_players/volumio.py │
        │   WebSocket Client       │
        │   (Threaded receiver)    │
        └────────────┬─────────────┘
                     │
                     │ Queue messages
                     │ (Thread-safe)
                     │
        ┌────────────▼────────────────┐
        │    app/main.py              │
        │  State Machine              │
        │  + Event Handler            │
        └────────────┬─────────────────┘
                     │
                     │ Render requests
                     │
        ┌────────────▼──────────────┐
        │   renderer.py              │
        │   PIL to Framebuffer       │
        └────────────┬────────────────┘
                     │
                     │ RGB565 bytes
                     │
        ┌────────────▼──────────────┐
        │   /dev/fb0                 │
        │   Framebuffer (480×320)    │
        └───────────────────────────┘
                     │
                     │ I2C/SPI
                     │
        ┌────────────▼──────────────┐
        │   SPI Display              │
        │   (Visual Output)          │
        └───────────────────────────┘
```

## Component Architecture

### 1. WebSocket Client (`media_players/volumio.py`)

**Responsibility**: Receive playback state updates from Volumio

**Socket.io Protocol**:
```
Connection: ws://localhost:3000/socket.io/?EIO=3&transport=websocket

Heartbeat Mechanism:
  Client receives: '2'  (heartbeat ping)
  Client responds: '3'  (heartbeat pong)

State Messages:
  Format: 42["pushState",{...}]
  Example:
    42["pushState",{
      "title":"Song Name",
      "artist":"Artist Name",
      "album":"Album Name",
      "status":"play",
      "seek":30000,
      "duration":180000,
      "samplerate":"44.1 kHz",
      "bitdepth":"16 bit",
      "albumart":"/albumart?imageUrl=..."
    }]
```

**Key Functions**:
```python
connect() -> bool
  # Establish WebSocket connection
  # Send initial getState request
  # Return success/failure

receive_message(timeout: float) -> dict | None
  # Non-blocking receive with timeout
  # Handle heartbeat (return None)
  # Parse pushState JSON
  # Handle errors gracefully
  # Return state dict or None

is_connected() -> bool
  # Check if WebSocket is active
```

**Critical Edge Cases**:
- **AirPlay (Spotify Connect)**: `seek=None, duration=None`
- **Malformed JSON**: Log and skip
- **Timeout**: Expected for idle clients
- **Connection Loss**: Handled by main event loop retry

**Threading**:
```python
# Conceptual (actual implementation in app/main.py):
while running:
    state = client.receive_message(timeout=1.0)
    if state:
        queue.put(state)  # Thread-safe queue to main loop
```

---

### 2. State Machine (`app/main.py`)

**Responsibility**: Manage display state, handle transitions, coordinate timing

**State Flow**:
```
START
  │
  └──► IDLE (no music)
        │
        ├──► [music starts] ──► PLAYING
        │                         │
        │                         ├──► [pause] ──► PAUSED ──┐
        │                         │                         │
        │                         ├──► [stop] ──► STOPPED   │
        │                         │        ▲                │
        │                         └────────┼────────────────┘
        │
        └──► [5 min idle] ──► SLEEP
              (display off)
                  │
                  └──► [music] ──► WAKE
```

**Critical State Variables**:
```python
# Playback state
current_state: dict = {}          # Latest Volumio state
rendered_state: dict = {}         # Last rendered state
last_state_update: float = 0.0    # Timestamp for seek interpolation

# Display timing
last_mode_change: float = 0.0     # When to toggle text ↔ artwork
current_mode: bool = True         # True = text, False = artwork
display_is_on: bool = True        # Sleep state
last_interaction: float = 0.0     # For STANDBY_TIMEOUT
```

**Timing Constants**:
```python
CYCLE_TIME = 30          # Seconds between mode changes (text ↔ artwork)
STANDBY_TIMEOUT = 300    # Seconds before display sleeps (5 min)
UPDATE_INTERVAL = 0.1    # Refresh rate (10 FPS)
```

**Key Logic**:

**1. Pause/Resume Recovery** (CRITICAL)
```python
# Problem: Pause leaves old rendered state, resume shows stale artwork
# Solution: Reset rendered_state on pause→resume

if current_state['status'] == 'play' and rendered_state.get('status') == 'pause':
    # Transitioning from pause to play
    rendered_state = {}  # Clear to force re-render
```

**2. Mode Alternation** (Every 30 seconds)
```python
elapsed = time.time() - last_mode_change
if elapsed >= CYCLE_TIME:
    current_mode = not current_mode  # Toggle text ↔ artwork
    last_mode_change = time.time()
    rendered_state = {}  # Force re-render in new mode
```

**3. Display Sleep** (After 5 min idle)
```python
elapsed = time.time() - last_interaction
if elapsed >= STANDBY_TIMEOUT:
    display_is_on = False
    renderer.turn_off_display()

# Wake up when music starts
if current_state['status'] == 'play' and not display_is_on:
    display_is_on = True
    renderer.turn_on_display()
    last_interaction = time.time()
```

**4. Seek Interpolation** (Smooth progress between updates)
```python
# Volumio updates ~1x/sec, but no progress update during paused
# Interpolate to smooth progress bar

elapsed_since_update = time.time() - last_state_update
interpolated_seek = rendered_state['seek'] + (elapsed_since_update * 1000)
progress_percent = interpolated_seek / rendered_state['duration']
```

**Event Loop Structure**:
```python
while running:
    # 1. Receive new state (non-blocking, timeout=0.1)
    new_state = volumio_client.receive_message(timeout=0.1)
    
    # 2. If new state received, update current_state
    if new_state:
        current_state = new_state
        last_state_update = time.time()
        last_interaction = time.time()  # Reset idle timer
    
    # 3. Check if re-render needed
    needs_render = False
    
    # Check state changed
    if states_are_equal(current_state, rendered_state) is False:
        needs_render = True
    
    # Check mode needs toggle (every 30s)
    if time.time() - last_mode_change >= CYCLE_TIME:
        current_mode = not current_mode
        last_mode_change = time.time()
        needs_render = True
    
    # Check display sleep/wake
    elapsed_idle = time.time() - last_interaction
    if elapsed_idle >= STANDBY_TIMEOUT and display_is_on:
        display_is_on = False
        needs_render = True
    
    # 4. Render if needed
    if needs_render:
        if current_mode == TEXT_MODE:
            renderer.render_text_mode(current_state)
        else:
            renderer.render_artwork_mode(current_state)
        rendered_state = copy(current_state)
    
    # 5. Sleep briefly to avoid busy-wait
    time.sleep(UPDATE_INTERVAL)
```

---

### 3. Renderer (`renderer.py`)

**Responsibility**: Convert playback state → visual framebuffer output

**Display Modes**:
```
TEXT MODE:
┌─────────────────────────────────────┐
│  Now Playing                        │
├─────────────────────────────────────┤
│  Song Name                          │
│  Artist Name                        │
│                                     │
│  ████████░░░░░░  Progress          │
│                                     │
│  44.1 kHz | 16 bit | Spotify       │
└─────────────────────────────────────┘

ARTWORK MODE:
┌─────────────────────────────────────┐
│                                     │
│        [Album Art Image]            │
│        (480×320 or centered)        │
│                                     │
│  ████████░░░░░░  Artist - Song     │
└─────────────────────────────────────┘

IDLE SCREEN:
┌─────────────────────────────────────┐
│                                     │
│       Waiting for Volumio...        │
│                                     │
│                                     │
└─────────────────────────────────────┘
```

**Framebuffer Details**:
```
Format: RGB565 (16-bit color)
  Red:   5 bits (0-31)
  Green: 6 bits (0-63)
  Blue:  5 bits (0-31)

Resolution: 480 × 320 pixels
Total bytes: 480 × 320 × 2 = 307,200 bytes

Memory layout: Row-major, left-to-right
  Pixel (0,0) → bytes 0-1
  Pixel (1,0) → bytes 2-3
  Pixel (479,0) → bytes 958-959
  Pixel (0,1) → bytes 960-961
```

**Key Functions**:

**1. Dominant Color Extraction** (For theme)
```python
def _get_dominant_color(image: PIL.Image) -> tuple:
    """Extract dominant color from album art.
    
    Used for:
    - Text color overlay
    - Background gradient
    - Progress bar color
    
    Returns: (R, G, B) tuple
    """
    # Resize to 1×1 to get average color
    # Or use colorsys to find dominant hue
```

**3. Album Art Cache** (LRU, 10 items)
```python
cache_album_art(url: str) -> PIL.Image | None:
    """Fetch and cache album art.
    
    Cache behavior:
    - Max 10 items in memory
    - Auto-clear oldest when full
    - Skip if already cached
    - Time limit on old entries (5 min)
    
    Returns: PIL Image or None if fetch fails
    """
```

**4. Rendering Modes**
```python
render_text_mode(state: dict) -> bytes:
    """Render text-based display.
    
    Layout:
    1. Background (black or dark)
    2. Title (white, bold)
    3. Artist (gray, smaller)
    4. Progress bar indicator
    5. Quality info (44.1 kHz, 16 bit, service)
    
    Returns: RGB565 bytes for framebuffer
    """

render_artwork_mode(state: dict) -> bytes:
    """Render artwork-centered display.
    
    Layout:
    1. Fetch album art
    2. Resize/center (maintain aspect)
    3. Overlay progress bar at bottom
    4. Show artist and song title
    
    Returns: RGB565 bytes for framebuffer
    """
```

**5. Framebuffer Writing**
```python
def write_to_framebuffer(buffer: bytes) -> None:
    """Write bytes directly to /dev/fb0.
    
    Opens /dev/fb0 in binary write mode
    Seeks to offset (for partial updates)
    Writes RGB565 bytes
    Closes file
    """
```

---

## Data Flow Example: "User plays a song"

```
1. Volumio state changes
   {"status": "play", "title": "New Song", "artist": "New Artist", ...}

2. WebSocket server sends pushState message
   42["pushState",{...}]

3. media_players/volumio.py receive thread captures message
   Parses JSON → dict

4. Main loop receives state via queue
   current_state = {...}
   last_interaction = time.time()  # Reset idle timer

5. State machine compares with rendered_state
   states_are_equal(current_state, rendered_state) → False
   needs_render = True

6. If TEXT_MODE, render text layout
   renderer.render_text_mode(current_state)
   
   - Create PIL Image
   - Draw title, artist
   - Draw progress bar
   - Convert to RGB565 bytes

7. Write to framebuffer
   write_to_framebuffer(rgb565_bytes)

8. Display updates (40-60ms frame time)
   Pixels change on physical display

9. Loop back to receiving state
   (continues interpolating seek while waiting for next Volumio update)
```

---

## Key Design Decisions & Trade-offs

### Decision 1: Global State (not ideal, but pragmatic)
```python
# Why: Main event loop needs fast access to last states
# Trade-off: Harder to test, but mitigated by tests that mock
# Alternative: Could use asyncio.Queue (future work)
```

### Decision 2: Thread for WebSocket, Main Loop for Rendering
```python
# Why: WebSocket blocks on recv(), rendering needs timely updates
# Trade-off: Need thread-safe queue between them
# Alternative: Could use asyncio (but WebSocket library requires threading)
```

### Decision 3: Mock WebSocket for Tests (not real Volumio)
```python
# Why: Can't assume Volumio available during testing
# Trade-off: Doesn't test real Socket.io protocol nuances
# Alternative: Could containerize Volumio for CI (future)
```

### Decision 4: LRU Cache for Album Art (10 items)
```python
# Why: Fetching every frame kills network bandwidth
# Trade-off: Memory vs. freshness (5 min timeout helps)
# Alternative: Could use disk cache (but Raspberry Pi SD card wear)
```

### Decision 5: Framebuffer (not X11/Wayland)
```python
# Why: Lighter weight, no desktop environment needed
# Trade-off: Lower-level, less abstraction
# Alternative: Could use Qt/GTK (but overkill for simple display)
```

---

## Testing Architecture

**Mock Strategy**:
```python
# conftest.py injects MockWebSocket before media_players/volumio.py imports websocket
# This allows testing WebSocket logic without real server

# Key insight: monkeypatch must happen BEFORE import
# Otherwise media_players/volumio.py caches real websocket module
```

**State Machine Testing**:
```python
# Tests simulate full state transitions
# Verify:
#   - State equality logic (handles None fields)
#   - Pause/resume transition resets rendered_state
#   - Mode alternation timing
#   - Sleep/wake logic
#   - Seek interpolation for smooth progress bar
```

**Renderer Testing**:
```python
# Tests verify output format and edge cases
# Verify:
#   - Progress bar calculation and rendering
#   - Color extraction
#   - Cache behavior (LRU)
#   - Image resizing
#   - No crashes on missing album art
```

---

## Deployment Architecture

**Systemd Service** (`install.sh`):
```
[Unit]
After=network-online.target volumio.service
Wants=network-online.target

[Service]
ExecStart=/path/to/venv/bin/python /path/to/spi-now-playing.py
Restart=always
RestartSec=10
User=volumio
Group=video
SupplementaryGroups=video

[Install]
WantedBy=multi-user.target
```

**Why this design**:
- ✅ Survives reboot
- ✅ Restarts on crash (RestartSec=10)
- ✅ Respects Volumio startup order (After=volumio.service)
- ✅ Has framebuffer access (Group=video)
- ✅ Simple logging (journalctl)

---

## Future Improvements

1. **Async/await instead of threading**
   - Use asyncio for WebSocket (needs compatible library)
   - Cleaner concurrency model

2. **Global state refactor**
   - Use dataclass or pydantic for state objects
   - Better type safety

3. **Retry logic for WebSocket**
   - Exponential backoff on connection failure
   - Reconnect after N failures

4. **Configurable resolution**
   - Support different display sizes (not just 480×320)
   - Auto-detect via /proc/cmdline

5. **Additional display modes**
   - Visualizer mode (spectrum analyzer)
   - Clock mode (time display)
   - Rotating modes (auto-cycle)

6. **CI/CD Pipeline**
   - GitHub Actions for automated testing
   - Build container for Raspberry Pi testing
   - Auto-release on tag

7. **Performance monitoring**
   - Frame rate metrics
   - Memory usage tracking
   - Slow operation logging

---

**Architecture Document**: Updated March 2026
**Tested Components**: All (55+ tests)
**Production Ready**: Yes, deployed on Raspberry Pi 5
