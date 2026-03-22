"""MoOde Audio Player client.

Implementation of the MediaPlayer interface for MoOde Audio,
a Raspberry Pi-based music player OS (https://moodeaudio.org).

MoOde exposes playback state via HTTP API endpoint `/engine-mpd.php`.
This implementation uses polling to fetch playback state at regular intervals,
maintaining the same MediaPlayer interface as other clients (Volumio, piCorePlayer).
"""

import json
import logging
import requests
from media_player import MediaPlayer

logger = logging.getLogger(__name__)

# Default MoOde HTTP API endpoint
MOODE_DEFAULT_URL = "http://localhost/engine-mpd.php"


class MoodeClient(MediaPlayer):
    """MediaPlayer implementation for MoOde Audio using HTTP polling.

    MoOde doesn't provide real-time WebSocket updates like Volumio, so this
    client polls the `/engine-mpd.php` endpoint periodically. The connection
    interface remains compatible with other MediaPlayer implementations.

    The polling is passive and on-demand: state is fetched when receive_message()
    is called, avoiding constant network requests while maintaining interface
    consistency.
    """

    def __init__(self, url: str = MOODE_DEFAULT_URL) -> None:
        """Initialize MoOde client.

        Args:
            url: HTTP endpoint for MoOde API (default: http://localhost/engine-mpd.php)
        """
        self.url = url
        self._connected = False
        self._last_state: dict | None = None
        self._base_url = self._extract_base_url(url)

    def _extract_base_url(self, url: str) -> str:
        """Extract base URL from full API endpoint.

        Args:
            url: Full endpoint URL (e.g., http://localhost/engine-mpd.php)

        Returns:
            Base URL for relative paths (e.g., http://localhost)
        """
        # Remove the script path to get base URL
        parts = url.split('/')
        # Reconstruct: http://localhost
        return f"{parts[0]}//{parts[2]}"

    def connect(self) -> bool:
        """Test connection to MoOde HTTP API.

        Performs a single request to verify the endpoint is reachable.

        Returns:
            True if connection was successful, False otherwise.
        """
        try:
            response = requests.get(self.url, timeout=3)
            response.raise_for_status()
            # Verify response is valid JSON
            response.json()
            self._connected = True
            logger.info(f"Connected to MoOde at {self.url}")
            return True
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Error connecting to MoOde at {self.url}: {e}")
            self._connected = False
            return False

    def receive_message(self, timeout: float = 1.0) -> dict | None:
        """Poll MoOde for current playback state.

        Fetches the current state from the MoOde API and returns it only if
        it differs from the last polled state (change detection).

        Args:
            timeout: Timeout in seconds for the HTTP request.

        Returns:
            A state dictionary when playback state has changed, or None if
            unchanged or unreachable. Returns None if not connected.
        """
        if not self._connected:
            return None

        try:
            response = requests.get(self.url, timeout=timeout)
            response.raise_for_status()
            state = response.json()
            
            # Convert MoOde fields to standard MediaPlayer state format
            normalized_state = self._normalize_state(state)
            
            # Only return state if it changed
            if normalized_state != self._last_state:
                self._last_state = normalized_state
                return normalized_state
            
            return None
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.debug(f"Error polling MoOde: {e}")
            return None

    def _normalize_state(self, raw_state: dict) -> dict:
        """Convert MoOde API response to standard playback state format.

        Maps MoOde-specific fields to the common state schema used by all
        MediaPlayer implementations.

        Args:
            raw_state: Raw JSON response from MoOde API.

        Returns:
            Normalized state dictionary ready for display/rendering.
        """
        # Extract and convert numeric fields
        elapsed = raw_state.get("elapsed", "")
        seek = None
        if elapsed and str(elapsed).isdigit():
            seek = int(elapsed)

        time = raw_state.get("time")
        duration = None
        if time is not None:
            try:
                duration = int(time) if isinstance(time, (int, float)) else int(time)
            except (ValueError, TypeError):
                pass

        # Convert MoOde status to standard format
        status = raw_state.get("state", "stop")
        if status not in ["play", "pause", "stop"]:
            status = "stop"

        # Build album artwork URL (relative path needs base URL)
        coverurl = raw_state.get("coverurl")
        albumart = None
        if coverurl and coverurl != "/images/default-album-cover.png":
            albumart = f"{self._base_url}{coverurl}" if coverurl.startswith("/") else coverurl

        # Extract quality info from bitrate and encoded fields
        bitrate = raw_state.get("bitrate", "")
        encoded = raw_state.get("encoded", "")
        quality = None
        if encoded:
            quality = encoded
        elif bitrate and bitrate != "0 bps":
            quality = bitrate

        return {
            "title": raw_state.get("title", ""),
            "artist": raw_state.get("artist", ""),
            "album": raw_state.get("album", ""),
            "albumart": albumart,
            "status": status,
            "seek": seek,
            "duration": duration,
            "quality": quality,
            "volume": int(raw_state.get("volume", 100)),
        }

    def is_connected(self) -> bool:
        """Check if currently connected to MoOde.

        Returns:
            True if the connection test passed, False otherwise.
        """
        return self._connected

    def close(self) -> None:
        """Close the connection to MoOde (cleanup).

        No persistent connection to close, but resets internal state.
        """
        self._connected = False
        self._last_state = None
