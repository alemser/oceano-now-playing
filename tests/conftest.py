"""Shared test fixtures and mocks for SPI Now Playing tests."""

import pytest
from unittest.mock import MagicMock, patch
import json
import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class MockWebSocket:
    """Mock WebSocket for Volumio communication testing."""
    
    def __init__(self):
        self.sent_messages = []
        self.timeout_value = 1.0
        self._message_queue = []
        self._should_timeout = False
    
    def send(self, message):
        """Capture sent messages."""
        self.sent_messages.append(message)
    
    def recv(self):
        """Return mocked responses."""
        if self._should_timeout:
            raise TimeoutError("Socket timeout")
        if self._message_queue:
            return self._message_queue.pop(0)
        raise TimeoutError("No messages")
    
    def settimeout(self, timeout):
        """Store timeout value."""
        self.timeout_value = timeout
    
    def close(self):
        """Mock close."""
        pass
    
    def queue_message(self, message):
        """Add a message to be returned by recv()."""
        self._message_queue.append(message)
    
    def trigger_timeout(self):
        """Trigger timeout on next recv()."""
        self._should_timeout = True
    
    def clear_timeout(self):
        """Clear timeout flag."""
        self._should_timeout = False


@pytest.fixture
def mock_websocket():
    """Provide a mock WebSocket."""
    return MockWebSocket()


@pytest.fixture
def mock_framebuffer(tmp_path):
    """Provide a mock framebuffer file."""
    fb_file = tmp_path / "framebuffer"
    fb_file.write_bytes(b'\x00' * (480 * 320 * 2))  # RGB565 buffer
    return str(fb_file)


@pytest.fixture
def volumio_state_playing():
    """Volumio state for playing music."""
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
def volumio_state_paused(volumio_state_playing):
    """Volumio state for paused music."""
    state = volumio_state_playing.copy()
    state['status'] = 'pause'
    return state


@pytest.fixture
def volumio_state_stopped():
    """Volumio state for stopped playback."""
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
def volumio_state_airplay():
    """Volumio state for AirPlay streaming (None seek/duration)."""
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
def volumio_websocket_message_playing(volumio_state_playing):
    """WebSocket message format for playing state."""
    return f'42["pushState",{json.dumps(volumio_state_playing)}]'


@pytest.fixture
def volumio_websocket_message_paused(volumio_state_paused):
    """WebSocket message format for paused state."""
    return f'42["pushState",{json.dumps(volumio_state_paused)}]'


@pytest.fixture
def volumio_websocket_message_heartbeat():
    """WebSocket heartbeat message."""
    return '2'


@pytest.fixture
def volumio_websocket_message_heartbeat_response():
    """WebSocket heartbeat response."""
    return '3'


@pytest.fixture
def mock_volumio_client(mock_websocket, monkeypatch):
    """Provide a VolumioClient with mocked WebSocket."""
    # Create a mock websocket module
    mock_ws_module = MagicMock()
    mock_ws_module.create_connection = MagicMock(return_value=mock_websocket)
    mock_ws_module.WebSocketException = Exception
    
    # Inject mock websocket module BEFORE any import
    monkeypatch.setitem(sys.modules, 'websocket', mock_ws_module)
    
    # Remove volumio from cache to force reimport with mocked websocket
    if 'media_players.volumio' in sys.modules:
        del sys.modules['media_players.volumio']
    
    # Now import VolumioClient - it will use the mocked websocket
    from media_players.volumio import VolumioClient
    
    client = VolumioClient('ws://localhost:3000/socket.io/?EIO=3&transport=websocket')
    client.connect()
    return client, mock_websocket


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
