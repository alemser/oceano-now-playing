# Copilot Instructions for spi-now-playing

## 🎯 Project Overview
**spi-now-playing** displays Volumio's current playing status (title, artist, album, artwork, quality) on an SPI-connected display for Raspberry Pi 5.

- **Hardware**: Raspberry Pi 5 with generic SPI framebuffer display (normally a 3.5 inch 480×320, RGB565)
- **Target Platform**: Volumio (music server running on localhost:3000)
- **Display Output**: Linux framebuffer via PIL (`/dev/fb0`)
- **Architecture**: Event-driven state machine + WebSocket listener

## 📁 Project Structure Explained

```
src/
├── spi-now-playing.py      # Main controller (state machine, signal handlers, ~400 lines)
├── volumio.py              # WebSocket client for Volumio API (Socket.io protocol)
└── renderer.py             # Display rendering via PIL to framebuffer

tests/
├── conftest.py             # Shared fixtures, MockWebSocket class
├── test_volumio.py         # 12 WebSocket API tests
├── test_state_machine.py   # 20+ state management tests
└── test_renderer.py        # 15+ utility function tests (~55 total)

Configuration/
├── pyproject.toml          # Project metadata + dependencies (PEP 517/518)
├── requirements.txt        # Runtime only: Pillow, numpy, spidev, websocket-client, etc.
├── requirements-dev.txt    # Dev only: pytest, pytest-mock
├── setup.sh                # Dev environment setup (creates venv, installs deps, git hooks)
├── install.sh              # Production Raspberry Pi deployment
├── Makefile                # Test commands (make test, make push, etc.)
└── .editorconfig           # Code style consistency
```

## 🔑 Key Components & Patterns

### 1. **WebSocket Client** (`volumio.py`)
**Pattern**: Socket.io protocol with heartbeat handling

```python
# What it does:
- Connects to ws://localhost:3000/socket.io/?EIO=3&transport=websocket
- Handles pushState messages: {"title": "...", "artist": "...", "status": "play", ...}
- Handles heartbeat: receives '2', responds with '3'
- Parses JSON from Socket.io frame format: 42["pushState",{...}]

# Critical: Handle None values
- AirPlay sends seek=None, duration=None (don't crash!)
- Tests verify this in test_volumio_airplay_none_values
```

**When to use AI help**: 
- Adding new Volumio state fields
- Handling new message types
- Connection error recovery

### 2. **State Machine** (`spi-now-playing.py`)
**Pattern**: Track display state, handle transitions, manage timing

```python
# States:
- IDLE: No music playing, display sleeps after STANDBY_TIMEOUT (5 min)
- PLAYING/PAUSED/STOPPED: Music-related states

# Critical behaviors:
- Pause/resume: Must reset `rendered_state` to avoid black screen
- Mode alternation: Every CYCLE_TIME (30s), toggle between text + metadata OR artwork
- Display sleep: After 5 min idle, power down display (STANDBY_TIMEOUT)
- Seek interpolation: For smooth progress display between Volumio updates

# Global state (not ideal, but tested):
global rendered_state, current_mode, last_mode_change, last_state_update
```

**When to use AI help**:
- New display modes or timing rules
- State transition edge cases
- Signal handler improvements

### 3. **Renderer** (`renderer.py`)
**Pattern**: Convert state → PIL image → framebuffer bytes

```python
# Key functions:
- _get_dominant_color(image) → RGB tuple (for theme extraction)
- Renderer class:
  - cache_album_art()        → 10-item LRU cache (auto-clear on overflow)
  - render_text_mode()       → Title + artist + quality + progress bar
  - render_artwork_mode()    → Album art centered + progress bar
  - render_idle_screen()     → "Waiting for Volumio..."

# Framebuffer:
- 480×320 pixels, RGB565 format (2 bytes per pixel)
- Writes directly to /dev/fb0

# NOTE: Time displays (MM:SS) not in scope for this phase.
# Progress bar is the key indicator of playback position.
```

**When to use AI help**:
- Display layout improvements
- Color/font handling
- Image processing edge cases

## 🧪 Testing Philosophy

### Test Organization
```python
# 55 tests total, organized by module:

tests/test_volumio.py (12 tests)
  - test_volumio_connect_success        → MockWebSocket captures sent messages
  - test_volumio_airplay_none_values    → CRITICAL: None handling
  - test_volumio_receive_*              → JSON parsing edge cases
  - test_volumio_malformed_json         → Error handling

tests/test_state_machine.py (20+ tests)
  - TestStatesAreEqual                  → State comparison with quality/albumart
  - TestPlaybackStateTransitions        → State machine transitions
  - TestAirPlayHandling                 → None value safety
  - TestSeekInterpolation               → Smooth progress calculation
  - TestModeAlternation                 → 30s cycle timing
  - TestDisplayStates                   → Sleep/wake logic

tests/test_renderer.py (15+ tests)
  - test_dominant_color_*               → Color extraction
  - test_cache_album_art_*              → LRU cache behavior
  - test_image_resizing_*               → PIL operations
  - test_progress_bar_*                 → Progress bar rendering and seek interpolation
```

### Mock Strategy
```python
# conftest.py provides:
- MockWebSocket class       → Queues messages, captures sends, simulates timeouts
- mock_volumio_client      → Injects MockWebSocket before importing VolumioClient
- Fixtures for states      → volumio_state_playing, volumio_state_airplay, etc.
- Message fixtures         → volumio_websocket_message_playing, etc.

# Why monkeypatch + sys.modules?
- socketio imports websocket at module load time
- Must inject mock BEFORE importing volumio.py
- Delete volumio from sys.modules between tests for isolation
```

