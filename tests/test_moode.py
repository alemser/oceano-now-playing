"""Tests for the MoOde Audio client stub.

Verifies that MoodeClient correctly implements the MediaPlayer interface
and behaves as a safe, non-crashing stub until the transport layer is
implemented.
"""

import pytest
import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def moode_client():
    """Provide a fresh MoodeClient for each test."""
    if 'moode' in sys.modules:
        del sys.modules['moode']
    from moode import MoodeClient
    return MoodeClient()


def test_moode_client_is_media_player(moode_client):
    """MoodeClient is a subclass of MediaPlayer."""
    from media_player import MediaPlayer
    assert isinstance(moode_client, MediaPlayer)


def test_moode_client_connect_returns_false(moode_client):
    """MoodeClient.connect() returns False (stub not yet implemented)."""
    assert moode_client.connect() is False


def test_moode_client_not_connected_after_connect(moode_client):
    """MoodeClient.is_connected() returns False because the stub cannot connect."""
    moode_client.connect()
    assert moode_client.is_connected() is False


def test_moode_client_receive_message_returns_none(moode_client):
    """MoodeClient.receive_message() returns None (stub not yet implemented)."""
    assert moode_client.receive_message(timeout=0.1) is None


def test_moode_client_close_does_not_raise(moode_client):
    """MoodeClient.close() completes without raising an exception."""
    moode_client.close()  # should not raise


def test_moode_client_custom_url():
    """MoodeClient accepts a custom URL."""
    if 'moode' in sys.modules:
        del sys.modules['moode']
    from moode import MoodeClient
    client = MoodeClient(url="ws://192.168.1.50/moode")
    assert client.url == "ws://192.168.1.50/moode"
