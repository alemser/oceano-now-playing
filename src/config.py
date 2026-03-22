"""Application configuration with defaults and validation.

Centralizes all settings (hardware, media player, timing) with environment
variable overrides and validation. Enables clean separation of configuration
from business logic.
"""

import os
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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

    # Media player
    media_player_type: str = "volumio"
    volumio_url: str = "ws://localhost:3000/socket.io/?EIO=3&transport=websocket"
    moode_url: str = "ws://localhost/moode"
    lms_url: str = "ws://localhost:9000"

    # Timing (seconds)
    mode_cycle_time: int = 30  # seconds between text/artwork modes
    standby_timeout: int = 600  # seconds before display sleeps (10 min)

    def __post_init__(self) -> None:
        """Load environment variables and validate.
        
        Environment variables override the defaults:
        - FB_DEVICE: framebuffer device path
        - COLOR_FORMAT: RGB565 or other PIL format
        - MEDIA_PLAYER: volumio, moode, or picore
        - VOLUMIO_URL: WebSocket URL for Volumio
        - MOODE_URL: WebSocket URL for MoOde
        - LMS_URL: WebSocket URL for piCorePlayer/LMS
        - STANDBY_TIMEOUT: display sleep timeout in seconds
        """
        # Load environment overrides
        self.framebuffer_device = os.getenv(
            "FB_DEVICE", self.framebuffer_device
        )
        self.color_format = os.getenv("COLOR_FORMAT", self.color_format)
        self.media_player_type = os.getenv(
            "MEDIA_PLAYER", self.media_player_type
        ).lower()
        self.volumio_url = os.getenv("VOLUMIO_URL", self.volumio_url)
        self.moode_url = os.getenv("MOODE_URL", self.moode_url)
        self.lms_url = os.getenv("LMS_URL", self.lms_url)

        # Parse integer environment variables with validation
        try:
            if "STANDBY_TIMEOUT" in os.environ:
                self.standby_timeout = int(os.environ["STANDBY_TIMEOUT"])
        except ValueError as e:
            raise ValueError(
                f"Invalid STANDBY_TIMEOUT environment variable: {e}"
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
        valid_players = ("volumio", "moode", "picore")
        if self.media_player_type not in valid_players:
            raise ValueError(
                f"media_player_type must be one of {valid_players}, "
                f"got '{self.media_player_type}'"
            )

        # Framebuffer device
        if not self.framebuffer_device:
            raise ValueError("framebuffer_device cannot be empty")

    def log_config(self) -> None:
        """Log the current configuration at INFO level."""
        logger.info(
            f"Display: {self.display_width}x{self.display_height}, "
            f"format={self.color_format}, device={self.framebuffer_device}"
        )
        logger.info(
            f"Media Player: {self.media_player_type.upper()}, "
            f"standby_timeout={self.standby_timeout}s, "
            f"mode_cycle_time={self.mode_cycle_time}s"
        )
        if self.media_player_type == "volumio":
            logger.info(f"Volumio URL: {self.volumio_url}")
        elif self.media_player_type == "moode":
            logger.info(f"MoOde URL: {self.moode_url}")
        elif self.media_player_type == "picore":
            logger.info(f"LMS URL: {self.lms_url}")
