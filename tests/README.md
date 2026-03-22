# Testing Guide for SPI Now Playing

## Test Coverage

This test suite covers the **critical functionality** of the application:

### 1. **Volumio API** (`test_volumio.py`)
Tests for WebSocket communication with Volumio:
- Parsing `pushState` messages
- Handling heartbeat responses
- Connection management
- **AirPlay edge case**: None values for seek/duration
- Malformed JSON error handling

### 2. **State Management** (`test_state_machine.py`)
Tests for the application state machine:
- State comparison logic (`states_are_equal`)
- Transitions: idle → playing → paused → stopped
- **Critical**: Pause/resume recovery (prevents black screen)
- Mode alternation (text vs artwork display)
- Seek interpolation for progress tracking
- Display sleep/wake behavior
- STANDBY_TIMEOUT handling

### 3. **Renderer Utilities** (`test_renderer.py`)
Tests for image and utility functions:
- Time formatting (mm:ss)
- Dominant color extraction from album art
- Album art caching with 10-item limit
- Image resizing
- Font loading and fallback

## Setup

### On Your Raspberry Pi (Recommended)
If testing on the actual Raspberry Pi, use a virtual environment:

```bash
cd /path/to/spi-now-playing
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-mock
```

### On macOS (Current Issue)
Due to Homebrew's PEP 668 restrictions, you may need:

```bash
# Option 1: Use uv (recommended, fast)
brew install uv
uv pip install pytest pytest-mock

# Option 2: Create a virtual environment
python3 -m venv venv
source venv/bin/activate
pip install pytest pytest-mock
```

## Running Tests

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/test_volumio.py -v

# Run specific test class
pytest tests/test_state_machine.py::TestStatesAreEqual -v

# Run with coverage report
pip install pytest-cov
pytest tests/ --cov=src --cov-report=html
```

## Test Strategy for Changes

When implementing Priority 1 fixes, follow this pattern:

1. **Run baseline tests first**
   ```bash
   pytest tests/ -v
   ```

2. **Make ONE change**
   - Example: Add type hints to single function

3. **Run tests again**
   ```bash
   pytest tests/ -v
   ```

4. **If tests pass**:
   - Commit the change
   - Move to next change

5. **If tests fail**:
   - Identify which test broke
   - Understand why
   - Fix the implementation
   - Re-run tests

## Critical Tests to Watch

These tests are most important for the quality changes:

### AirPlay Support (`test_volumio_airplay_none_values`)
Ensures that None seek/duration values (from AirPlay) don't crash the app.

### Pause/Resume (`test_paused_to_playing`)
Ensures pause and resume correctly transition between states without black screen.

### Mode Alternation (`test_mode_timing`)
Ensures display switches between artwork and technical info every 30 seconds.

### State Equality (`test_states_are_equal` family)
Core logic for detecting when to re-render the display.

## Mock Objects

The tests use mock objects to avoid requiring:
- Real Volumio server
- Real framebuffer device (/dev/fb0)  
- Real system calls

This makes tests fast and repeatable without hardware.

## Next Steps

1. Set up pytest in your environment (venv recommended)
2. Run: `pytest tests/ -v`
3. Gradually apply Priority 1 fixes
4. Run tests after each change
5. Commit only after tests pass
