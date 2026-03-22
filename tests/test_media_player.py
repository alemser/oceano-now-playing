"""Tests for the MediaPlayer abstract base class, VolumioClient inheritance,
and the detect_media_player() factory function.

Verifies that:
- MediaPlayer cannot be instantiated directly (it is abstract)
- VolumioClient is a subclass of MediaPlayer
- All required abstract methods are implemented by VolumioClient
- detect_media_player() returns the correct implementation for each
  value of the MEDIA_PLAYER environment variable
"""

import pytest
import sys
import os
from unittest.mock import MagicMock

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def media_player_class():
    """Import a fresh copy of MediaPlayer for each test."""
    if 'media_player' in sys.modules:
        del sys.modules['media_player']
    from media_player import MediaPlayer
    return MediaPlayer


@pytest.fixture
def volumio_client_class(monkeypatch):
    """Import VolumioClient with a mocked websocket module."""
    mock_ws_module = MagicMock()
    mock_ws_module.WebSocketException = Exception
    monkeypatch.setitem(sys.modules, 'websocket', mock_ws_module)

    if 'volumio' in sys.modules:
        del sys.modules['volumio']

    from volumio import VolumioClient
    return VolumioClient


def test_media_player_is_abstract(media_player_class):
    """MediaPlayer cannot be instantiated directly because it is abstract."""
    with pytest.raises(TypeError):
        media_player_class()


def test_media_player_abstract_methods(media_player_class):
    """MediaPlayer declares the four required abstract methods."""
    abstract_methods = media_player_class.__abstractmethods__
    assert 'connect' in abstract_methods
    assert 'receive_message' in abstract_methods
    assert 'is_connected' in abstract_methods
    assert 'close' in abstract_methods


def test_volumio_client_is_media_player(media_player_class, volumio_client_class):
    """VolumioClient is a subclass of MediaPlayer."""
    assert issubclass(volumio_client_class, media_player_class)


def test_volumio_client_implements_all_abstract_methods(volumio_client_class):
    """VolumioClient implements every method required by MediaPlayer."""
    client = volumio_client_class('ws://localhost:3000')

    assert callable(getattr(client, 'connect', None))
    assert callable(getattr(client, 'receive_message', None))
    assert callable(getattr(client, 'is_connected', None))
    assert callable(getattr(client, 'close', None))


def test_concrete_subclass_must_implement_all_methods(media_player_class):
    """A subclass missing any abstract method cannot be instantiated."""
    class IncompletePlayer(media_player_class):
        def connect(self) -> bool:
            return True
        # receive_message, is_connected, close are intentionally missing

    with pytest.raises(TypeError):
        IncompletePlayer()


def test_concrete_subclass_with_all_methods_can_be_instantiated(media_player_class):
    """A complete subclass implementing all abstract methods can be instantiated."""
    class DummyPlayer(media_player_class):
        def connect(self) -> bool:
            return True

        def receive_message(self, timeout: float) -> dict | None:
            return None

        def is_connected(self) -> bool:
            return False

        def close(self) -> None:
            pass

    player = DummyPlayer()
    assert isinstance(player, media_player_class)
    assert player.connect() is True
    assert player.receive_message(1.0) is None
    assert player.is_connected() is False
    player.close()  # should not raise


# ---------------------------------------------------------------------------
# detect_media_player() factory tests
# ---------------------------------------------------------------------------

def _load_detect_function(monkeypatch, mock_ws_module):
    """Helper: inject websocket mock and return detect_media_player.

    The main module reads MEDIA_PLAYER_TYPE at import time, so the module
    must be reloaded after setting the environment variable to pick up the
    new value.
    """
    monkeypatch.setitem(sys.modules, 'websocket', mock_ws_module)
    for mod in ('volumio', 'moode', 'picore_player', 'spi_now_playing'):
        sys.modules.pop(mod, None)
    # The main module uses a hyphen in its filename; import via importlib
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'spi_now_playing',
        os.path.join(os.path.dirname(__file__), '..', 'src', 'spi-now-playing.py')
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.detect_media_player


def test_detect_media_player_default_returns_volumio(monkeypatch):
    """detect_media_player() returns a VolumioClient when MEDIA_PLAYER is unset."""
    monkeypatch.delenv('MEDIA_PLAYER', raising=False)
    mock_ws_module = MagicMock()
    mock_ws_module.WebSocketException = Exception
    mock_ws_module.create_connection = MagicMock()
    fn = _load_detect_function(monkeypatch, mock_ws_module)
    from volumio import VolumioClient
    player = fn()
    assert isinstance(player, VolumioClient)


def test_detect_media_player_volumio_explicit(monkeypatch):
    """detect_media_player() returns a VolumioClient when MEDIA_PLAYER=volumio."""
    monkeypatch.setenv('MEDIA_PLAYER', 'volumio')
    mock_ws_module = MagicMock()
    mock_ws_module.WebSocketException = Exception
    mock_ws_module.create_connection = MagicMock()
    fn = _load_detect_function(monkeypatch, mock_ws_module)
    from volumio import VolumioClient
    player = fn()
    assert isinstance(player, VolumioClient)


def test_detect_media_player_moode(monkeypatch):
    """detect_media_player() returns a MoodeClient when MEDIA_PLAYER=moode."""
    monkeypatch.setenv('MEDIA_PLAYER', 'moode')
    mock_ws_module = MagicMock()
    mock_ws_module.WebSocketException = Exception
    fn = _load_detect_function(monkeypatch, mock_ws_module)
    from moode import MoodeClient
    player = fn()
    assert isinstance(player, MoodeClient)


def test_detect_media_player_picore(monkeypatch):
    """detect_media_player() returns a PiCorePlayerClient when MEDIA_PLAYER=picore."""
    monkeypatch.setenv('MEDIA_PLAYER', 'picore')
    mock_ws_module = MagicMock()
    mock_ws_module.WebSocketException = Exception
    fn = _load_detect_function(monkeypatch, mock_ws_module)
    from picore_player import PiCorePlayerClient
    player = fn()
    assert isinstance(player, PiCorePlayerClient)
