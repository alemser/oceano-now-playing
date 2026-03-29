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
        'FB_DEVICE', 'COLOR_FORMAT', 'UI_PRESET', 'LAYOUT_PROFILE', 'DISPLAY_MODE', 'MEDIA_PLAYER',
        'CYCLE_TIME', 'STANDBY_TIMEOUT', 'EXTERNAL_ARTWORK_ENABLED', 'OCEANO_METADATA_PIPE'
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
    assert cfg.ui_preset == "high_contrast_rotate"
    assert cfg.layout_profile == "high_contrast"
    assert cfg.display_mode == "rotate"
    assert cfg.media_player_type == "auto"
    assert cfg.external_artwork_enabled is True
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


def test_config_env_UI_PRESET(monkeypatch):
    """Config maps UI_PRESET to layout profile and display mode."""
    monkeypatch.setenv("UI_PRESET", "classic_artwork")
    cfg = Config()

    assert cfg.ui_preset == "classic_artwork"
    assert cfg.layout_profile == "classic"
    assert cfg.display_mode == "artwork"


def test_config_env_UI_PRESET_hybrid(monkeypatch):
    """Config supports one-screen hybrid preset."""
    monkeypatch.setenv("UI_PRESET", "high_contrast_hybrid")
    cfg = Config()

    assert cfg.layout_profile == "high_contrast"
    assert cfg.display_mode == "hybrid"


def test_config_env_UI_PRESET_invalid(monkeypatch):
    """Config rejects invalid UI_PRESET values."""
    monkeypatch.setenv("UI_PRESET", "retro_magic")
    with pytest.raises(ValueError, match="Invalid UI_PRESET"):
        Config()


def test_config_env_LAYOUT_PROFILE(monkeypatch):
    """Config allows explicit LAYOUT_PROFILE override."""
    monkeypatch.setenv("LAYOUT_PROFILE", "classic")
    cfg = Config()
    assert cfg.layout_profile == "classic"


def test_config_env_DISPLAY_MODE(monkeypatch):
    """Config loads DISPLAY_MODE from environment."""
    monkeypatch.setenv("DISPLAY_MODE", "artwork")
    cfg = Config()
    assert cfg.display_mode == "artwork"


def test_config_display_mode_overrides_ui_preset(monkeypatch):
    """DISPLAY_MODE should override mode chosen by UI_PRESET."""
    monkeypatch.setenv("UI_PRESET", "classic_artwork")
    monkeypatch.setenv("DISPLAY_MODE", "text")
    cfg = Config()

    assert cfg.layout_profile == "classic"
    assert cfg.display_mode == "text"


def test_config_validate_invalid_layout_profile():
    """Config.validate() rejects unsupported layout profiles."""
    cfg = Config()
    cfg.layout_profile = "retro"
    with pytest.raises(ValueError, match="layout_profile must be one of"):
        cfg.validate()


def test_config_validate_invalid_display_mode():
    """Config.validate() rejects unsupported display modes."""
    cfg = Config()
    cfg.display_mode = "mosaic"
    with pytest.raises(ValueError, match="display_mode must be one of"):
        cfg.validate()


def test_config_env_DISPLAY_MODE_vu(monkeypatch):
    """Config accepts vu as a valid DISPLAY_MODE."""
    monkeypatch.setenv("DISPLAY_MODE", "vu")
    cfg = Config()
    assert cfg.display_mode == "vu"
    cfg.validate()  # should not raise


def test_config_env_VU_SOCKET(monkeypatch):
    """Config loads VU_SOCKET from environment."""
    monkeypatch.setenv("VU_SOCKET", "/tmp/custom-vu.sock")
    cfg = Config()
    assert cfg.vu_socket == "/tmp/custom-vu.sock"


def test_config_env_MEDIA_PLAYER(monkeypatch):
    """Config normalizes explicit Oceano selection to lowercase."""
    monkeypatch.setenv("MEDIA_PLAYER", "OcEaNo")
    cfg = Config()
    assert cfg.media_player_type == "oceano"


def test_config_env_MEDIA_PLAYER_legacy_value_is_coerced(monkeypatch):
    """Unknown MEDIA_PLAYER values are coerced to 'auto' for migration safety."""
    monkeypatch.setenv("MEDIA_PLAYER", "volumio")
    cfg = Config()
    assert cfg.media_player_type == "auto"


def test_config_env_OCEANO_METADATA_PIPE(monkeypatch):
    """Config loads OCEANO_METADATA_PIPE from environment."""
    test_pipe = "/tmp/custom-shairport-metadata"
    monkeypatch.setenv("OCEANO_METADATA_PIPE", test_pipe)
    cfg = Config()
    assert cfg.oceano_metadata_pipe == test_pipe


def test_config_env_STANDBY_TIMEOUT(monkeypatch):
    """Config loads and parses STANDBY_TIMEOUT from environment."""
    monkeypatch.setenv("STANDBY_TIMEOUT", "1200")
    cfg = Config()
    assert cfg.standby_timeout == 1200


def test_config_env_CYCLE_TIME(monkeypatch):
    """Config loads and parses CYCLE_TIME from environment."""
    monkeypatch.setenv("CYCLE_TIME", "45")
    cfg = Config()
    assert cfg.mode_cycle_time == 45


def test_config_env_CYCLE_TIME_invalid(monkeypatch):
    """Config raises ValueError for invalid CYCLE_TIME."""
    monkeypatch.setenv("CYCLE_TIME", "not_a_number")
    with pytest.raises(ValueError, match="Invalid CYCLE_TIME or STANDBY_TIMEOUT"):
        Config()


def test_config_env_STANDBY_TIMEOUT_invalid(monkeypatch):
    """Config raises ValueError for invalid STANDBY_TIMEOUT."""
    monkeypatch.setenv("STANDBY_TIMEOUT", "not_a_number")
    with pytest.raises(ValueError, match="Invalid CYCLE_TIME or STANDBY_TIMEOUT"):
        Config()


def test_config_env_external_artwork_enabled_false(monkeypatch):
    """Config loads EXTERNAL_ARTWORK_ENABLED from environment."""
    monkeypatch.setenv("EXTERNAL_ARTWORK_ENABLED", "false")
    cfg = Config()
    assert cfg.external_artwork_enabled is False


def test_config_env_external_artwork_enabled_invalid(monkeypatch):
    """Config rejects invalid EXTERNAL_ARTWORK_ENABLED values."""
    monkeypatch.setenv("EXTERNAL_ARTWORK_ENABLED", "maybe")
    with pytest.raises(ValueError, match="Invalid EXTERNAL_ARTWORK_ENABLED"):
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


def test_config_validate_oceano():
    """Config.validate() accepts oceano as valid media_player_type."""
    cfg = Config()
    cfg.media_player_type = "oceano"
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


def test_config_validate_media_player_unknown_rejected():
    """Config.validate() rejects unknown media_player_type values."""
    cfg = Config()
    cfg.media_player_type = "volumio"
    with pytest.raises(ValueError, match="media_player_type must be one of"):
        cfg.validate()
