"""Tests for MoodeClient HTTP polling implementation.

Verifies that MoodeClient:
- Connects to the HTTP API endpoint
- Polls and parses JSON responses
- Normalizes MoOde state to standard MediaPlayer format
- Detects state changes (change detection)
- Handles None/null/empty values gracefully
- Constructs album art URLs from relative paths
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def moode_response_playing():
    """MoOde API response for actively playing track."""
    return {
        "volume": "100",
        "state": "play",
        "title": "LR Channel And Phase",
        "artist": "Koz",
        "album": "Stereo Test",
        "elapsed": "45",
        "time": 128,
        "bitrate": "320 kbps",
        "encoded": "FLAC 16/48 kHz, 2ch",
        "coverurl": "/coverart.php/OSDISK%2FStereo%20Test%2FLRMonoPhase4.flac",
        "hidef": "yes",
        "output": "Playing",
    }


@pytest.fixture
def moode_response_paused():
    """MoOde API response for paused track."""
    return {
        "volume": "80",
        "state": "pause",
        "title": "Test Track",
        "artist": "Test Artist",
        "album": "Test Album",
        "elapsed": "30",
        "time": 200,
        "bitrate": "128 kbps",
        "encoded": "MP3 44.1 kHz, 2ch",
        "coverurl": "/coverart.php/test.mp3",
        "hidef": "no",
        "output": "Paused",
    }


@pytest.fixture
def moode_response_stopped():
    """MoOde API response for stopped state (no track)."""
    return {
        "volume": "100",
        "state": "stop",
        "title": "",
        "artist": "",
        "album": "",
        "elapsed": "",
        "time": None,
        "bitrate": "0 bps",
        "encoded": "",
        "coverurl": "/images/default-album-cover.png",
        "hidef": "no",
        "output": "Not playing",
    }


@pytest.fixture
def moode_response_no_cover():
    """MoOde API response with missing cover art."""
    return {
        "volume": "100",
        "state": "play",
        "title": "No Cover Track",
        "artist": "Artist",
        "album": "Album",
        "elapsed": "10",
        "time": 300,
        "bitrate": "320 kbps",
        "encoded": "FLAC 16/48 kHz, 2ch",
        "cover_art_hash": "getCoverHash(): no cover found",
        "coverurl": "/images/default-album-cover.png",
        "output": "Playing",
    }


@pytest.fixture
def moode_client():
    """Create a MoodeClient with mocked requests."""
    if 'moode' in sys.modules:
        del sys.modules['moode']
    from moode import MoodeClient
    return MoodeClient("http://localhost/engine-mpd.php")


def test_moode_client_is_media_player(moode_client):
    """MoodeClient is a subclass of MediaPlayer."""
    from media_player import MediaPlayer
    assert isinstance(moode_client, MediaPlayer)


def test_moode_client_connect_success(moode_client, moode_response_playing):
    """MoodeClient.connect() succeeds when API is reachable."""
    with patch('moode.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = moode_response_playing
        mock_get.return_value = mock_response

        assert moode_client.connect() is True
        assert moode_client.is_connected() is True
        mock_get.assert_called_once_with("http://localhost/engine-mpd.php", timeout=3)


def test_moode_client_connect_failure(moode_client):
    """MoodeClient.connect() fails gracefully when API is unreachable."""
    with patch('moode.requests.get') as mock_get:
        import requests
        mock_get.side_effect = requests.RequestException("Connection refused")

        assert moode_client.connect() is False
        assert moode_client.is_connected() is False


def test_moode_client_receive_message_requires_connection(moode_client):
    """MoodeClient.receive_message() returns None when not connected."""
    moode_client._connected = False
    state = moode_client.receive_message(timeout=1.0)
    assert state is None


def test_moode_client_receive_message_returns_state(moode_client, moode_response_playing):
    """MoodeClient.receive_message() returns normalized state on first poll."""
    moode_client._connected = True

    with patch('moode.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = moode_response_playing
        mock_get.return_value = mock_response

        state = moode_client.receive_message(timeout=1.0)

        assert state is not None
        assert state["title"] == "LR Channel And Phase"
        assert state["artist"] == "Koz"
        assert state["album"] == "Stereo Test"
        assert state["status"] == "play"
        assert state["seek"] == 45000  # 45 seconds in milliseconds
        assert state["duration"] == 128000  # 128 seconds in milliseconds


def test_moode_client_change_detection(moode_client, moode_response_playing, moode_response_paused):
    """MoodeClient only returns state when it changes (change detection)."""
    import time
    moode_client._connected = True

    with patch('moode.requests.get') as mock_get:
        # First poll: returns state
        mock_response = MagicMock()
        mock_response.json.return_value = moode_response_playing
        mock_get.return_value = mock_response

        state1 = moode_client.receive_message(timeout=1.0)
        assert state1 is not None

        # Second identical poll: should be rate-limited (no HTTP request)
        state2 = moode_client.receive_message(timeout=1.0)
        assert state2 is None

        # Wait for rate-limit interval to pass
        time.sleep(1.1)

        # Third poll with different state: returns new state
        mock_response.json.return_value = moode_response_paused
        state3 = moode_client.receive_message(timeout=1.0)
        assert state3 is not None
        assert state3["status"] == "pause"


def test_moode_client_normalize_state_playing(moode_client, moode_response_playing):
    """State normalization converts MoOde fields to standard format."""
    normalized = moode_client._normalize_state(moode_response_playing)

    assert normalized["title"] == "LR Channel And Phase"
    assert normalized["artist"] == "Koz"
    assert normalized["album"] == "Stereo Test"
    assert normalized["status"] == "play"
    assert normalized["seek"] == 45000  # 45 seconds in milliseconds
    assert normalized["duration"] == 128000  # 128 seconds in milliseconds
    assert normalized["quality"] == "FLAC 16/48 kHz, 2ch"
    assert normalized["volume"] == 100


def test_moode_client_normalize_state_stopped(moode_client, moode_response_stopped):
    """State normalization handles stopped/idle state."""
    normalized = moode_client._normalize_state(moode_response_stopped)

    assert normalized["status"] == "stop"
    assert normalized["title"] == ""
    assert normalized["artist"] == ""
    assert normalized["seek"] is None
    assert normalized["duration"] is None


def test_moode_client_normalize_state_paused(moode_client, moode_response_paused):
    """State normalization handles paused state with seek and duration."""
    normalized = moode_client._normalize_state(moode_response_paused)

    assert normalized["title"] == "Test Track"
    assert normalized["artist"] == "Test Artist"
    assert normalized["album"] == "Test Album"
    assert normalized["status"] == "pause"
    assert normalized["seek"] == 30000  # 30 seconds in milliseconds
    assert normalized["duration"] == 200000  # 200 seconds in milliseconds
    assert normalized["quality"] == "MP3 44.1 kHz, 2ch"
    assert normalized["volume"] == 80


def test_moode_client_empty_elapsed_returns_none_seek(moode_client):
    """Empty elapsed value is converted to None seek."""
    response = {
        "elapsed": "",
        "time": 300,
        "state": "stop",
        "title": "", "artist": "", "album": "",
    }
    normalized = moode_client._normalize_state(response)
    assert normalized["seek"] is None


def test_moode_client_null_time_returns_none_duration(moode_client):
    """Null time is converted to None duration."""
    response = {
        "elapsed": "10",
        "time": None,
        "state": "play",
        "title": "", "artist": "", "album": "",
    }
    normalized = moode_client._normalize_state(response)
    assert normalized["duration"] is None


def test_moode_client_album_art_url_construction(moode_client, moode_response_playing):
    """Relative cover art paths are converted to full URLs."""
    normalized = moode_client._normalize_state(moode_response_playing)

    assert normalized["albumart"] == "http://localhost/coverart.php/OSDISK%2FStereo%20Test%2FLRMonoPhase4.flac"


def test_moode_client_default_cover_skipped(moode_client, moode_response_no_cover):
    """Default cover image path is skipped (albumart is None)."""
    normalized = moode_client._normalize_state(moode_response_no_cover)

    assert normalized["albumart"] is None


def test_moode_client_bitrate_quality_fallback(moode_client):
    """Bitrate is used as quality if encoded is empty."""
    response = {
        "state": "play",
        "elapsed": "0",
        "time": 100,
        "bitrate": "192 kbps",
        "encoded": "",
        "title": "", "artist": "", "album": "",
    }
    normalized = moode_client._normalize_state(response)
    assert normalized["quality"] == "192 kbps"


def test_moode_client_zero_bitrate_skipped(moode_client):
    """Zero bitrate (stopped state) is skipped."""
    response = {
        "state": "stop",
        "elapsed": "",
        "time": None,
        "bitrate": "0 bps",
        "encoded": "",
        "title": "", "artist": "", "album": "",
    }
    normalized = moode_client._normalize_state(response)
    assert normalized["quality"] is None


def test_moode_client_close(moode_client):
    """MoodeClient.close() resets connection state."""
    moode_client._connected = True
    moode_client._last_state = {"title": "Test"}

    moode_client.close()

    assert moode_client._connected is False
    assert moode_client._last_state is None


def test_moode_client_custom_url():
    """MoodeClient accepts a custom URL."""
    if 'moode' in sys.modules:
        del sys.modules['moode']
    from moode import MoodeClient
    client = MoodeClient(url="ws://192.168.1.50/moode")
    assert client.url == "ws://192.168.1.50/moode"


def test_moode_client_rate_limiting(moode_client, moode_response_playing):
    """Rapid receive_message() calls are rate-limited to avoid excessive HTTP requests."""
    import time
    from unittest.mock import patch
    
    moode_client._connected = True
    
    with patch('moode.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = moode_response_playing
        mock_get.return_value = mock_response
        
        # First call should make HTTP request
        state1 = moode_client.receive_message(timeout=0.1)
        assert state1 is not None
        assert mock_get.call_count == 1
        
        # Rapid second call should NOT make HTTP request (rate-limited)
        state2 = moode_client.receive_message(timeout=0.1)
        assert state2 is None  # No state change (we were rate-limited)
        assert mock_get.call_count == 1  # Still only 1 HTTP request
        
        # Wait for rate-limit interval, then next call should make HTTP request
        time.sleep(1.1)
        state3 = moode_client.receive_message(timeout=0.1)
        # state3 is None because nothing changed, but HTTP request was made
        assert mock_get.call_count == 2  # Now 2 HTTP requests


def test_moode_client_poll_time_reset_on_connect(moode_client, moode_response_playing):
    """connect() resets poll time to allow immediate first poll."""
    from unittest.mock import patch
    
    moode_client._last_poll_time = 100.0  # Simulate old poll time
    
    with patch('moode.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = moode_response_playing
        mock_get.return_value = mock_response
        
        moode_client.connect()
        
        # Poll time should be reset to 0.0
        assert moode_client._last_poll_time == 0.0
        
        # First receive_message after connect should work immediately
        state = moode_client.receive_message(timeout=0.1)
        assert state is not None  # Should get state without waiting


def test_moode_client_poll_time_reset_on_close(moode_client):
    """close() resets poll time."""
    moode_client._last_poll_time = 100.0
    
    moode_client.close()
    
    assert moode_client._last_poll_time == 0.0
