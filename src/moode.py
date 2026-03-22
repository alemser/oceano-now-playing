"""MoOde Audio Player client stub.

Placeholder implementation of the MediaPlayer interface for MoOde Audio,
a Raspberry Pi-based music player OS (https://moodeaudio.org).

MoOde exposes playback state via a local Unix socket and a PHP/WebSocket
API. This stub provides the correct class structure so the state machine
can be wired up without modification; a future contributor only needs to
fill in the connection and message-parsing logic below.
"""

import logging
from media_player import MediaPlayer

logger = logging.getLogger(__name__)

# Default MoOde WebSocket endpoint (Socket.io compatible)
MOODE_DEFAULT_URL = "ws://localhost/moode"


class MoodeClient(MediaPlayer):
    """MediaPlayer implementation for MoOde Audio.

    This is a stub — the interface is complete but the transport layer
    (WebSocket connection to MoOde) is not yet implemented.  Override
    the methods below once the MoOde API details are confirmed.
    """

    def __init__(self, url: str = MOODE_DEFAULT_URL) -> None:
        self.url = url
        self._connected = False

    def connect(self) -> bool:
        """Connect to the MoOde WebSocket endpoint.

        Returns:
            True if connection was successful, False otherwise.
        """
        logger.warning(
            "MoodeClient.connect() is not yet implemented. "
            "Contribute the MoOde WebSocket transport to enable this player."
        )
        return False

    def receive_message(self, timeout: float = 1.0) -> dict | None:
        """Receive the next playback state from MoOde.

        Args:
            timeout: Maximum seconds to wait for a message.

        Returns:
            A state dictionary when a new playback state is available,
            or None if no message arrived within the timeout.
        """
        logger.warning(
            "MoodeClient.receive_message() is not yet implemented."
        )
        return None

    def is_connected(self) -> bool:
        """Check if currently connected to MoOde.

        Returns:
            True if the connection is active, False otherwise.
        """
        return self._connected

    def close(self) -> None:
        """Close the connection to MoOde gracefully."""
        self._connected = False
