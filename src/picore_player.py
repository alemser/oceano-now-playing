"""PiCorePlayer client stub.

Placeholder implementation of the MediaPlayer interface for piCorePlayer,
a minimal Raspberry Pi music player OS built on Tiny Core Linux that runs
Squeezelite against a Logitech Media Server (LMS) back-end
(https://www.picoreplayer.org).

This stub provides the correct class structure so the state machine can be
wired up without modification; a future contributor only needs to fill in
the LMS JSON-RPC / CLI connection and message-parsing logic below.
"""

import logging
from media_player import MediaPlayer

logger = logging.getLogger(__name__)

# Default LMS JSON-RPC endpoint served by piCorePlayer
PICORE_DEFAULT_URL = "ws://localhost:9000"


class PiCorePlayerClient(MediaPlayer):
    """MediaPlayer implementation for piCorePlayer / LMS.

    This is a stub — the interface is complete but the transport layer
    (LMS CLI or JSON-RPC connection) is not yet implemented.  Override
    the methods below once the LMS API details are confirmed.
    """

    def __init__(self, url: str = PICORE_DEFAULT_URL) -> None:
        self.url = url
        self._connected = False

    def connect(self) -> bool:
        """Connect to the LMS endpoint exposed by piCorePlayer.

        Returns:
            True if connection was successful, False otherwise.
        """
        logger.warning(
            "PiCorePlayerClient.connect() is not yet implemented. "
            "Contribute the LMS transport to enable this player."
        )
        return False

    def receive_message(self, timeout: float = 1.0) -> dict | None:
        """Receive the next playback state from piCorePlayer / LMS.

        Args:
            timeout: Maximum seconds to wait for a message.

        Returns:
            A state dictionary when a new playback state is available,
            or None if no message arrived within the timeout.
        """
        logger.warning(
            "PiCorePlayerClient.receive_message() is not yet implemented."
        )
        return None

    def is_connected(self) -> bool:
        """Check if currently connected to piCorePlayer / LMS.

        Returns:
            True if the connection is active, False otherwise.
        """
        return self._connected

    def close(self) -> None:
        """Close the connection to piCorePlayer / LMS gracefully."""
        self._connected = False
