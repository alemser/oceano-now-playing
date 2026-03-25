"""Abstract base class for the media player integration layer.

Defines the interface that OceanoClient must follow, keeping the state
machine and renderer decoupled from the metadata transport layer.
"""

from abc import ABC, abstractmethod
import logging

from artwork.providers import ArtworkLookup


logger = logging.getLogger(__name__)


class MediaPlayer(ABC):
    """Interface for the metadata transport layer.

    Concrete implementations provide connection management and message
    reception so the main event loop is decoupled from the underlying
    metadata source.
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

    def _resolved_artwork(self, cache_key: str, image, source: str) -> dict:
        """Build a renderer-friendly artwork payload."""
        return {
            "cache_key": cache_key,
            "image": image,
            "source": source,
        }

    def _log_art_decision(
        self,
        source: str,
        cache_key: str | None,
        artist: str,
        album: str,
    ) -> None:
        """Emit a compact, one-line artwork decision log for diagnostics."""
        logger.info(
            "[ART DECISION] source=%s key=%s artist='%s' album='%s'",
            source,
            cache_key or "none",
            artist,
            album,
        )

    def resolve_artwork(self, state: dict, timeout: float = 3.0) -> dict | None:
        """Resolve artwork via external providers using artist and album metadata.

        Args:
            state: Current playback state.
            timeout: Maximum seconds to spend resolving artwork.

        Returns:
            A dictionary containing resolved artwork information, or None if
            no usable artwork is available.

        Notes:
            Set ``self.external_artwork_enabled = False`` on a concrete client
            to disable provider lookups.
        """
        artist = (state.get("artist") or "").strip()
        album = (state.get("album") or "").strip()
        if not artist or not album:
            self._log_art_decision("none-metadata", None, artist, album)
            return None

        if not getattr(self, "external_artwork_enabled", True):
            logger.info(f"[ART FALLBACK] External artwork disabled for {artist} - {album}")
            self._log_art_decision("disabled", None, artist, album)
            return None

        fallback_art = ArtworkLookup.get_artwork(artist, album, timeout=timeout)
        if fallback_art:
            logger.info(f"[ART FALLBACK] Using external artwork provider for {artist} - {album}")
            cache_key = f"fallback:{artist}|{album}"
            self._log_art_decision("fallback", cache_key, artist, album)
            return self._resolved_artwork(
                cache_key,
                fallback_art,
                "fallback",
            )

        logger.warning(f"[ART FALLBACK] No fallback artwork for {artist} - {album}")
        self._log_art_decision("none-provider-miss", None, artist, album)
        return None
