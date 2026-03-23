"""Tests for MoodeClient skeleton.

Verifies that MoodeClient implements the MediaPlayer interface contract.
The actual implementation (HTTP polling, state normalization, etc.) is not
yet implemented and should be added by a future contributor.
"""

import pytest
import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def moode_client():
    """Create a MoodeClient for testing."""
    if 'media_players.moode' in sys.modules:
        del sys.modules['media_players.moode']
    from media_players.moode import MoodeClient
    return MoodeClient("http://localhost/engine-mpd.php")


def test_moode_client_is_media_player(moode_client):
    """MoodeClient implements the MediaPlayer interface."""
    from media_players.base import MediaPlayer
    assert isinstance(moode_client, MediaPlayer)


def test_moode_client_connect_not_implemented(moode_client):
    """MoodeClient.connect() is a stub (not yet implemented)."""
    result = moode_client.connect()
    assert result is False


def test_moode_client_receive_message_not_implemented(moode_client):
    """MoodeClient.receive_message() is a stub (not yet implemented)."""
    state = moode_client.receive_message(timeout=1.0)
    assert state is None


def test_moode_client_is_connected_false_by_default(moode_client):
    """MoodeClient.is_connected() returns False until connect() succeeds."""
    assert moode_client.is_connected() is False


def test_moode_client_close_succeeds(moode_client):
    """MoodeClient.close() is callable without error."""
    moode_client.close()
    # Should not raise


def test_moode_client_custom_url():
    """MoodeClient accepts a custom URL."""
    if 'media_players.moode' in sys.modules:
        del sys.modules['media_players.moode']
    from media_players.moode import MoodeClient
    client = MoodeClient(url="http://192.168.1.50/engine-mpd.php")
    assert client.url == "http://192.168.1.50/engine-mpd.php"
