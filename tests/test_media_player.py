import tempfile
import json
import shutil
"""Tests for the MediaPlayer abstract base class, OceanoClient inheritance,
and the Oceano-only detect_media_player() factory function.

Verifies that:
- MediaPlayer cannot be instantiated directly (it is abstract)
- OceanoClient is a subclass of MediaPlayer
- All required abstract methods are implemented by OceanoClient
- detect_media_player() returns the Oceano implementation and coerces
    legacy MEDIA_PLAYER values safely
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
    if 'media_players.base' in sys.modules:
        del sys.modules['media_players.base']
    from media_players.base import MediaPlayer
    return MediaPlayer


@pytest.fixture
def oceano_client_class():
    """Import a fresh copy of OceanoClient for each test."""
    if 'media_players.oceano' in sys.modules:
        del sys.modules['media_players.oceano']

    from media_players.oceano import OceanoClient
    return OceanoClient


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


def test_oceano_client_is_media_player(media_player_class, oceano_client_class):
    """OceanoClient is a subclass of MediaPlayer."""
    assert issubclass(oceano_client_class, media_player_class)


def test_oceano_client_implements_all_abstract_methods(oceano_client_class):
    """OceanoClient implements every method required by MediaPlayer."""
    client = oceano_client_class('/tmp/shairport-sync-metadata')

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

def _load_detect_function():
    """Import detect_media_player and a fresh Config instance.

    The config is instantiated at runtime in main(), so we need to create a Config
    object here and pass it to detect_media_player(cfg).
    
    Returns:
        A tuple of (detect_media_player_function, Config_object)
    """
    for mod in (
        'media_players.oceano',
        'config',
        'oceano_now_playing',
        'app.main',
    ):
        sys.modules.pop(mod, None)
    
    # Import config module (not spi_now_playing yet)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'config',
        os.path.join(os.path.dirname(__file__), '..', 'src', 'config.py')
    )
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)
    
    # Now import the main module
    spec = importlib.util.spec_from_file_location(
        'oceano_now_playing',
        os.path.join(os.path.dirname(__file__), '..', 'src', 'oceano-now-playing.py')
    )
    main_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_module)
    
    # Create a config object (which picks up env vars via __post_init__)
    cfg = config_module.Config()
    
    return main_module.detect_media_player, cfg


def test_detect_media_player_default_returns_oceano(monkeypatch):
    """detect_media_player() returns an OceanoClient when MEDIA_PLAYER is unset."""
    monkeypatch.delenv('MEDIA_PLAYER', raising=False)
    fn, cfg = _load_detect_function()
    from media_players.oceano import OceanoClient
    player = fn(cfg)
    assert isinstance(player, OceanoClient)


def test_detect_media_player_oceano_explicit(monkeypatch):
    """detect_media_player() returns an OceanoClient when MEDIA_PLAYER=oceano."""
    monkeypatch.setenv('MEDIA_PLAYER', 'oceano')
    fn, cfg = _load_detect_function()
    from media_players.oceano import OceanoClient
    player = fn(cfg)
    assert isinstance(player, OceanoClient)


def test_detect_media_player_respects_external_artwork_flag(monkeypatch):
    """Explicit Oceano mode must propagate EXTERNAL_ARTWORK_ENABLED config."""
    monkeypatch.setenv('MEDIA_PLAYER', 'oceano')
    monkeypatch.setenv('EXTERNAL_ARTWORK_ENABLED', 'false')
    fn, cfg = _load_detect_function()
    from media_players.oceano import OceanoClient
    player = fn(cfg)
    assert isinstance(player, OceanoClient)
    assert player.external_artwork_enabled is False


def test_detect_media_player_coerces_legacy_backend_values(monkeypatch):
    """Legacy backend values are coerced to Oceano during migration."""
    monkeypatch.setenv('MEDIA_PLAYER', 'volumio')
    fn, cfg = _load_detect_function()
    import pytest
    with pytest.raises(ValueError):
        fn(cfg)


# ---------------------------------------------------------------------------
# OceanoAnalogClient tests
# ---------------------------------------------------------------------------

def test_oceano_analog_client_basic(tmp_path):
    """OceanoAnalogClient reads and parses the analog source file."""
    from media_players.oceano_analog import OceanoAnalogClient
    analog_file = tmp_path / "oceano-source.json"
    # Write initial state
    data = {"source": "Vinyl", "updated_at": "2026-03-27T00:24:39Z"}
    analog_file.write_text(json.dumps(data))
    client = OceanoAnalogClient(str(analog_file))
    assert client.connect() is True
    state = client.receive_message(timeout=0.1)
    assert state["title"] == "Analog source"
    assert state["quality"] == "Vinyl"
    assert state["status"] == "play"
    # Change to CD
    data = {"source": "CD", "updated_at": "2026-03-27T01:00:00Z"}
    analog_file.write_text(json.dumps(data))
    state = client.receive_message(timeout=0.1)
    assert state["quality"] == "CD"
    assert state["sample_rate"] == 44100
    # Change to Standby
    data = {"source": "Standby", "updated_at": "2026-03-27T02:00:00Z"}
    analog_file.write_text(json.dumps(data))
    state = client.receive_message(timeout=0.1)
    assert state["quality"] == "Standby"
    assert state["status"] == "stop"

    # Source is None (idle)
    data = {"source": None, "updated_at": "2026-03-27T03:00:00Z"}
    analog_file.write_text(json.dumps(data))
    state = client.receive_message(timeout=0.1)
    assert state["quality"] == "Standby"
    assert state["status"] == "stop"
    assert state["title"] == ""

    # Source missing (idle)
    data = {"updated_at": "2026-03-27T04:00:00Z"}
    analog_file.write_text(json.dumps(data))
    state = client.receive_message(timeout=0.1)
    assert state["quality"] == "Standby"
    assert state["status"] == "stop"
    assert state["title"] == ""


def test_detect_media_player_oceano_analog(monkeypatch, tmp_path):
    """detect_media_player() returns OceanoAnalogClient when MEDIA_PLAYER=oceano_analog."""
    analog_file = tmp_path / "oceano-source.json"
    analog_file.write_text(json.dumps({"source": "Vinyl", "updated_at": "2026-03-27T00:24:39Z"}))
    monkeypatch.setenv('MEDIA_PLAYER', 'oceano_analog')
    # Patch default path to our temp file
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'app_main',
        os.path.join(os.path.dirname(__file__), '..', 'src', 'app', 'main.py')
    )
    app_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_main)
    # Patch OceanoAnalogClient to use our temp file
    from media_players.oceano_analog import OceanoAnalogClient
    orig_init = OceanoAnalogClient.__init__
    def _patched_init(self, source_file=None):
        orig_init(self, str(analog_file))
    OceanoAnalogClient.__init__ = _patched_init
    from config import Config
    cfg = Config()
    player = app_main.detect_media_player(cfg)
    assert isinstance(player, OceanoAnalogClient)
    state = player.receive_message(timeout=0.1)
    assert state["quality"] == "Vinyl"
    # Restore
    OceanoAnalogClient.__init__ = orig_init
