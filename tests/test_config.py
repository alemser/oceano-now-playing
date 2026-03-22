"""Tests for the Config class.

Verifies that:
- Config loads environment variables correctly
- Config validates settings appropriately
- Invalid configurations raise ValueError
"""

import pytest
import os
from config import Config


@pytest.fixture(autouse=True)
def clean_env():
    """Remove config-related env vars between tests."""
    config_vars = [
        'FB_DEVICE', 'COLOR_FORMAT', 'MEDIA_PLAYER',
        'VOLUMIO_URL', 'MOODE_URL', 'LMS_URL', 'STANDBY_TIMEOUT'
    ]
    original = {}
    for var in config_vars:
        original[var] = os.environ.pop(var, None)
    yield
    # Restore original values
    for var, value in original.items():
        if value is not None:
            os.environ[var] = value
        else:
            os.environ.pop(var, None)


def test_config_defaults():
    """Config uses sensible defaults when no env vars are set."""
    cfg = Config()
    
    assert cfg.display_width == 480
    assert cfg.display_height == 320
    assert cfg.framebuffer_device == "/dev/fb0"
    assert cfg.color_format == "RGB565"
    assert cfg.media_player_type == "volumio"
    assert cfg.mode_cycle_time == 30
    assert cfg.standby_timeout == 600


def test_config_env_FB_DEVICE(monkeypatch):
    """Config loads FB_DEVICE from environment."""
    monkeypatch.setenv("FB_DEVICE", "/dev/fb1")
    cfg = Config()
    assert cfg.framebuffer_device == "/dev/fb1"


def test_config_env_COLOR_FORMAT(monkeypatch):
    """Config loads COLOR_FORMAT from environment."""
    monkeypatch.setenv("COLOR_FORMAT", "BGR565")
    cfg = Config()
    assert cfg.color_format == "BGR565"


def test_config_env_MEDIA_PLAYER(monkeypatch):
    """Config loads MEDIA_PLAYER from environment and normalizes to lowercase."""
    monkeypatch.setenv("MEDIA_PLAYER", "MoOde")
    cfg = Config()
    assert cfg.media_player_type == "moode"


def test_config_env_VOLUMIO_URL(monkeypatch):
    """Config loads VOLUMIO_URL from environment."""
    test_url = "ws://192.168.1.50:3000/socket.io/?EIO=3&transport=websocket"
    monkeypatch.setenv("VOLUMIO_URL", test_url)
    cfg = Config()
    assert cfg.volumio_url == test_url


def test_config_env_MOODE_URL(monkeypatch):
    """Config loads MOODE_URL from environment."""
    test_url = "ws://192.168.1.60/moode"
    monkeypatch.setenv("MOODE_URL", test_url)
    cfg = Config()
    assert cfg.moode_url == test_url


def test_config_env_LMS_URL(monkeypatch):
    """Config loads LMS_URL from environment."""
    test_url = "ws://192.168.1.70:9000"
    monkeypatch.setenv("LMS_URL", test_url)
    cfg = Config()
    assert cfg.lms_url == test_url


def test_config_env_STANDBY_TIMEOUT(monkeypatch):
    """Config loads and parses STANDBY_TIMEOUT from environment."""
    monkeypatch.setenv("STANDBY_TIMEOUT", "1200")
    cfg = Config()
    assert cfg.standby_timeout == 1200


def test_config_env_STANDBY_TIMEOUT_invalid(monkeypatch):
    """Config raises ValueError for invalid STANDBY_TIMEOUT."""
    monkeypatch.setenv("STANDBY_TIMEOUT", "not_a_number")
    with pytest.raises(ValueError, match="Invalid STANDBY_TIMEOUT"):
        Config()


def test_config_validate_negative_standby_timeout():
    """Config.validate() raises ValueError for negative standby_timeout."""
    cfg = Config()
    cfg.standby_timeout = -1
    with pytest.raises(ValueError, match="standby_timeout must be positive"):
        cfg.validate()


def test_config_validate_zero_display_width():
    """Config.validate() raises ValueError for zero display width."""
    cfg = Config()
    cfg.display_width = 0
    with pytest.raises(ValueError, match="Display dimensions must be positive"):
        cfg.validate()


def test_config_validate_negative_display_height():
    """Config.validate() raises ValueError for negative display height."""
    cfg = Config()
    cfg.display_height = -100
    with pytest.raises(ValueError, match="Display dimensions must be positive"):
        cfg.validate()


def test_config_validate_invalid_media_player_type():
    """Config.validate() raises ValueError for unknown media_player_type."""
    cfg = Config()
    cfg.media_player_type = "unknown_player"
    with pytest.raises(ValueError, match="media_player_type must be one of"):
        cfg.validate()


def test_config_validate_empty_framebuffer_device():
    """Config.validate() raises ValueError for empty framebuffer_device."""
    cfg = Config()
    cfg.framebuffer_device = ""
    with pytest.raises(ValueError, match="framebuffer_device cannot be empty"):
        cfg.validate()


def test_config_validate_passes_with_valid_settings():
    """Config.validate() passes with all valid settings."""
    cfg = Config()
    cfg.validate()  # Should not raise


def test_config_validate_picore():
    """Config.validate() accepts picore as valid media_player_type."""
    cfg = Config()
    cfg.media_player_type = "picore"
    cfg.validate()  # Should not raise


def test_config_validate_moode():
    """Config.validate() accepts moode as valid media_player_type."""
    cfg = Config()
    cfg.media_player_type = "moode"
    cfg.validate()  # Should not raise


def test_config_validate_color_format_rgb565():
    """Config.validate() accepts RGB565 (default color format)."""
    cfg = Config()
    assert cfg.color_format == "RGB565"
    cfg.validate()  # Should not raise


def test_config_validate_color_format_bgr565():
    """Config.validate() accepts BGR565 as valid color format."""
    cfg = Config()
    cfg.color_format = "BGR565"
    cfg.validate()  # Should not raise


def test_config_validate_color_format_invalid():
    """Config.validate() rejects unsupported color formats."""
    cfg = Config()
    cfg.color_format = "RGB888"
    with pytest.raises(ValueError, match="color_format must be one of"):
        cfg.validate()


def test_config_validate_color_format_case_insensitive():
    """Config.validate() accepts color_format in any case."""
    cfg = Config()
    cfg.color_format = "bgr565"
    cfg.validate()  # Should not raise
    
    cfg.color_format = "Rgb565"
    cfg.validate()  # Should not raise
