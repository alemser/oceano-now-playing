"""Tests for the Config class."""

import pytest
import os
from config import Config


@pytest.fixture(autouse=True)
def clean_env():
    """Remove config-related env vars between tests."""
    config_vars = [
        'FB_DEVICE', 'COLOR_FORMAT', 'UI_PRESET', 'LAYOUT_PROFILE', 'DISPLAY_MODE',
        'CYCLE_TIME', 'STANDBY_TIMEOUT', 'OCEANO_STATE_FILE', 'VU_SOCKET',
    ]
    original = {}
    for var in config_vars:
        original[var] = os.environ.pop(var, None)
    yield
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
    assert cfg.oceano_state_file == "/tmp/oceano-state.json"
    assert cfg.mode_cycle_time == 30
    assert cfg.standby_timeout == 600


def test_config_env_FB_DEVICE(monkeypatch):
    monkeypatch.setenv("FB_DEVICE", "/dev/fb1")
    cfg = Config()
    assert cfg.framebuffer_device == "/dev/fb1"


def test_config_env_COLOR_FORMAT(monkeypatch):
    monkeypatch.setenv("COLOR_FORMAT", "BGR565")
    cfg = Config()
    assert cfg.color_format == "BGR565"


def test_config_env_UI_PRESET(monkeypatch):
    monkeypatch.setenv("UI_PRESET", "high_contrast_artwork")
    cfg = Config()
    assert cfg.ui_preset == "high_contrast_artwork"
    assert cfg.layout_profile == "high_contrast"
    assert cfg.display_mode == "artwork"


def test_config_env_UI_PRESET_hybrid(monkeypatch):
    monkeypatch.setenv("UI_PRESET", "high_contrast_hybrid")
    cfg = Config()
    assert cfg.layout_profile == "high_contrast"
    assert cfg.display_mode == "hybrid"


def test_config_env_UI_PRESET_invalid(monkeypatch):
    monkeypatch.setenv("UI_PRESET", "retro_magic")
    with pytest.raises(ValueError, match="Invalid UI_PRESET"):
        Config()


def test_config_env_LAYOUT_PROFILE(monkeypatch):
    monkeypatch.setenv("LAYOUT_PROFILE", "high_contrast")
    cfg = Config()
    assert cfg.layout_profile == "high_contrast"


def test_config_env_DISPLAY_MODE(monkeypatch):
    monkeypatch.setenv("DISPLAY_MODE", "artwork")
    cfg = Config()
    assert cfg.display_mode == "artwork"


def test_config_display_mode_overrides_ui_preset(monkeypatch):
    monkeypatch.setenv("UI_PRESET", "high_contrast_artwork")
    monkeypatch.setenv("DISPLAY_MODE", "text")
    cfg = Config()
    assert cfg.layout_profile == "high_contrast"
    assert cfg.display_mode == "text"


def test_config_env_DISPLAY_MODE_vu(monkeypatch):
    monkeypatch.setenv("DISPLAY_MODE", "vu")
    cfg = Config()
    assert cfg.display_mode == "vu"
    cfg.validate()  # should not raise


def test_config_env_VU_SOCKET(monkeypatch):
    monkeypatch.setenv("VU_SOCKET", "/tmp/custom-vu.sock")
    cfg = Config()
    assert cfg.vu_socket == "/tmp/custom-vu.sock"


def test_config_env_OCEANO_STATE_FILE(monkeypatch):
    monkeypatch.setenv("OCEANO_STATE_FILE", "/tmp/custom-state.json")
    cfg = Config()
    assert cfg.oceano_state_file == "/tmp/custom-state.json"


def test_config_env_STANDBY_TIMEOUT(monkeypatch):
    monkeypatch.setenv("STANDBY_TIMEOUT", "1200")
    cfg = Config()
    assert cfg.standby_timeout == 1200


def test_config_env_CYCLE_TIME(monkeypatch):
    monkeypatch.setenv("CYCLE_TIME", "45")
    cfg = Config()
    assert cfg.mode_cycle_time == 45


def test_config_env_CYCLE_TIME_invalid(monkeypatch):
    monkeypatch.setenv("CYCLE_TIME", "not_a_number")
    with pytest.raises(ValueError, match="Invalid CYCLE_TIME or STANDBY_TIMEOUT"):
        Config()


def test_config_env_STANDBY_TIMEOUT_invalid(monkeypatch):
    monkeypatch.setenv("STANDBY_TIMEOUT", "not_a_number")
    with pytest.raises(ValueError, match="Invalid CYCLE_TIME or STANDBY_TIMEOUT"):
        Config()


def test_config_validate_invalid_layout_profile():
    cfg = Config()
    cfg.layout_profile = "retro"
    with pytest.raises(ValueError, match="layout_profile must be one of"):
        cfg.validate()


def test_config_validate_invalid_display_mode():
    cfg = Config()
    cfg.display_mode = "mosaic"
    with pytest.raises(ValueError, match="display_mode must be one of"):
        cfg.validate()


def test_config_validate_negative_standby_timeout():
    cfg = Config()
    cfg.standby_timeout = -1
    with pytest.raises(ValueError, match="standby_timeout must be positive"):
        cfg.validate()


def test_config_validate_zero_display_width():
    cfg = Config()
    cfg.display_width = 0
    with pytest.raises(ValueError, match="Display dimensions must be positive"):
        cfg.validate()


def test_config_validate_negative_display_height():
    cfg = Config()
    cfg.display_height = -100
    with pytest.raises(ValueError, match="Display dimensions must be positive"):
        cfg.validate()


def test_config_validate_empty_framebuffer_device():
    cfg = Config()
    cfg.framebuffer_device = ""
    with pytest.raises(ValueError, match="framebuffer_device cannot be empty"):
        cfg.validate()


def test_config_validate_passes_with_valid_settings():
    cfg = Config()
    cfg.validate()  # should not raise


def test_config_validate_color_format_rgb565():
    cfg = Config()
    assert cfg.color_format == "RGB565"
    cfg.validate()


def test_config_validate_color_format_bgr565():
    cfg = Config()
    cfg.color_format = "BGR565"
    cfg.validate()


def test_config_validate_color_format_invalid():
    cfg = Config()
    cfg.color_format = "RGB888"
    with pytest.raises(ValueError, match="color_format must be one of"):
        cfg.validate()


def test_config_validate_color_format_case_insensitive():
    cfg = Config()
    cfg.color_format = "bgr565"
    cfg.validate()

    cfg.color_format = "Rgb565"
    cfg.validate()
