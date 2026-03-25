"""Shared test fixtures for oceano-now-playing tests."""

import pytest
from unittest.mock import MagicMock
import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def mock_framebuffer(tmp_path):
    """Provide a mock framebuffer file."""
    fb_file = tmp_path / "framebuffer"
    fb_file.write_bytes(b'\x00' * (480 * 320 * 2))  # RGB565 buffer
    return str(fb_file)


@pytest.fixture
def oceano_state_playing():
    """Oceano/AirPlay state for playing music."""
    return {
        'title': 'Test Song',
        'artist': 'Test Artist',
        'album': 'Test Album',
        'albumart': '/albumart?imageUrl=test.jpg',
        'status': 'play',
        'seek': 30000,
        'duration': 180000,
        'samplerate': '44.1 kHz',
        'bitdepth': '16 bit',
        'service': 'mpd'
    }


@pytest.fixture
def oceano_state_paused(oceano_state_playing):
    """Oceano/AirPlay state for paused music."""
    state = oceano_state_playing.copy()
    state['status'] = 'pause'
    return state


@pytest.fixture
def oceano_state_stopped():
    """Oceano/AirPlay state for stopped playback."""
    return {
        'title': '',
        'artist': '',
        'album': '',
        'albumart': '',
        'status': 'stop',
        'seek': 0,
        'duration': 0,
        'samplerate': '',
        'bitdepth': '',
        'service': 'mpd'
    }


@pytest.fixture
def oceano_state_airplay():
    """AirPlay state with None seek/duration (sparse metadata)."""
    return {
        'title': 'AirPlay Song',
        'artist': 'AirPlay Artist',
        'album': 'AirPlay Album',
        'albumart': '/albumart?imageUrl=airplay.jpg',
        'status': 'play',
        'seek': None,  # AirPlay doesn't provide seek
        'duration': None,  # AirPlay doesn't provide duration
        'samplerate': '44.1 kHz',
        'bitdepth': '16 bit',
        'service': 'airplay'
    }


@pytest.fixture
def mock_renderer(mock_framebuffer, monkeypatch):
    """Provide a Renderer with mocked framebuffer."""
    from renderer import Renderer
    
    # Mock file operations for framebuffer
    monkeypatch.setattr('os.path.exists', lambda x: x == mock_framebuffer)
    monkeypatch.setattr('builtins.open', lambda *args, **kwargs: MagicMock(spec=['seek', 'write', 'flush', 'close', 'tell', 'fileno']))
    
    renderer = Renderer(
        width=480,
        height=320,
        fb_device=mock_framebuffer,
        color_format='RGB565'
    )
    return renderer