## ✅ Code Standards

### Type Hints (Required)
```python
# All public functions must have type hints:
def receive_message(self, timeout: float = 1.0) -> dict | None:
    """Receive and parse WebSocket message."""
    ...

def _get_dominant_color(image: PIL.Image) -> tuple:
    """Extract dominant color from album art for theme."""
    ...
```

### Docstrings (Required)
```python
def connect(self) -> bool:
    """Connects to Volumio's WebSocket.
    
    Returns:
        True if connection successful, False otherwise.
    """
```

### Exception Handling (No Bare `except`)
```python
# ❌ WRONG:
try:
    self.ws.send('42["getState"]')
except:
    self.ws = None

# ✅ RIGHT:
try:
    self.ws.send('42["getState"]')
except (TimeoutError, ConnectionError) as e:
    logger.error(f"Send failed: {e}")
    self.ws = None
```

### Context Managers (For Resources)
```python
# ✅ When dealing with files/sockets:
with open(self.framebuffer_path, 'r+b') as fb:
    fb.seek(offset)
    fb.write(buffer)
```

## 🎲 Critical Functionality (Test Before Coding)

### Must Not Break These
1. **WebSocket Connection** - Volumio communication is essential
   - Test: `test_volumio_connect_success`
   - Test: `test_volumio_receive_playing_state`

2. **Pause/Resume** - Users expect music to resume without black screen
   - Test: `test_paused_to_playing`
   - Code: Reset `rendered_state` on pause→resume transition

3. **AirPlay Safety** - Spotify Connect sends None for seek/duration
   - Test: `test_volumio_airplay_none_values`
   - Test: `test_airplay_none_seek_duration`
   - Code: Check `if seek is not None` before using

4. **Display Sleep** - Must not stay on after 5 min idle
   - Test: `test_go_to_sleep_after_timeout`
   - Code: STANDBY_TIMEOUT = 300 seconds

5. **Mode Alternation** - Every 30s toggle text ↔ artwork
   - Test: `test_mode_timing`
   - Code: CYCLE_TIME = 30 seconds

## 🔄 Before Writing Code

1. **Check existing tests** - Read `tests/test_*.py` first
2. **Run test suite** - `make test` (should show 55 passed)
3. **Understand the change impact** - Will it affect state machine? WebSocket? Display?
4. **Write/update tests** - Test first, then code
5. **Run tests again** - `make test` must pass

## 🚀 Testing Commands

```bash
# Quick validation
make test                    # Run all 55 tests (quiet output)

# Detailed feedback
make test-verbose            # Full output + failures

# Specific test suites
make test-volumio            # WebSocket API only
make test-state              # State machine only
make test-renderer           # Display utilities only

# Before pushing
make push                    # Git push (pre-push hook runs tests)
make test-push               # Run tests, push if pass
```

## 📋 Code Review Checklist (For AI Suggestions)

When suggesting code changes:
- [ ] All functions have type hints
- [ ] All public functions have docstrings
- [ ] No bare `except:` blocks
- [ ] Error messages are logged (not silent failures)
- [ ] Existing tests still pass
- [ ] New functionality has tests
- [ ] Code matches project patterns (see existing files)
- [ ] Changes don't affect Raspberry Pi deployment
- [ ] Variable names match project conventions (see source files)

## 🎯 Common Tasks & Patterns

### Adding a New Volumio State Field
```python
# 1. Update test fixture in conftest.py:
@pytest.fixture
def volumio_state_playing():
    return {'title': '...', 'someNewField': 'value', ...}

# 2. Update receive_message parser in volumio.py:
if '"pushState"' in result:
    json_str = result[start:end+1]
    state = json.loads(json_str)
    return state  # New field automatically included

# 3. Test it:
def test_volumio_new_field(mock_volumio_client):
    mock_ws.queue_message(volumio_websocket_message_playing)
    state = client.receive_message(timeout=0.1)
    assert state['someNewField'] == 'value'
```

### Handling New Display States
```python
# 1. Update state machine logic in spi-now-playing.py
# 2. Add test:
def test_new_state_transition():
    # Setup old state
    # Trigger transition
    # Assert new state reached

# 3. Update renderer if display changes
# 4. Run: make test
```

## 🐛 Debugging Tips

**WebSocket not responding?**
- Check Volumio is running: http://localhost:3000
- Check logs: `journalctl -u volumio.service -f`
- Test connection: `make test-volumio -v`

**Display not updating?**
- Check `/dev/fb0` exists: `ls -la /dev/fb0`
- Check permissions: `groups` (should include `video` group)
- Check `rendered_state` is reset on transitions
- Run: `make test-state -v`

**Tests failing?**
- Check virtual environment: `source venv/bin/activate`
- Reinstall deps: `pip install -r requirements.txt -r requirements-dev.txt`
- Run verbose: `make test-verbose`

## 📚 Key Files to Review First

1. **src/volumio.py** - WebSocket protocol understanding
2. **src/spi-now-playing.py** - State machine + global state
3. **tests/conftest.py** - Mock strategy + fixtures
4. **tests/test_volumio.py** - WebSocket test patterns
5. **tests/test_state_machine.py** - State transition testing

## 🎓 Development Best Practices

- **Test First**: Write test, make it pass, then refactor
- **Small Changes**: One feature per commit
- **Run Tests**: Before every push (hook does this)
- **Commit Messages**: Clear, describe the why not the what
- **Review Tests**: If test fails, fix test + code together
- **Document Edge Cases**: Add comments for AirPlay, None values, timeouts

---

**Last Updated**: March 2026
**Test Coverage**: 55+ passing tests
**Python Version**: 3.8+
**Lead Maintainer**: alemser
