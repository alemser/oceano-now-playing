"""Application configuration with defaults and validation.

Centralizes all settings (hardware, media player, timing) with environment
variable overrides and validation. Enables clean separation of configuration
from business logic.
"""

import os
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


UI_PRESETS = {
    "high_contrast_rotate": ("high_contrast", "rotate"),
    "high_contrast_text": ("high_contrast", "text"),
    "high_contrast_artwork": ("high_contrast", "artwork"),
    "high_contrast_hybrid": ("high_contrast", "hybrid"),
    "classic_rotate": ("classic", "rotate"),
    "classic_text": ("classic", "text"),
    "classic_artwork": ("classic", "artwork"),
    "classic_hybrid": ("classic", "hybrid"),
}


def _parse_bool_env(var_name: str, default: bool) -> bool:
    """Parse a boolean environment variable using common true/false values."""
    value = os.getenv(var_name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(
        f"Invalid {var_name} environment variable: expected true/false, got '{value}'"
    )


@dataclass
class Config:
    """Application settings with environment variable overrides and validation.
    
    Display hardware settings, media player type and URLs, and timing parameters
    are all defined here with sensible defaults. Environment variables can override
    any setting.
    """

    # Display hardware
    display_width: int = 480
    display_height: int = 320
    framebuffer_device: str = "/dev/fb0"
    color_format: str = "RGB565"
    layout_profile: str = "high_contrast"
    display_mode: str = "rotate"
    ui_preset: str = "high_contrast_rotate"

    # Media player
    media_player_type: str = "auto"
    volumio_url: str = "ws://localhost:3000/socket.io/?EIO=3&transport=websocket"
    moode_url: str = "http://localhost/engine-mpd.php"
    lms_url: str = "ws://localhost:9000"
    external_artwork_enabled: bool = True

    # Timing (seconds)
    mode_cycle_time: int = 30  # seconds between text/artwork modes
    standby_timeout: int = 600  # seconds before display sleeps (10 min)

    def __post_init__(self) -> None:
        """Load environment variable overrides.
        
        Parses and applies environment variable overrides for all settings.
        Note: Validation is not performed here; call validate() explicitly
        after initialization to check all values.
        
        Environment variables (with defaults):
        - FB_DEVICE: framebuffer device path (default: /dev/fb0)
        - COLOR_FORMAT: RGB565 or BGR565 (default: RGB565)
        - UI_PRESET: combined style+mode preset (default: high_contrast_rotate)
        - LAYOUT_PROFILE: renderer layout profile (classic or high_contrast)
        - DISPLAY_MODE: rotate, text, artwork, or hybrid
        - MEDIA_PLAYER: auto, volumio, moode, or picore (default: auto)
        - VOLUMIO_URL: WebSocket URL for Volumio
        - MOODE_URL: HTTP polling endpoint for MoOde (e.g., http://localhost/engine-mpd.php)
        - LMS_URL: WebSocket URL for piCorePlayer/LMS
        - EXTERNAL_ARTWORK_ENABLED: enable external artwork fallback lookups (default: true)
        - CYCLE_TIME: text/artwork mode cycle in seconds (default: 30)
        - STANDBY_TIMEOUT: display sleep timeout in seconds (default: 600)
        
        Raises:
            ValueError: If CYCLE_TIME or STANDBY_TIMEOUT cannot be parsed as an integer.
        """
        # Load environment overrides
        self.framebuffer_device = os.getenv(
            "FB_DEVICE", self.framebuffer_device
        )
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

        self.media_player_type = os.getenv(
            "MEDIA_PLAYER", self.media_player_type
        ).lower()
        self.volumio_url = os.getenv("VOLUMIO_URL", self.volumio_url)
        self.moode_url = os.getenv("MOODE_URL", self.moode_url)
        self.lms_url = os.getenv("LMS_URL", self.lms_url)
        self.external_artwork_enabled = _parse_bool_env(
            "EXTERNAL_ARTWORK_ENABLED",
            self.external_artwork_enabled,
        )

        # Parse integer environment variables with validation
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
        """Validate all configuration values.
        
        Raises:
            ValueError: If any setting is invalid.
        """
        # Display dimensions
        if self.display_width <= 0 or self.display_height <= 0:
            raise ValueError(
                f"Display dimensions must be positive, "
                f"got {self.display_width}x{self.display_height}"
            )

        # Timing
        if self.mode_cycle_time <= 0:
            raise ValueError(
                f"mode_cycle_time must be positive, got {self.mode_cycle_time}"
            )
        if self.standby_timeout <= 0:
            raise ValueError(
                f"standby_timeout must be positive, got {self.standby_timeout}"
            )

        # Media player type
        valid_players = ("auto", "volumio", "moode", "picore")
        if self.media_player_type not in valid_players:
            raise ValueError(
                f"media_player_type must be one of {valid_players}, "
                f"got '{self.media_player_type}'"
            )

        # Color format (only RGB565 and BGR565 are supported)
        valid_formats = ("rgb565", "bgr565")
        if self.color_format.lower() not in valid_formats:
            raise ValueError(
                f"color_format must be one of {valid_formats}, "
                f"got '{self.color_format}'"
            )

        # Renderer layout profile
        valid_layout_profiles = ("classic", "high_contrast")
        if self.layout_profile not in valid_layout_profiles:
            raise ValueError(
                f"layout_profile must be one of {valid_layout_profiles}, "
                f"got '{self.layout_profile}'"
            )

        valid_display_modes = ("rotate", "text", "artwork", "hybrid")
        if self.display_mode not in valid_display_modes:
            raise ValueError(
                f"display_mode must be one of {valid_display_modes}, "
                f"got '{self.display_mode}'"
            )

        valid_ui_presets = tuple(UI_PRESETS.keys())
        if self.ui_preset not in valid_ui_presets:
            raise ValueError(
                f"ui_preset must be one of {valid_ui_presets}, "
                f"got '{self.ui_preset}'"
            )

        # Framebuffer device
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
            f"Media Player: {self.media_player_type.upper()}, "
            f"standby_timeout={self.standby_timeout}s, "
            f"mode_cycle_time={self.mode_cycle_time}s, "
            f"external_artwork={'on' if self.external_artwork_enabled else 'off'}"
        )
        if self.media_player_type == "volumio":
            logger.info(f"Volumio URL: {self.volumio_url}")
        elif self.media_player_type == "moode":
            logger.info(f"MoOde URL: {self.moode_url}")
        elif self.media_player_type == "picore":
            logger.info(f"LMS URL: {self.lms_url}")
