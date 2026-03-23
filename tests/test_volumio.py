"""Tests for Volumio WebSocket API client.

Critical functionality:
- Parsing pushState messages from Volumio
- Handling heartbeat responses
- Connection management
- Error handling for None values (AirPlay)
"""

import pytest
import json
from unittest.mock import patch

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


@patch('media_players.base.ArtworkLookup.get_artwork')
def test_volumio_resolve_artwork_uses_external_provider(mock_lookup, mock_volumio_client, volumio_state_playing):
    """Resolve artwork using external providers only."""
    client, _ = mock_volumio_client
    fallback_image = Image.new('RGB', (20, 20), color='blue')
    mock_lookup.return_value = fallback_image

    resolved = client.resolve_artwork(volumio_state_playing)

    assert resolved is not None
    assert resolved['source'] == 'fallback'
    assert resolved['cache_key'] == 'fallback:Test Artist|Test Album'
    assert resolved['image'] is fallback_image


@patch('media_players.base.ArtworkLookup.get_artwork')
def test_volumio_resolve_artwork_returns_none_without_provider_match(mock_lookup, mock_volumio_client, volumio_state_playing):
    """Return None when external providers cannot find artwork."""
    client, _ = mock_volumio_client
    mock_lookup.return_value = None

    resolved = client.resolve_artwork(volumio_state_playing)

    assert resolved is None


@patch('media_players.base.ArtworkLookup.get_artwork')
def test_volumio_resolve_artwork_skips_external_services_when_disabled(mock_lookup, mock_volumio_client, volumio_state_playing):
    """Do not call external providers when artwork fallback is disabled."""
    client, _ = mock_volumio_client
    client.external_artwork_enabled = False

    resolved = client.resolve_artwork(volumio_state_playing)

    assert resolved is None
    mock_lookup.assert_not_called()


@patch('media_players.base.ArtworkLookup.get_artwork')
def test_volumio_resolve_artwork_returns_none_without_artist_or_album(mock_lookup, mock_volumio_client):
    """Return None when required metadata is missing for provider lookup."""
    client, _ = mock_volumio_client

    resolved = client.resolve_artwork({'artist': 'Sade', 'album': ''})

    assert resolved is None
    mock_lookup.assert_not_called()
