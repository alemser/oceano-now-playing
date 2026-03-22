"""Abstract base class for media player OS integrations.

Defines the interface that all media player implementations must follow,
allowing the state machine and renderer to remain agnostic of the
underlying media OS (Volumio, MoOde, PiCorePlayer, etc.).
"""

from abc import ABC, abstractmethod


class MediaPlayer(ABC):
    """Interface for media player OS integrations.

    Concrete implementations must provide connection management and
    message reception so the main event loop can remain unchanged
    when a new media OS is introduced.
    """

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the media player OS.

        Returns:
            True if connection was successful, False otherwise.
        """
        ...

    @abstractmethod
    def receive_message(self, timeout: float) -> dict | None:
        """Receive the next state message or None on timeout.

        Args:
            timeout: Maximum seconds to wait for a message.

        Returns:
            A state dictionary when a new playback state is available,
            or None if no message arrived within the timeout.
        """
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if currently connected to the media player OS.

        Returns:
            True if the connection is active, False otherwise.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the connection gracefully."""
        ...
