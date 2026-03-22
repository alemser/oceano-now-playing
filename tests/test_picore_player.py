"""Tests for the piCorePlayer client stub.

Verifies that PiCorePlayerClient correctly implements the MediaPlayer
interface and behaves as a safe, non-crashing stub until the LMS
transport layer is implemented.
"""

import pytest
import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def picore_client():
    """Provide a fresh PiCorePlayerClient for each test."""
    if 'picore_player' in sys.modules:
        del sys.modules['picore_player']
    from picore_player import PiCorePlayerClient
    return PiCorePlayerClient()


def test_picore_client_is_media_player(picore_client):
    """PiCorePlayerClient is a subclass of MediaPlayer."""
    from media_player import MediaPlayer
    assert isinstance(picore_client, MediaPlayer)


def test_picore_client_connect_returns_false(picore_client):
    """PiCorePlayerClient.connect() returns False (stub not yet implemented)."""
    assert picore_client.connect() is False


def test_picore_client_not_connected_after_connect(picore_client):
    """PiCorePlayerClient.is_connected() returns False because the stub cannot connect."""
    picore_client.connect()
    assert picore_client.is_connected() is False


def test_picore_client_receive_message_returns_none(picore_client):
    """PiCorePlayerClient.receive_message() returns None (stub not yet implemented)."""
    assert picore_client.receive_message(timeout=0.1) is None


def test_picore_client_close_does_not_raise(picore_client):
    """PiCorePlayerClient.close() completes without raising an exception."""
    picore_client.close()  # should not raise


def test_picore_client_custom_url():
    """PiCorePlayerClient accepts a custom URL."""
    if 'picore_player' in sys.modules:
        del sys.modules['picore_player']
    from picore_player import PiCorePlayerClient
    client = PiCorePlayerClient(url="ws://192.168.1.50:9000")
    assert client.url == "ws://192.168.1.50:9000"
