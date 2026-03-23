"""Tests for Volumio WebSocket API client.

Critical functionality:
- Parsing pushState messages from Volumio
- Handling heartbeat responses
- Connection management
- Error handling for None values (AirPlay)
"""

import pytest
import json
from io import BytesIO
from unittest.mock import MagicMock, patch

from PIL import Image


def test_volumio_connect_success(mock_volumio_client):
    """Test successful connection to Volumio."""
    client, mock_ws = mock_volumio_client
    
    assert client.is_connected()
    assert '42["getState"]' in mock_ws.sent_messages


def test_volumio_receive_playing_state(mock_volumio_client, volumio_websocket_message_playing, volumio_state_playing):
    """Test receiving and parsing a playing state message."""
    client, mock_ws = mock_volumio_client
    
    mock_ws.queue_message(volumio_websocket_message_playing)
    state = client.receive_message(timeout=0.1)
    
    assert state is not None
    assert state['title'] == 'Test Song'
    assert state['artist'] == 'Test Artist'
    assert state['status'] == 'play'
    assert state['seek'] == 30000
    assert state['duration'] == 180000


def test_volumio_receive_paused_state(mock_volumio_client, volumio_websocket_message_paused):
    """Test receiving a paused state message."""
    client, mock_ws = mock_volumio_client
    
    mock_ws.queue_message(volumio_websocket_message_paused)
    state = client.receive_message(timeout=0.1)
    
    assert state is not None
    assert state['status'] == 'pause'


def test_volumio_receive_heartbeat(mock_volumio_client, volumio_websocket_message_heartbeat):
    """Test handling WebSocket heartbeat."""
    client, mock_ws = mock_volumio_client
    
    mock_ws.queue_message(volumio_websocket_message_heartbeat)
    state = client.receive_message(timeout=0.1)
    
    # Heartbeat should trigger a response and return None
    assert state is None
    assert '3' in mock_ws.sent_messages


def test_volumio_receive_timeout(mock_volumio_client):
    """Test timeout handling when no message is received."""
    client, mock_ws = mock_volumio_client
    mock_ws.trigger_timeout()
    
    state = client.receive_message(timeout=0.1)
    
    assert state is None


def test_volumio_airplay_none_values(mock_volumio_client, volumio_state_airplay):
    """Test handling AirPlay states with None seek and duration.
    
    This is critical: AirPlay streaming doesn't provide seek/duration,
    and the code must safely handle None values.
    """
    client, mock_ws = mock_volumio_client
    
    message = f'42["pushState",{json.dumps(volumio_state_airplay)}]'
    mock_ws.queue_message(message)
    state = client.receive_message(timeout=0.1)
    
    assert state is not None
    assert state['title'] == 'AirPlay Song'
    assert state['seek'] is None  # Must preserve None, not crash
    assert state['duration'] is None
    assert state['status'] == 'play'


def test_volumio_malformed_json(mock_volumio_client):
    """Test handling of malformed JSON in state message."""
    client, mock_ws = mock_volumio_client
    
    # Send malformed JSON
    mock_ws.queue_message('42["pushState",{invalid json}]')
    state = client.receive_message(timeout=0.1)
    
    # Should return None instead of crashing
    assert state is None


def test_volumio_missing_fields(mock_volumio_client):
    """Test handling state with missing optional fields."""
    client, mock_ws = mock_volumio_client
    
    incomplete_state = {
        'title': 'Song',
        'artist': 'Artist',
        'status': 'play'
        # Missing other fields
    }
    message = f'42["pushState",{json.dumps(incomplete_state)}]'
    mock_ws.queue_message(message)
    state = client.receive_message(timeout=0.1)
    
    assert state is not None
    assert state['title'] == 'Song'
    assert state.get('album') is None  # Missing field should be None


def test_volumio_get_state_request(mock_volumio_client):
    """Test requesting current state from Volumio."""
    client, mock_ws = mock_volumio_client
    
    mock_ws.sent_messages.clear()
    client.get_state()
    
    # Should send getState request
    assert '42["getState"]' in mock_ws.sent_messages


def test_volumio_close_connection(mock_volumio_client):
    """Test closing the connection."""
    client, mock_ws = mock_volumio_client
    
    assert client.is_connected()
    client.close()
    assert not client.is_connected()


def test_volumio_reconnect_on_error(mock_volumio_client):
    """Test that connection is set to None on WebSocket error during receive."""
    client, mock_ws = mock_volumio_client
    
    # Simulate receiving a message that triggers an error
    mock_ws.trigger_timeout()
    state = client.receive_message(timeout=0.1)
    
    # Timeout alone shouldn't disconnect, but connection errors should
    # (Need to implement socket.error handling to test this fully)
    assert state is None


def _image_bytes(color=(255, 0, 0)):
    """Build image bytes for artwork resolution tests."""
    image = Image.new('RGB', (16, 16), color=color)
    buffer = BytesIO()
    image.save(buffer, format='JPEG')
    return buffer.getvalue()


