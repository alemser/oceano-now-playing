"""Application configuration with defaults and validation."""

import os
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


UI_PRESETS = {
    "high_contrast_rotate": ("high_contrast", "rotate"),
    "high_contrast_text": ("high_contrast", "text"),
    "high_contrast_artwork": ("high_contrast", "artwork"),
    "high_contrast_hybrid": ("high_contrast", "hybrid"),
    "high_contrast_vu": ("high_contrast", "vu"),
}


@dataclass
class Config:
    """Application settings with environment variable overrides and validation."""

    # Display hardware
    display_width: int = 480
    display_height: int = 320
    framebuffer_device: str = "/dev/fb0"
    color_format: str = "RGB565"
    layout_profile: str = "high_contrast"
    display_mode: str = "rotate"
    ui_preset: str = "high_contrast_rotate"

    # Metadata source
    oceano_state_file: str = "/tmp/oceano-state.json"

    # VU meter
    vu_socket: str = "/tmp/oceano-vu.sock"

    # Timing (seconds)
    mode_cycle_time: int = 30
    standby_timeout: int = 600

    def __post_init__(self) -> None:
        """Load environment variable overrides.

        Environment variables:
        - FB_DEVICE: framebuffer device path (default: /dev/fb0)
        - COLOR_FORMAT: RGB565 or BGR565 (default: RGB565)
        - UI_PRESET: combined style+mode preset (default: high_contrast_rotate)
        - LAYOUT_PROFILE: renderer layout profile
        - DISPLAY_MODE: rotate, text, artwork, hybrid, or vu
        - OCEANO_STATE_FILE: unified state file path (default: /tmp/oceano-state.json)
        - VU_SOCKET: VU meter socket path
        - CYCLE_TIME: text/artwork mode cycle in seconds (default: 30)
        - STANDBY_TIMEOUT: display sleep timeout in seconds (default: 600)
        """
        self.framebuffer_device = os.getenv("FB_DEVICE", self.framebuffer_device)
        self.color_format = os.getenv("COLOR_FORMAT", self.color_format)
        self.ui_preset = os.getenv("UI_PRESET", self.ui_preset).lower()
        if self.ui_preset not in UI_PRESETS:
            valid_ui_presets = tuple(UI_PRESETS.keys())
            raise ValueError(
                f"Invalid UI_PRESET environment variable: must be one of {valid_ui_presets}, "
                f"got '{self.ui_preset}'"
            )

        self.layout_profile, self.display_mode = UI_PRESETS[self.ui_preset]

        if "LAYOUT_PROFILE" in os.environ:
            self.layout_profile = os.environ["LAYOUT_PROFILE"].lower()
        if "DISPLAY_MODE" in os.environ:
            self.display_mode = os.environ["DISPLAY_MODE"].lower()

        self.oceano_state_file = os.getenv("OCEANO_STATE_FILE", self.oceano_state_file)
        self.vu_socket = os.getenv("VU_SOCKET", self.vu_socket)

        try:
            if "CYCLE_TIME" in os.environ:
                self.mode_cycle_time = int(os.environ["CYCLE_TIME"])
            if "STANDBY_TIMEOUT" in os.environ:
                self.standby_timeout = int(os.environ["STANDBY_TIMEOUT"])
        except ValueError as e:
            raise ValueError(
                f"Invalid CYCLE_TIME or STANDBY_TIMEOUT environment variable: {e}"
            )

    def validate(self) -> None:
        """Validate all configuration values."""
        if self.display_width <= 0 or self.display_height <= 0:
            raise ValueError(
                f"Display dimensions must be positive, "
                f"got {self.display_width}x{self.display_height}"
            )

        if self.mode_cycle_time <= 0:
            raise ValueError(f"mode_cycle_time must be positive, got {self.mode_cycle_time}")
        if self.standby_timeout <= 0:
            raise ValueError(f"standby_timeout must be positive, got {self.standby_timeout}")

        valid_formats = ("rgb565", "bgr565")
        if self.color_format.lower() not in valid_formats:
            raise ValueError(
                f"color_format must be one of {valid_formats}, got '{self.color_format}'"
            )

        valid_layout_profiles = ("classic", "high_contrast")
        if self.layout_profile not in valid_layout_profiles:
            raise ValueError(
                f"layout_profile must be one of {valid_layout_profiles}, got '{self.layout_profile}'"
            )

        valid_display_modes = ("rotate", "text", "artwork", "hybrid", "vu")
        if self.display_mode not in valid_display_modes:
            raise ValueError(
                f"display_mode must be one of {valid_display_modes}, got '{self.display_mode}'"
            )

        valid_ui_presets = tuple(UI_PRESETS.keys())
        if self.ui_preset not in valid_ui_presets:
            raise ValueError(
                f"ui_preset must be one of {valid_ui_presets}, got '{self.ui_preset}'"
            )

        if not self.framebuffer_device:
            raise ValueError("framebuffer_device cannot be empty")

    def log_config(self) -> None:
        """Log the current configuration at INFO level."""
        logger.info(
            f"Display: {self.display_width}x{self.display_height}, "
            f"format={self.color_format}, device={self.framebuffer_device}, "
            f"preset={self.ui_preset}, layout={self.layout_profile}, mode={self.display_mode}"
        )
        logger.info(
            f"State file: {self.oceano_state_file}, "
            f"standby_timeout={self.standby_timeout}s, "
            f"mode_cycle_time={self.mode_cycle_time}s"
        )
