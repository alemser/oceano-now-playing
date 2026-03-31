"""Abstract base class for the media player integration layer."""

from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class MediaPlayer(ABC):
    """Interface for the metadata transport layer."""

    @abstractmethod
    def connect(self) -> bool:
        ...

    @abstractmethod
    def receive_message(self, timeout: float) -> dict | None:
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    def get_state(self) -> None:
        return None

    def _resolved_artwork(self, cache_key: str, image, source: str) -> dict:
        """Build a renderer-friendly artwork payload."""
        return {
            "cache_key": cache_key,
            "image": image,
            "source": source,
        }