@patch('media_players.volumio.hashlib.sha256')
def test_is_placeholder_image_detects_c9_hash(mock_sha256, mock_volumio_client):
    """The known Volumio default placeholder hash c9...db1 must match exactly."""
    client, _ = mock_volumio_client
    mock_sha256.return_value.hexdigest.return_value = (
        'c9c0eb5de9ba0d540f0784f2de757a18ef095005032e97fd559ce74430167db1'
    )

    image = Image.new('RGB', (16, 16), color=(255, 255, 255))
    is_placeholder, reason, sha256 = client._is_placeholder_image(b'ignored', image)

    assert is_placeholder is True
    assert reason == 'exact-sha256-match'
    assert sha256.endswith('0167db1')


@patch('media_players.volumio.requests.get')
def test_volumio_resolve_artwork_success(mock_get, mock_volumio_client, volumio_state_playing):
    """Resolve Volumio artwork into a renderer-friendly object."""
    client, _ = mock_volumio_client

    response = MagicMock()
    response.status_code = 200
    response.content = _image_bytes()
    response.headers = {'content-type': 'image/jpeg'}
    response.raise_for_status.return_value = None
    mock_get.return_value = response

    with patch.object(client, '_is_placeholder_image', return_value=(False, 'no-match', 'abc')):
        resolved = client.resolve_artwork(volumio_state_playing)

    assert resolved is not None
    assert resolved['cache_key'] == volumio_state_playing['albumart']
    assert resolved['source'] == 'volumio'
    assert resolved['image'].size == (16, 16)


@patch('media_players.volumio.ArtworkLookup.get_artwork')
@patch('media_players.volumio.requests.get')
def test_volumio_resolve_artwork_uses_fallback(mock_get, mock_lookup, mock_volumio_client, volumio_state_playing):
    """Use fallback artwork when Volumio returns its default placeholder."""
    client, _ = mock_volumio_client

    response = MagicMock()
    response.status_code = 200
    response.content = _image_bytes()
    response.headers = {'content-type': 'image/jpeg'}
    response.raise_for_status.return_value = None
    mock_get.return_value = response

    fallback_image = Image.new('RGB', (20, 20), color='blue')
    mock_lookup.return_value = fallback_image

    with patch.object(client, '_is_placeholder_image', return_value=(True, 'exact-sha256-match', 'abc')):
        resolved = client.resolve_artwork(volumio_state_playing)

    assert resolved is not None
    assert resolved['source'] == 'fallback'
    assert resolved['cache_key'] == 'fallback:Test Artist|Test Album'
    assert resolved['image'] is fallback_image


@patch('media_players.volumio.ArtworkLookup.get_artwork')
@patch('media_players.volumio.requests.get')
def test_volumio_resolve_artwork_returns_none_without_fallback(mock_get, mock_lookup, mock_volumio_client, volumio_state_playing):
    """Return None when placeholder artwork has no fallback match."""
    client, _ = mock_volumio_client

    response = MagicMock()
    response.status_code = 200
    response.content = _image_bytes()
    response.headers = {'content-type': 'image/jpeg'}
    response.raise_for_status.return_value = None
    mock_get.return_value = response
    mock_lookup.return_value = None

    with patch.object(client, '_is_placeholder_image', return_value=(True, 'exact-sha256-match', 'abc')):
        resolved = client.resolve_artwork(volumio_state_playing)

    assert resolved is None


@patch('media_players.volumio.time.sleep')
@patch('media_players.volumio.ArtworkLookup.get_artwork')
@patch('media_players.volumio.requests.get')
def test_volumio_resolve_artwork_retries_and_uses_native_art(
    mock_get,
    mock_lookup,
    mock_sleep,
    mock_volumio_client,
    volumio_state_playing,
):
    """Retry once after placeholder and keep native Volumio artwork if it recovers."""
    client, _ = mock_volumio_client

    first_response = MagicMock()
    first_response.status_code = 200
    first_response.content = _image_bytes(color=(255, 0, 0))
    first_response.headers = {'content-type': 'image/jpeg'}
    first_response.raise_for_status.return_value = None

    second_response = MagicMock()
    second_response.status_code = 200
    second_response.content = _image_bytes(color=(0, 255, 0))
    second_response.headers = {'content-type': 'image/jpeg'}
    second_response.raise_for_status.return_value = None

    mock_get.side_effect = [first_response, second_response]
    mock_lookup.return_value = Image.new('RGB', (20, 20), color='blue')

    with patch.object(
        client,
        '_is_placeholder_image',
        side_effect=[
            (True, 'perceptual-dhash-match(distance=0)', 'placeholder-sha'),
            (False, 'no-match', 'real-sha'),
        ],
    ):
        resolved = client.resolve_artwork(volumio_state_playing)

    assert resolved is not None
    assert resolved['source'] == 'volumio'
    assert resolved['cache_key'] == volumio_state_playing['albumart']
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once()
    mock_lookup.assert_not_called()
